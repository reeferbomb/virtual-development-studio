"""Persist specialist reports and explicit lead reviews against claimed work orders."""
import fcntl
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import PureWindowsPath

from . import scheduler, task_store
from .checkpoints import _locked_directory
from .defect_store import MAX_NOTE, _fields, _notes, _text
from .projects import PROJECT_ID, TEMPLATES
from .provenance import spec_digest
from .task_store import MAX_FILE_BYTES, _read_json, _valid_digest
from .work_orders import work_orders


REGISTRY = 'handoffs.json'
MAX_ITEMS = 100
REPORT_FIELDS = {'outcome', 'summary', 'evidence', 'changed_paths', 'next_action'}
ITEM_FIELDS = REPORT_FIELDS | {
    'id', 'order_id', 'task_id', 'attempt', 'role', 'board_revision', 'spec_sha256',
    'created_at', 'review', 'review_note', 'reviewed_at',
}
RECORD_FIELDS = {'project_id', 'revision', 'items'}
DECISIONS = ('accepted', 'rejected')


def _handoff_id(value):
    if not isinstance(value, str) or not task_store.JOB_ID.fullmatch(value):
        raise ValueError('handoff_id must be a lowercase 32-hex ID')


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 32:
        raise ValueError('Invalid handoff timestamp')
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo != timezone.utc or stamp.isoformat() != value:
        raise ValueError('Invalid handoff timestamp')
    return stamp


def _validate_report(report):
    if report['outcome'] not in ('completed', 'blocked', 'progress'):
        raise ValueError('outcome must be completed, blocked or progress')
    _text(report['summary'], MAX_NOTE, 'Summary')
    _text(report['next_action'], MAX_NOTE, 'Next action')
    _notes(report['evidence'], 8)
    paths = report['changed_paths']
    if not isinstance(paths, list) or len(paths) > 16:
        raise ValueError('changed_paths must contain at most 16 relative paths')
    for path in paths:
        _text(path, 256, 'Changed path')
        # Interpret either slash as a separator to reject traversal and rooted or
        # drive-relative names even when a report arrives from a different OS.
        parsed = PureWindowsPath(path)
        if not path.isprintable() or parsed.anchor or not parsed.parts or '..' in parsed.parts:
            raise ValueError('Changed paths must be safe relative paths')


def _validate_items(items, revision):
    if not isinstance(items, list) or len(items) > MAX_ITEMS or type(revision) is not int:
        raise ValueError('Invalid handoff registry length or revision')
    seen_ids = set()
    orders = {}
    reviewed = 0
    previous = None
    for item in items:
        _fields(item, ITEM_FIELDS, 'stored handoff')
        _handoff_id(item['id'])
        scheduler._task_id(item['task_id'])
        if (item['id'] in seen_ids or not _valid_digest(item['order_id'])
                or not _valid_digest(item['spec_sha256']) or not isinstance(item['role'], str)
                or item['role'] not in scheduler._ROLES or type(item['attempt']) is not int
                or type(item['board_revision']) is not int
                or not 1 <= item['attempt'] <= item['board_revision']):
            raise ValueError('Invalid stored handoff provenance')
        seen_ids.add(item['id'])
        identity = tuple(item[key] for key in ('spec_sha256', 'board_revision', 'task_id', 'attempt', 'role'))
        if orders.setdefault(item['order_id'], identity) != identity:
            raise ValueError('Handoffs disagree on work order provenance')
        _validate_report(item)
        created = _timestamp(item['created_at'])
        if previous is not None and previous < created:
            raise ValueError('Handoffs must be newest first')
        previous = created
        if item['review'] == 'pending':
            if item['review_note'] is not None or item['reviewed_at'] is not None:
                raise ValueError('Pending handoff contains review details')
        elif item['review'] in DECISIONS:
            _text(item['review_note'], MAX_NOTE, 'Review note')
            if _timestamp(item['reviewed_at']) < created:
                raise ValueError('Review predates handoff')
            reviewed += 1
        else:
            raise ValueError('Invalid handoff review')
    if revision != len(items) + reviewed:
        raise ValueError('Handoff revision disagrees with submissions and reviews')


def validate_record(record, project_id):
    """Validate the persisted registry, including all historical reports."""
    _fields(record, RECORD_FIELDS, 'stored handoff registry')
    if record['project_id'] != project_id or not record['items']:
        raise ValueError('Invalid stored handoff registry')
    _validate_items(record['items'], record['revision'])


def validate_history(history):
    """Validate a handoff projection, including the initial, empty state."""
    _fields(history, RECORD_FIELDS | {'spec_sha256'}, 'handoff history')
    identifier = history['project_id']
    if (not isinstance(identifier, str) or len(identifier) > 80 or not PROJECT_ID.fullmatch(identifier)
            or not _valid_digest(history['spec_sha256'])):
        raise ValueError('Invalid handoff project or specification identity')
    _validate_items(history['items'], history['revision'])


def _read_project(directory, project_id):
    metadata = _read_json(directory, 'project.json')
    if (not isinstance(metadata, dict) or metadata.get('id') != project_id
            or not isinstance(metadata.get('kind'), str) or metadata['kind'] not in TEMPLATES):
        raise ValueError('Invalid project metadata')
    spec = _read_json(directory, 'spec.json')
    if not isinstance(spec, dict):
        raise ValueError('Invalid project specification')
    return {**metadata, 'spec': spec}


def _read_record(directory, project_id):
    try:
        record = _read_json(directory, REGISTRY)
    except FileNotFoundError:
        return {'project_id': project_id, 'revision': 0, 'items': []}
    validate_record(record, project_id)
    return record


def _write(directory, record):
    raw = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('Handoff registry exceeds the storage limit')
    stage = f'.handoffs-{secrets.token_hex(16)}.tmp'
    fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, REGISTRY, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(stage, dir_fd=directory)
        except FileNotFoundError:
            pass


def _submit(directory, project, digest, items, action):
    _fields(action, REPORT_FIELDS | {'op', 'task_id', 'order_id'}, 'handoff submission')
    scheduler._task_id(action['task_id'])
    if not _valid_digest(action['order_id']):
        raise ValueError('order_id must be a lowercase SHA-256 digest')
    _validate_report(action)
    if len(items) >= MAX_ITEMS:
        raise ValueError(f'A project may contain at most {MAX_ITEMS} handoffs')
    board_digest, board_record = task_store._read_state(directory, project['id'])
    board = task_store._projection(project['id'], board_digest, board_record)
    orders = work_orders(project, board)['orders']
    order = next((item for item in orders if item['order_id'] == action['order_id']
                  and item['task_id'] == action['task_id']), None)
    if order is None:
        raise FileExistsError('Work order is no longer current. Reload the claimed work orders.')
    identifier = secrets.token_hex(16)
    if any(item['id'] == identifier for item in items):
        raise FileExistsError('Handoff ID collision. Retry the request.')
    created = datetime.now(timezone.utc)
    if items:
        created = max(created, _timestamp(items[0]['created_at']))
    items.insert(0, dict(id=identifier, order_id=order['order_id'], task_id=order['task_id'],
                         attempt=order['attempt'], role=order['role'], board_revision=board['revision'],
                         spec_sha256=digest, created_at=created.isoformat(), outcome=action['outcome'],
                         summary=action['summary'], evidence=list(action['evidence']),
                         changed_paths=list(action['changed_paths']), next_action=action['next_action'],
                         review='pending', review_note=None, reviewed_at=None))


def _review(items, digest, action):
    _fields(action, {'op', 'handoff_id', 'decision', 'note'}, 'handoff review')
    _handoff_id(action['handoff_id'])
    if action['decision'] not in DECISIONS:
        raise ValueError('Review decision must be accepted or rejected')
    _text(action['note'], MAX_NOTE, 'Review note')
    item = next((row for row in items if row['id'] == action['handoff_id']), None)
    if item is None:
        raise ValueError('Unknown handoff ID')
    if item['spec_sha256'] != digest:
        raise FileExistsError('Historical handoffs are read-only for the current specification.')
    if item['review'] != 'pending':
        raise ValueError('This handoff has already been reviewed')
    reviewed = max(datetime.now(timezone.utc), _timestamp(item['created_at']))
    item.update(review=action['decision'], review_note=action['note'], reviewed_at=reviewed.isoformat())


class HandoffStore:
    def __init__(self, projects):
        self.projects = projects

    def get(self, project_id):
        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH) as directory:
            project = _read_project(directory, project_id)
            return {**_read_record(directory, project_id), 'spec_sha256': spec_digest(project['spec'])}

    def apply(self, project_id, data):
        _fields(data, {'expected_revision', 'spec_sha256', 'action'}, 'handoff request')
        if type(data['expected_revision']) is not int or data['expected_revision'] < 0:
            raise ValueError('expected_revision must be a nonnegative integer')
        if not _valid_digest(data['spec_sha256']):
            raise ValueError('spec_sha256 must be a lowercase SHA-256 digest')
        action = data['action']
        if not isinstance(action, dict) or action.get('op') not in ('submit', 'review'):
            raise ValueError('Unknown handoff operation')
        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_EX) as directory:
            project = _read_project(directory, project_id)
            digest = spec_digest(project['spec'])
            record = _read_record(directory, project_id)
            if record['revision'] != data['expected_revision']:
                raise FileExistsError('Handoff revision changed. Reload the handoff history.')
            if data['spec_sha256'] != digest:
                raise FileExistsError('Project specification changed. Reload the handoff history.')
            if action['op'] == 'submit':
                _submit(directory, project, digest, record['items'], action)
            else:
                _review(record['items'], digest, action)
            record['revision'] += 1
            _write(directory, record)
            return {**record, 'spec_sha256': digest}
