"""Record operator-reported defects and their evidence against exact project specifications."""
import fcntl
import json
import os
import re
import secrets
from datetime import datetime, timezone

from .checkpoints import _locked_directory
from .projects import TEMPLATES
from .provenance import spec_digest
from .task_store import MAX_FILE_BYTES, _read_json, _valid_digest


REGISTRY = 'defects.json'
MAX_ITEMS = 100
MAX_TITLE = 160
MAX_DESCRIPTION = 2048
MAX_NOTE = 512
MAX_NOTES_PER_ACTION = 8
MAX_NOTES = 32
SEVERITIES = ('critical', 'high', 'medium', 'low')
ITEM_FIELDS = {'id', 'title', 'severity', 'description', 'status', 'spec_sha256',
               'created_at', 'updated_at', 'evidence'}
DEFECT_ID = re.compile(r'[0-9a-f]{32}')
INVALID_TEXT = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff]')


def _fields(value, expected, label):
    if not isinstance(value, dict) or value.keys() != expected:
        raise ValueError(f'Invalid {label} fields')


def _text(value, limit, label):
    if (not isinstance(value, str) or len(value) > limit or INVALID_TEXT.search(value)
            or not any(c.isprintable() and not c.isspace() for c in value)):
        raise ValueError(f'{label} requires nonblank text of at most {limit} characters')


def _notes(notes, limit):
    if not isinstance(notes, list) or not 1 <= len(notes) <= limit:
        raise ValueError(f'evidence must contain 1 to {limit} notes')
    for note in notes:
        _text(note, MAX_NOTE, 'Evidence')


def _details(item):
    _text(item['title'], MAX_TITLE, 'Title')
    _text(item['description'], MAX_DESCRIPTION, 'Description')
    if item['severity'] not in SEVERITIES:
        raise ValueError('severity must be critical, high, medium or low')


def _identifier(value):
    if not isinstance(value, str) or not DEFECT_ID.fullmatch(value):
        raise ValueError('defect_id must be a lowercase 32-hex ID')


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 32:
        raise ValueError('Invalid stored defect timestamp')
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo != timezone.utc or timestamp.isoformat() != value:
        raise ValueError('Invalid stored defect timestamp')
    return timestamp


def _note_limit(status):
    # Leave room for a resolution note on every open defect.
    return MAX_NOTES - 1 if status == 'open' else MAX_NOTES


def _read_state(directory, project_id):
    metadata = _read_json(directory, 'project.json')
    if (not isinstance(metadata, dict) or metadata.get('id') != project_id
            or not isinstance(metadata.get('kind'), str) or metadata['kind'] not in TEMPLATES):
        raise ValueError('Invalid project metadata')
    spec = _read_json(directory, 'spec.json')
    if not isinstance(spec, dict):
        raise ValueError('Invalid project specification')
    digest = spec_digest(spec)
    try:
        record = _read_json(directory, REGISTRY)
    except FileNotFoundError:
        return digest, {'project_id': project_id, 'revision': 0, 'items': []}

    _fields(record, {'project_id', 'revision', 'items'}, 'stored defect registry')
    items = record['items']
    if (record['project_id'] != project_id or type(record['revision']) is not int
            or not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS):
        raise ValueError('Invalid stored defect registry')
    identifiers = set()
    total_notes = 0
    minimum_revision = len(items)
    for item in items:
        _fields(item, ITEM_FIELDS, 'stored defect')
        _identifier(item['id'])
        if (item['id'] in identifiers or not _valid_digest(item['spec_sha256'])
                or item['status'] not in ('open', 'resolved')):
            raise ValueError('Invalid stored defect identity or status')
        identifiers.add(item['id'])
        _details(item)
        _notes(item['evidence'], _note_limit(item['status']))
        if _timestamp(item['updated_at']) < _timestamp(item['created_at']):
            raise ValueError('Invalid stored defect chronology')
        total_notes += len(item['evidence'])
        if item['status'] == 'resolved':
            if len(item['evidence']) < 2:
                raise ValueError('Resolved defect is missing evidence')
            minimum_revision += 1
    if not minimum_revision <= record['revision'] <= total_notes:
        raise ValueError('Invalid stored defect revision')
    return digest, record


def _projection(record, digest):
    summary = dict(current_open=0, current_resolved=0, historical_open=0, historical_resolved=0)
    for item in record['items']:
        scope = 'current' if item['spec_sha256'] == digest else 'historical'
        summary[f"{scope}_{item['status']}"] += 1
    return {**record, 'spec_sha256': digest, 'summary': summary}


def _write(directory, record):
    raw = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('Defect registry exceeds the storage limit')
    name = f'.defects-{secrets.token_hex(16)}.tmp'
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory)
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


def _add(items, digest, action):
    _fields(action, {'op', 'title', 'severity', 'description', 'evidence'}, 'add action')
    _details(action)
    _notes(action['evidence'], MAX_NOTES_PER_ACTION)
    if len(items) >= MAX_ITEMS:
        raise ValueError(f'A project may contain at most {MAX_ITEMS} defects')
    identifier = secrets.token_hex(16)
    if any(item['id'] == identifier for item in items):
        raise FileExistsError('Defect ID collision. Retry the request.')
    now = datetime.now(timezone.utc).isoformat()
    items.append({'id': identifier, 'spec_sha256': digest, 'status': 'open',
                  'title': action['title'], 'severity': action['severity'],
                  'description': action['description'], 'evidence': list(action['evidence']),
                  'created_at': now, 'updated_at': now})


def _transition(items, digest, action):
    _fields(action, {'op', 'defect_id', 'evidence'}, 'defect transition')
    _identifier(action['defect_id'])
    _notes(action['evidence'], MAX_NOTES_PER_ACTION)
    item = next((row for row in items if row['id'] == action['defect_id']), None)
    if item is None:
        raise ValueError('Unknown defect ID')
    if item['spec_sha256'] != digest:
        raise FileExistsError('Historical defects are read-only for the current specification.')
    status = 'resolved' if action['op'] == 'resolve' else 'open'
    if item['status'] == status:
        raise ValueError(f'Defect is already {status}')
    if len(item['evidence']) + len(action['evidence']) > _note_limit(status):
        raise ValueError(f'A {status} defect may contain at most {_note_limit(status)} evidence notes')
    item['evidence'].extend(action['evidence'])
    item['status'] = status
    item['updated_at'] = max(datetime.now(timezone.utc), _timestamp(item['updated_at'])).isoformat()


class DefectStore:
    def __init__(self, projects):
        self.projects = projects

    def get(self, project_id):
        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH) as directory:
            digest, record = _read_state(directory, project_id)
            return _projection(record, digest)

    def apply(self, project_id, data):
        _fields(data, {'expected_revision', 'spec_sha256', 'action'}, 'defect request')
        if type(data['expected_revision']) is not int or data['expected_revision'] < 0:
            raise ValueError('expected_revision must be a nonnegative integer')
        if not _valid_digest(data['spec_sha256']):
            raise ValueError('spec_sha256 must be a lowercase SHA-256 digest')
        action = data['action']
        if not isinstance(action, dict) or action.get('op') not in ('add', 'resolve', 'reopen'):
            raise ValueError('Unknown defect operation')
        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_EX) as directory:
            digest, record = _read_state(directory, project_id)
            if record['revision'] != data['expected_revision']:
                raise FileExistsError('Defect revision changed. Reload the defect registry.')
            if data['spec_sha256'] != digest:
                raise FileExistsError('Project specification changed. Reload the defect registry.')
            if action['op'] == 'add':
                _add(record['items'], digest, action)
            else:
                _transition(record['items'], digest, action)
            record['revision'] += 1
            _write(directory, record)
            return _projection(record, digest)
