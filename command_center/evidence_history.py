"""Persist explicitly captured observations from the project supervisor."""
import fcntl
import json
import os
import re
import secrets
from datetime import datetime, timezone

from .checkpoints import _locked_directory
from .defect_store import MAX_NOTE, _fields, _text
from .projects import PROJECT_ID, TEMPLATES
from .provenance import spec_digest
from .supervisor import _LABELS
from .task_store import MAX_FILE_BYTES, _read_json, _valid_digest


REGISTRY = 'evidence-history.json'
MAX_ITEMS = 100
MAX_EVIDENCE = 8192  # A board check can name 100 blocked tasks of 64 characters each.
RECORD_FIELDS = {'project_id', 'revision', 'items'}
ITEM_FIELDS = {'id', 'created_at', 'spec_sha256', 'status', 'checks', 'note'}
CHECK_FIELDS = {'id', 'label', 'status', 'evidence'}
OVERALL_PRIORITY = (('fail', 'blocked'), ('warn', 'attention'), ('pending', 'pending'))
SNAPSHOT_ID = re.compile(r'[0-9a-f]{32}')


def _identity(value):
    identifier = value['project_id']
    if (not isinstance(identifier, str) or len(identifier) > 80 or not PROJECT_ID.fullmatch(identifier)
            or not _valid_digest(value['spec_sha256'])):
        raise ValueError('Invalid project or specification identity')


def validate_checks(status, checks):
    """Require one result per supervisor check and a consistent overall status."""
    if not isinstance(checks, list) or len(checks) != len(_LABELS):
        raise ValueError('Expected all supervisor checks')
    seen, statuses = set(), set()
    for check in checks:
        _fields(check, CHECK_FIELDS, 'supervisor check')
        key = check['id']
        if (not isinstance(key, str) or key not in _LABELS or key in seen
                or check['label'] != _LABELS[key]):
            raise ValueError('Invalid or duplicate supervisor check identity')
        if check['status'] not in ('pass', 'pending', 'warn', 'fail'):
            raise ValueError('Invalid supervisor check status')
        _text(check['evidence'], MAX_EVIDENCE, 'Check evidence')
        seen.add(key)
        statuses.add(check['status'])
    overall = next((result for state, result in OVERALL_PRIORITY if state in statuses), 'pass')
    if status != overall:
        raise ValueError('Supervisor status disagrees with checks')


def validate_audit(audit):
    """Validate the identity and observed check results of a live supervisor audit."""
    _fields(audit, {'project_id', 'spec_sha256', 'status', 'checks', 'recommendations'}, 'supervisor audit')
    _identity(audit)
    if not isinstance(audit['recommendations'], list):
        raise ValueError('Invalid supervisor recommendations')
    validate_checks(audit['status'], audit['checks'])


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 32:
        raise ValueError('Invalid snapshot timestamp')
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo != timezone.utc or timestamp.isoformat() != value:
        raise ValueError('Invalid snapshot timestamp')
    return timestamp


def validate_history(history):
    """Validate a projected history, including snapshots of earlier specifications."""
    _fields(history, RECORD_FIELDS | {'spec_sha256'}, 'evidence history')
    _identity(history)
    items = history['items']
    if (not isinstance(items, list) or len(items) > MAX_ITEMS
            or type(history['revision']) is not int or history['revision'] != len(items)):
        raise ValueError('Invalid evidence history length or revision')
    seen = set()
    previous = None
    for item in items:
        _fields(item, ITEM_FIELDS, 'evidence snapshot')
        identifier = item['id']
        if (not isinstance(identifier, str) or not SNAPSHOT_ID.fullmatch(identifier)
                or identifier in seen or not _valid_digest(item['spec_sha256'])):
            raise ValueError('Invalid or duplicate snapshot identity')
        seen.add(identifier)
        created = _timestamp(item['created_at'])
        if previous is not None and created > previous:
            raise ValueError('Evidence snapshots must be newest first')
        previous = created
        _text(item['note'], MAX_NOTE, 'Capture note')
        validate_checks(item['status'], item['checks'])


def _read_state(directory, project_id):
    meta = _read_json(directory, 'project.json')
    if (not isinstance(meta, dict) or meta.get('id') != project_id
            or not isinstance(meta.get('kind'), str) or meta['kind'] not in TEMPLATES):
        raise ValueError('Invalid project metadata')
    spec = _read_json(directory, 'spec.json')
    if not isinstance(spec, dict):
        raise ValueError('Invalid project specification')
    digest = spec_digest(spec)
    try:
        record = _read_json(directory, REGISTRY)
    except FileNotFoundError:
        return dict(project_id=project_id, spec_sha256=digest, revision=0, items=[])
    _fields(record, RECORD_FIELDS, 'stored evidence history')
    if record['project_id'] != project_id or not record['items']:
        raise ValueError('Invalid stored evidence history')
    history = {**record, 'spec_sha256': digest}
    validate_history(history)
    return history


def _write(directory, history):
    record = {key: history[key] for key in ('project_id', 'revision', 'items')}
    raw = (json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('Evidence history exceeds the storage limit')
    name = f'.evidence-history-{secrets.token_hex(16)}.tmp'
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, REGISTRY, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(name, dir_fd=directory)
        except FileNotFoundError:
            pass


class EvidenceHistory:
    def __init__(self, projects):
        self.projects = projects

    def get(self, project_id):
        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH) as directory:
            return _read_state(directory, project_id)

    def capture(self, project_id, data, audit, *, assert_snapshot=None):
        _fields(data, {'expected_revision', 'spec_sha256', 'note'}, 'evidence capture')
        if type(data['expected_revision']) is not int or data['expected_revision'] < 0:
            raise ValueError('expected_revision must be a nonnegative integer')
        if not _valid_digest(data['spec_sha256']):
            raise ValueError('spec_sha256 must be a lowercase SHA-256 digest')
        _text(data['note'], MAX_NOTE, 'Capture note')
        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_EX) as directory:
            history = _read_state(directory, project_id)
            if data['expected_revision'] != history['revision']:
                raise FileExistsError('Evidence history revision changed. Reload the history.')
            validate_audit(audit)
            if audit['project_id'] != project_id:
                raise ValueError('Supervisor audit belongs to another project')
            digest = history['spec_sha256']
            if data['spec_sha256'] != digest or audit['spec_sha256'] != digest:
                raise FileExistsError('Project specification changed. Reload the audit and history.')
            if assert_snapshot is not None:
                assert_snapshot(directory)
            items = history['items']
            if len(items) >= MAX_ITEMS:
                raise ValueError(f'A project may contain at most {MAX_ITEMS} evidence snapshots')
            identifier = secrets.token_hex(16)
            if any(item['id'] == identifier for item in items):
                raise FileExistsError('Snapshot ID collision. Retry the request.')
            created = datetime.now(timezone.utc)
            if items:
                created = max(created, _timestamp(items[0]['created_at']))
            items.insert(0, dict(id=identifier, created_at=created.isoformat(), spec_sha256=digest,
                                 status=audit['status'], checks=[dict(row) for row in audit['checks']],
                                 note=data['note']))
            history['revision'] += 1
            _write(directory, history)
            return history
