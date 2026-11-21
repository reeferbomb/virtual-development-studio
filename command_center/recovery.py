"""Export and verify a read-only snapshot of a project's Studio records.

Keep the workspace jobs directory and build outputs separately. A matching
checksum identifies the captured JSON and does not authenticate its author.
"""
import argparse
import fcntl
import json
import os
import stat
import sys
from datetime import datetime
from pathlib import Path

from . import checkpoints, defect_store, evidence_history, handoff_store, release_store, scheduler, task_store
from .checkpoints import _locked_directory
from .projects import PROJECT_ID, PROJECT_NAME, TEMPLATES
from .provenance import spec_digest
from .task_store import _valid_digest


FORMAT = 'studio-project-recovery-v1'
REQUIRED = ('project.json', 'spec.json')
RECORD_NAMES = (*REQUIRED, task_store.BOARD, checkpoints.CHECKPOINT, defect_store.REGISTRY,
                release_store.REGISTRY, evidence_history.REGISTRY, handoff_store.REGISTRY)
MAX_RECORD_BYTES = task_store.MAX_FILE_BYTES
# The HTTP encoder may escape Unicode scalars, which consumes up to three
# times their original UTF-8 size. Also allow its spaces and the envelope.
MAX_BUNDLE_BYTES = 4 * len(RECORD_NAMES) * MAX_RECORD_BYTES + 4096
BUNDLE_FIELDS = {'format', 'project_id', 'spec_sha256', 'records', 'bundle_sha256'}


def _fields(record, fields, name):
    if not isinstance(record, dict) or record.keys() != fields:
        raise ValueError(f'Invalid {name} fields')


def _timestamp(value):
    if not isinstance(value, str) or datetime.fromisoformat(value).utcoffset() is None:
        raise ValueError('Expected a timestamp with a timezone')


def _record_digest(data, name):
    if not isinstance(data, dict):
        raise ValueError(f'{name} must contain a JSON object')
    # Bound compact UTF-8 size separately from hashing. The canonical Studio
    # digest ASCII-escapes Unicode and can be much larger than the source.
    try:
        compact = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        if len(compact.encode('utf-8')) > MAX_RECORD_BYTES:
            raise ValueError(f'{name} exceeds the recovery storage limit')
        if json.loads(compact) != data:
            raise ValueError(f'{name} contains values outside the JSON data model')
        return spec_digest(data)
    except (TypeError, RecursionError, OverflowError) as exc:
        raise ValueError(f'Invalid JSON in {name}') from exc


def _bundle_digest(payload):
    try:
        return spec_digest(payload)
    except (TypeError, RecursionError, OverflowError) as exc:
        raise ValueError('Recovery records exceed the supported JSON structure') from exc


def _defects(data):
    _fields(data, {'project_id', 'revision', 'items'}, 'defect registry')
    items = data['items']
    if not isinstance(items, list) or not 1 <= len(items) <= defect_store.MAX_ITEMS:
        raise ValueError('Invalid defect list')
    seen = set()
    minimum_revision = len(items)
    notes = 0
    for item in items:
        _fields(item, defect_store.ITEM_FIELDS, 'defect')
        defect_store._identifier(item['id'])
        if (item['id'] in seen or not _valid_digest(item['spec_sha256'])
                or item['status'] not in ('open', 'resolved')):
            raise ValueError('Invalid defect identity or status')
        seen.add(item['id'])
        defect_store._details(item)
        defect_store._notes(item['evidence'], defect_store._note_limit(item['status']))
        if defect_store._timestamp(item['updated_at']) < defect_store._timestamp(item['created_at']):
            raise ValueError('Invalid defect chronology')
        if item['status'] == 'resolved':
            if len(item['evidence']) < 2:
                raise ValueError('Missing defect resolution evidence')
            minimum_revision += 1
        notes += len(item['evidence'])
    if not minimum_revision <= data['revision'] <= notes:
        raise ValueError('Invalid defect revision')


def _releases(data):
    _fields(data, release_store.RECORD_FIELDS, 'release registry')
    releases = data['releases']
    if not isinstance(releases, list) or not 1 <= len(releases) <= data['revision']:
        raise ValueError('Invalid release list')
    ids, jobs = set(), set()
    for item in releases:
        _fields(item, release_store.RELEASE_FIELDS, 'release')
        if (not release_store._hex(item['id'], 32) or not release_store._hex(item['job_id'], 32)
                or item['id'] in ids or item['job_id'] in jobs
                or not _valid_digest(item['spec_sha256']) or not _valid_digest(item['manifest_sha256'])
                or item['output'] != release_store._output(item['job_id'])):
            raise ValueError('Invalid release identity or output reference')
        ids.add(item['id'])
        jobs.add(item['job_id'])
        _timestamp(item['created_at'])
    if not release_store._hex(data['active_release_id'], 32) or data['active_release_id'] not in ids:
        raise ValueError('Unknown active release')


def _validate_record(name, data, project_id, digest):
    if name == 'spec.json':
        return  # The envelope binds the exact spec object below.
    if name == 'project.json':
        _fields(data, {'id', 'name', 'kind', 'created_at'}, 'project metadata')
        if (data['id'] != project_id or not isinstance(data['name'], str)
                or not PROJECT_NAME.fullmatch(data['name']) or data['name'] != data['name'].strip()
                or not isinstance(data['kind'], str) or data['kind'] not in TEMPLATES):
            raise ValueError('Invalid project metadata or identity')
        _timestamp(data['created_at'])
        return
    if (data.get('project_id') != project_id or type(data.get('revision')) is not int
            or data['revision'] < 1):
        raise ValueError(f'Invalid project identity or revision in {name}')
    if name == task_store.BOARD:
        _fields(data, task_store.RECORD_FIELDS, name)
        if not _valid_digest(data['spec_sha256']):
            raise ValueError('Invalid task board specification digest')
        scheduler.validate_tasks(data['tasks'])
    elif name == checkpoints.CHECKPOINT:
        _fields(data, checkpoints.RECORD_FIELDS, name)
        _timestamp(data['updated_at'])
        checkpoints._validate_work(data)
    elif name == defect_store.REGISTRY:
        _defects(data)
    elif name == release_store.REGISTRY:
        _releases(data)
    elif name == evidence_history.REGISTRY:
        _fields(data, evidence_history.RECORD_FIELDS, name)
        evidence_history.validate_history({**data, 'spec_sha256': digest})
    elif name == handoff_store.REGISTRY:
        handoff_store.validate_record(data, project_id)


def _validate_scope(bundle):
    if bundle['format'] != FORMAT:
        raise ValueError('Unsupported project recovery format')
    project_id = bundle['project_id']
    if (not isinstance(project_id, str) or len(project_id) > 80 or not PROJECT_ID.fullmatch(project_id)
            or not _valid_digest(bundle['spec_sha256'])):
        raise ValueError('Invalid recovery project or specification identity')
    records = bundle['records']
    _fields(records, set(RECORD_NAMES), 'recovery manifest')
    for name in RECORD_NAMES:
        entry = records[name]
        if entry is None:
            if name in REQUIRED:
                raise ValueError(f'Missing required record {name}')
            continue
        _fields(entry, {'sha256', 'data'}, name)
        if not _valid_digest(entry['sha256']) or entry['sha256'] != _record_digest(entry['data'], name):
            raise ValueError(f'Recovery digest mismatch for {name}')
        _validate_record(name, entry['data'], project_id, bundle['spec_sha256'])
    if bundle['spec_sha256'] != records['spec.json']['sha256']:
        raise ValueError('Recovery specification identity mismatch')


def capture_recovery(projects, project_id):
    """Capture only allowlisted project records under one shared directory lock."""
    records = {}
    with _locked_directory(projects.directory(project_id), fcntl.LOCK_SH) as directory:
        for name in RECORD_NAMES:
            try:
                data = task_store._read_json(directory, name)
            except FileNotFoundError:
                if name in REQUIRED:
                    raise ValueError(f'Missing required record {name}') from None
                records[name] = None
            else:
                records[name] = {'data': data}
    # Serialization and validation touch only the captured data. Release the
    # shared lock first so this CPU work cannot hold up the next project writer.
    for name, entry in records.items():
        if entry is not None:
            entry['sha256'] = _record_digest(entry['data'], name)
    payload = dict(format=FORMAT, project_id=project_id, spec_sha256=records['spec.json']['sha256'],
                   records=records)
    for name, entry in records.items():
        if entry is not None:
            _validate_record(name, entry['data'], project_id, payload['spec_sha256'])
    return {**payload, 'bundle_sha256': _bundle_digest(payload)}


def verify_recovery(bundle):
    """Return True for an intact record bundle. Never consult or change a workspace."""
    _fields(bundle, BUNDLE_FIELDS, 'recovery bundle')
    _validate_scope(bundle)
    payload = {key: value for key, value in bundle.items() if key != 'bundle_sha256'}
    if not _valid_digest(bundle['bundle_sha256']) or bundle['bundle_sha256'] != _bundle_digest(payload):
        raise ValueError('Recovery bundle digest mismatch')
    return True


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field in recovery bundle')
        result[key] = value
    return result


def _read_bundle(path):
    with _locked_directory(path.absolute().parent, fcntl.LOCK_SH) as directory:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BUNDLE_BYTES:
                raise ValueError('Expected a regular recovery file within the bundle size limit')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                raw = stream.read(MAX_BUNDLE_BYTES + 1)
        finally:
            os.close(fd)
    if len(raw) > MAX_BUNDLE_BYTES:
        raise ValueError('Recovery file exceeds the bundle size limit')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_fields)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    verify = commands.add_parser('verify', help='verify the contents of an exported JSON file')
    verify.add_argument('path', type=Path)
    args = parser.parse_args(argv)
    try:
        bundle = _read_bundle(args.path)
        verify_recovery(bundle)
    except (OSError, ValueError, RecursionError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(dict(project_id=bundle['project_id'], bundle_sha256=bundle['bundle_sha256'],
                          verified=True, scope='project records',
                          note='Preserve workspace jobs and build output packages separately.')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
