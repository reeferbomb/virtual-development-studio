"""Private local history of Academy submissions, deterministic checks and declared reviews."""
import errno
import fcntl
import json
import os
import re
import secrets
import stat
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from . import training_lab
from .checkpoints import _locked_directory
from .defect_store import MAX_NOTE, _fields, _text
from .projects import _safe_path
from .provenance import spec_digest
from .scheduler import _ROLES
from .task_store import JOB_ID, _valid_digest


REGISTRY = 'training-records.json'
# Keep room for the expanded role/exercise matrix alongside historical reviews.
# The independent file-size cap still bounds total persisted data.
MAX_RECORDS = 200
MAX_FILE_BYTES = 32 * 1024 * 1024
VERSION = 1
RECORD_FIELDS = {'id', 'exercise_id', 'role', 'created_at', 'reference', 'submission', 'report', 'review'}
REVIEW_FIELDS = {'reviewer_role', 'decision', 'note', 'reviewed_at'}
REPORT_FIELDS = {'version', 'lab_sha256', 'exercise_id', 'submission_sha256', 'status', 'summary',
                 'checks', 'note', 'assessment_sha256'}
NAME = re.compile(r'[a-z][a-z0-9_-]{0,79}')
NOTE = ('Roles are declared locally. A review records a judgment about this submission and its '
        'measured practice checks. It does not authenticate a person or certify competency or release readiness.')


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 32:
        raise ValueError('Invalid Academy timestamp')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo != timezone.utc or parsed.isoformat() != value:
        raise ValueError('Expected an ISO UTC Academy timestamp')
    return parsed


def _identifier(value):
    if not isinstance(value, str) or not JOB_ID.fullmatch(value):
        raise ValueError('Expected a 32-hex training record ID')


def _validate_review(review, item):
    _fields(review, REVIEW_FIELDS, 'training review')
    role = review['reviewer_role']
    if not isinstance(role, str) or (role != 'lead' and role not in _ROLES) or role == item['role']:
        raise ValueError('Choose a different specialist role or lead to review the submission')
    if review['decision'] not in ('accepted', 'rejected'):
        raise ValueError('Review decision must be accepted or rejected')
    if review['decision'] == 'accepted' and (item['reference'] or item['report']['status'] != 'pass'):
        raise ValueError('Only a passing submission that differs from the reference may be accepted')
    _text(review['note'], MAX_NOTE, 'Review note')
    if _timestamp(review['reviewed_at']) < _timestamp(item['created_at']):
        raise ValueError('Review predates training record')


def _validate_report(item):
    """Check the saved report's own evidence, even if its old evaluator is unavailable."""
    report = item['report']
    _fields(report, REPORT_FIELDS, 'stored training report')
    if (type(report['version']) is not int or report['version'] < 1
            or not _valid_digest(report['lab_sha256']) or report['exercise_id'] != item['exercise_id']
            or report['submission_sha256'] != spec_digest(item['submission'])
            or report['assessment_sha256'] != spec_digest({k: v for k, v in report.items()
                                                         if k != 'assessment_sha256'})):
        raise ValueError('Invalid stored training report identity')
    _text(report['note'], 2000, 'Training report note')
    checks = report['checks']
    if not isinstance(checks, list) or not 1 <= len(checks) <= 100:
        raise ValueError('Invalid saved practice checks')
    seen = set()
    passed = 0
    for check in checks:
        _fields(check, {'id', 'status', 'label', 'detail'}, 'stored practice check')
        if (not isinstance(check['id'], str) or not NAME.fullmatch(check['id'])
                or check['id'] in seen or check['status'] not in ('pass', 'fail')):
            raise ValueError('Invalid saved practice check')
        seen.add(check['id'])
        _text(check['label'], 2000, 'Practice check label')
        _text(check['detail'], 2000, 'Practice check detail')
        passed += check['status'] == 'pass'
    failed = len(checks) - passed
    summary = report['summary']
    _fields(summary, {'pass', 'fail'}, 'stored practice summary')
    if (type(summary['pass']) is not int or type(summary['fail']) is not int
            or summary != {'pass': passed, 'fail': failed} or report['status'] != ('fail' if failed else 'pass')):
        raise ValueError('Stored training report disagrees with its checks')


def _exercise(exercises, exercise_id, role):
    if not isinstance(exercise_id, str) or exercise_id not in exercises:
        raise ValueError('Unknown training exercise')
    exercise = exercises[exercise_id]
    if role not in exercise['roles']:
        raise ValueError('The selected role is not assigned to this exercise')
    return exercise


def _validate_records(state, digest, exercises):
    records = state['records']
    if (not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS
            or type(state['revision']) is not int):
        raise ValueError('Invalid stored training history length or revision')
    reviewed, previous, seen = 0, None, set()
    for item in records:
        _fields(item, RECORD_FIELDS, 'stored training record')
        _identifier(item['id'])
        created = _timestamp(item['created_at'])
        if (item['id'] in seen or (previous is not None and created > previous)
                or not isinstance(item['exercise_id'], str) or not NAME.fullmatch(item['exercise_id'])
                or not isinstance(item['role'], str) or item['role'] not in _ROLES
                or type(item['reference']) is not bool):
            raise ValueError('Invalid stored training record identity or order')
        seen.add(item['id'])
        previous = created
        training_lab._validate_data(item['submission'])
        _validate_report(item)
        report = item['report']
        if report['lab_sha256'] == digest:
            exercise = _exercise(exercises, item['exercise_id'], item['role'])
            expected = training_lab.assess_submission(item['exercise_id'], item['submission'])
            if (expected['assessment_sha256'] != report['assessment_sha256']
                    or item['reference'] != (expected['submission_sha256'] == spec_digest(exercise['example']))):
                raise ValueError('Stored training assessment differs from the current evaluator')
        if item['review'] is not None:
            _validate_review(item['review'], item)
            reviewed += 1
    if state['revision'] != len(records) + reviewed:
        raise ValueError('Training revision disagrees with records and reviews')


def _read_state(directory, digest, exercises):
    try:
        fd = os.open(REGISTRY, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return {'revision': 0, 'records': []}
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError('Training records must not be a symbolic link') from exc
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise ValueError('Training history must be a regular file within the storage limit')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('Training history exceeds the storage limit')
    try:
        saved = json.loads(raw.decode('utf-8'), object_pairs_hook=training_lab.reject_duplicate_keys)
        _fields(saved, {'version', 'revision', 'records', 'ledger_sha256'}, 'stored training ledger')
        checksum = saved.pop('ledger_sha256')
        if type(saved['version']) is not int or saved['version'] != VERSION or checksum != spec_digest(saved):
            raise ValueError('Stored training ledger version or checksum mismatch')
        _validate_records(saved, digest, exercises)
    except RecursionError as exc:
        raise ValueError('Stored training history exceeds structural limits') from exc
    return {'revision': saved['revision'], 'records': saved['records']}


def _save(directory, state):
    payload = {'version': VERSION, **state}
    payload['ledger_sha256'] = spec_digest(payload)
    raw = (json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('Training history exceeds the storage limit')
    stage = f'.training-records-{secrets.token_hex(16)}.tmp'
    fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, REGISTRY, src_dir_fd=directory, dst_dir_fd=directory)
        # After replacement an fsync error leaves the new revision visible. Re-read before retrying.
        os.fsync(directory)
    finally:
        try:
            os.unlink(stage, dir_fd=directory)
        except FileNotFoundError:
            pass


def _record(records, exercises, digest, action):
    fields = {'op', 'exercise_id', 'role', 'submission'}
    if 'expected_assessment_sha256' in action:
        fields.add('expected_assessment_sha256')
        if not _valid_digest(action['expected_assessment_sha256']):
            raise ValueError('expected_assessment_sha256 must be a lowercase SHA-256 digest')
    _fields(action, fields, 'training record action')
    if len(records) >= MAX_RECORDS:
        raise ValueError(f'At most {MAX_RECORDS} training records can be saved')
    exercise = _exercise(exercises, action['exercise_id'], action['role'])
    training_lab._validate_data(action['submission'])
    submission = deepcopy(action['submission'])
    report = training_lab.assess_submission(exercise['id'], submission)
    if report['lab_sha256'] != digest:
        raise FileExistsError('The training catalog changed during assessment. Reload and try again.')
    if ('expected_assessment_sha256' in action
            and action['expected_assessment_sha256'] != report['assessment_sha256']):
        raise FileExistsError('The assessment changed. Reassess the submission before recording it.')
    identifier = secrets.token_hex(16)
    if any(item['id'] == identifier for item in records):
        raise FileExistsError('Training record ID collision. Retry the request.')
    created = datetime.now(timezone.utc)
    if records:
        created = max(created, _timestamp(records[0]['created_at']))
    records.insert(0, dict(id=identifier, exercise_id=exercise['id'], role=action['role'],
                           created_at=created.isoformat(), submission=submission, report=report,
                           reference=report['submission_sha256'] == spec_digest(exercise['example']), review=None))


def _review(records, digest, action):
    _fields(action, {'op', 'record_id', 'reviewer_role', 'decision', 'note'}, 'training review action')
    _identifier(action['record_id'])
    item = next((row for row in records if row['id'] == action['record_id']), None)
    if item is None:
        raise ValueError('Unknown training record ID')
    if item['report']['lab_sha256'] != digest:
        raise FileExistsError('Historical training records are read-only for the current catalog.')
    if item['review'] is not None:
        raise ValueError('This training record has already been reviewed')
    reviewed = max(datetime.now(timezone.utc), _timestamp(item['created_at']))
    review = {key: action[key] for key in ('reviewer_role', 'decision', 'note')}
    review['reviewed_at'] = reviewed.isoformat()
    _validate_review(review, item)
    item['review'] = review


def _catalog():
    catalog = training_lab.lab_catalog()
    return catalog['lab_sha256'], {row['id']: row for row in catalog['exercises']}


def _snapshot(state, digest):
    return dict(revision=state['revision'], lab_sha256=digest, note=NOTE,
                records=[dict(item, current=item['report']['lab_sha256'] == digest) for item in state['records']])


class TrainingRecordStore:
    def __init__(self, workspace):
        supplied = _safe_path(Path(workspace).absolute())
        self.workspace = Path(os.path.abspath(supplied))
        if self.workspace.is_relative_to(Path(__file__).resolve().parents[1]):
            raise ValueError('Choose a private Academy workspace outside the public checkout')

    def read(self):
        digest, exercises = _catalog()
        try:
            with _locked_directory(self.workspace, fcntl.LOCK_SH) as directory:
                state = _read_state(directory, digest, exercises)
        except FileNotFoundError:
            state = {'revision': 0, 'records': []}
        return _snapshot(state, digest)

    def apply(self, data):
        _fields(data, {'expected_revision', 'action'}, 'training request')
        expected = data['expected_revision']
        if type(expected) is not int or expected < 0:
            raise ValueError('expected_revision must be a nonnegative integer')
        action = data['action']
        if not isinstance(action, dict) or action.get('op') not in ('record', 'review'):
            raise ValueError('Unknown training operation')
        with _locked_directory(self.workspace, fcntl.LOCK_EX) as directory:
            digest, exercises = _catalog()
            state = _read_state(directory, digest, exercises)
            if expected != state['revision']:
                raise FileExistsError('Training revision changed. Reload the training records.')
            if action['op'] == 'record':
                _record(state['records'], exercises, digest, action)
            else:
                _review(state['records'], digest, action)
            state['revision'] += 1
            _save(directory, state)
            return _snapshot(state, digest)
