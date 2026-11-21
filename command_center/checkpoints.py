"""Durable, spec-bound progress checkpoints for manually reported active work."""
import errno
import fcntl
import json
import os
import re
import secrets
import stat
from contextlib import contextmanager
from datetime import datetime, timezone

from .projects import ProjectStore, TEMPLATES
from .provenance import spec_digest


TARGET_SECONDS = 18_000
CHECKPOINT = 'checkpoint.json'
LIST_FIELDS = ('completed_work', 'verification_evidence', 'remaining_work')
WORK_FIELDS = {'spec_sha256', 'elapsed_seconds', 'status', 'next_action', *LIST_FIELDS}
RECORD_FIELDS = WORK_FIELDS | {'project_id', 'revision', 'updated_at'}
REQUEST_FIELDS = WORK_FIELDS | {'expected_revision'}
OPTIONAL_FIELDS = {'reset_for_spec_change', 'start_new_run'}
STATUSES = ('in_progress', 'paused', 'completed', 'blocked')
MAX_ENTRIES = 32
MAX_TEXT = 1024
MAX_FILE_BYTES = 2 * 1024 * 1024


@contextmanager
def _locked_directory(path, lock_mode):
    # Pin each directory by descriptor so a renamed parent or a substituted
    # symlink cannot redirect later reads, staging, replacement or cleanup.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(path.anchor, flags)
    try:
        for component in path.parts[1:]:
            try:
                child = os.open(component, flags, dir_fd=directory)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise ValueError('Invalid checkpoint storage directory') from exc
                raise
            os.close(directory)
            directory = child
        fcntl.flock(directory, lock_mode)
        yield directory
    finally:
        os.close(directory)


def _read_json(directory, name):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError(f'{name} must not be a symbolic link') from exc
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f'{name} must be a regular file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            if name == CHECKPOINT:
                raw = stream.read(MAX_FILE_BYTES + 1)
                if len(raw) > MAX_FILE_BYTES:
                    raise ValueError('Checkpoint is too large')
            else:
                raw = stream.read()
        return json.loads(raw.decode('utf-8'))
    except RecursionError as exc:
        raise ValueError(f'Invalid JSON in {name}') from exc
    finally:
        os.close(fd)


def _write_record(directory, record):
    temporary = f'.checkpoint-{secrets.token_hex(16)}.tmp'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, CHECKPOINT, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def _text(value, field, allow_empty=False):
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        raise ValueError(f'{field} must be a string of at most {MAX_TEXT} characters')
    if not value.strip() and not (allow_empty and value == ''):
        raise ValueError(f'{field} must contain nonblank text')
    value.encode('utf-8')  # Reject unpaired surrogate code points before staging.
    return value


def _validate_work(data):
    digest = data['spec_sha256']
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('spec_sha256 must be a lowercase SHA-256 digest')
    elapsed = data['elapsed_seconds']
    if type(elapsed) is not int or not 0 <= elapsed <= TARGET_SECONDS:
        raise ValueError(f'elapsed_seconds must be an integer from 0 to {TARGET_SECONDS}')
    status = data['status']
    if status not in STATUSES:
        raise ValueError('Unknown checkpoint status')
    work = {'spec_sha256': digest, 'elapsed_seconds': elapsed, 'status': status,
            'next_action': _text(data['next_action'], 'next_action', allow_empty=status == 'completed')}
    for field in LIST_FIELDS:
        entries = data[field]
        if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
            raise ValueError(f'{field} must be a list of at most {MAX_ENTRIES} entries')
        work[field] = [_text(entry, field) for entry in entries]
    return work


def _read_state(directory, project_id):
    metadata = _read_json(directory, 'project.json')
    if (not isinstance(metadata, dict) or metadata.get('id') != project_id
            or not isinstance(metadata.get('kind'), str) or metadata['kind'] not in TEMPLATES):
        raise ValueError('Invalid project metadata')
    digest = spec_digest(_read_json(directory, 'spec.json'))
    try:
        record = _read_json(directory, CHECKPOINT)
    except FileNotFoundError:
        return digest, None
    if (not isinstance(record, dict) or set(record) != RECORD_FIELDS
            or record['project_id'] != project_id or type(record['revision']) is not int
            or record['revision'] < 1 or not isinstance(record['updated_at'], str)):
        raise ValueError('Invalid stored checkpoint')
    if datetime.fromisoformat(record['updated_at']).utcoffset() is None:
        raise ValueError('Checkpoint timestamp requires a timezone')
    _validate_work(record)
    return digest, record


def _projection(project_id, digest, record):
    state = 'empty'
    remaining = TARGET_SECONDS
    if record is not None:
        state = 'current' if record['spec_sha256'] == digest else 'stale'
        remaining = TARGET_SECONDS - record['elapsed_seconds'] if state == 'current' else None
    return {'project_id': project_id, 'spec_sha256': digest, 'state': state,
            'revision': record['revision'] if record else 0, 'checkpoint': record,
            'target_seconds': TARGET_SECONDS, 'remaining_seconds': remaining}


class CheckpointStore:
    def __init__(self, projects: ProjectStore):
        self.projects = projects

    def get(self, project_id):
        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH) as directory:
            digest, record = _read_state(directory, project_id)
            return _projection(project_id, digest, record)

    def save(self, project_id, data):
        if not isinstance(data, dict) or set(data) - OPTIONAL_FIELDS != REQUEST_FIELDS:
            raise ValueError('Invalid checkpoint fields')
        expected = data['expected_revision']
        if type(expected) is not int or expected < 0:
            raise ValueError('expected_revision must be a nonnegative integer')
        reset = data.get('reset_for_spec_change', False)
        new_run = data.get('start_new_run', False)
        if type(reset) is not bool or type(new_run) is not bool:
            raise ValueError('reset_for_spec_change and start_new_run must be booleans')
        if reset and new_run:
            raise ValueError('Choose one of reset_for_spec_change and start_new_run')
        work = _validate_work(data)
        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_EX) as directory:
            digest, previous = _read_state(directory, project_id)
            revision = previous['revision'] if previous else 0
            if expected != revision:
                raise FileExistsError('Checkpoint revision changed. Reload the current checkpoint.')
            if digest != work['spec_sha256']:
                raise FileExistsError('Project specification changed. Reload the project.')
            stale = previous is not None and previous['spec_sha256'] != digest
            if stale and not reset:
                raise FileExistsError('The saved checkpoint belongs to an older specification. Reset explicitly.')
            if reset and (not stale or work['elapsed_seconds'] != 0):
                raise ValueError('A reset requires a changed specification and zero elapsed seconds')
            if new_run and (not previous or previous['status'] != 'completed' or work['elapsed_seconds'] != 0):
                raise ValueError('A new run requires a completed checkpoint and zero elapsed seconds')
            if previous and not (reset or new_run) and work['elapsed_seconds'] < previous['elapsed_seconds']:
                raise ValueError('Elapsed seconds cannot decrease for the same specification')
            record = {'project_id': project_id, 'revision': revision + 1, **work,
                      'updated_at': datetime.now(timezone.utc).isoformat()}
            _write_record(directory, record)
            return _projection(project_id, digest, record)
