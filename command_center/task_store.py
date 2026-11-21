"""Persist a manually operated task board against an exact project specification."""
import errno
import fcntl
import json
import os
import re
import secrets
import stat
from copy import deepcopy

from . import scheduler
from .checkpoints import _locked_directory
from .projects import ProjectStore, TEMPLATES
from .provenance import spec_digest


BOARD = 'task-board.json'
MAX_FILE_BYTES = 8 * 1024 * 1024
RECORD_FIELDS = {'project_id', 'spec_sha256', 'revision', 'tasks'}
DIGEST = re.compile(r'[0-9a-f]{64}')
JOB_ID = re.compile(r'[0-9a-f]{32}')


def _read_json(directory, name):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(name, flags, dir_fd=directory)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError(f'{name} must not be a symbolic link') from exc
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f'{name} must be a regular file')
        if info.st_size > MAX_FILE_BYTES:
            raise ValueError(f'{name} exceeds the storage limit')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError(f'{name} exceeds the storage limit')
        return json.loads(raw.decode('utf-8'))
    except RecursionError as exc:
        raise ValueError(f'Invalid JSON in {name}') from exc
    finally:
        os.close(fd)


def _write_board(directory, record):
    raw = (json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('Task board exceeds the storage limit')
    stage = f'.task-board-{secrets.token_hex(16)}.tmp'
    fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, BOARD, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(stage, dir_fd=directory)
        except FileNotFoundError:
            pass


def _valid_digest(value):
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def _add_batch(tasks, action):
    if set(action) != {'op', 'tasks'} or not isinstance(action['tasks'], list) or not action['tasks']:
        raise ValueError('add_batch requires a nonempty tasks list')
    if len(tasks) + len(action['tasks']) > scheduler.MAX_TASKS:
        raise ValueError(f'Task board may contain at most {scheduler.MAX_TASKS} tasks')

    updated = tasks.copy()
    for definition in action['tasks']:
        scheduler._exact_fields(definition, scheduler._DEFINITION, 'new task')
        updated.append(dict(definition, status='pending', attempts=0, reason=None, job_id=None, evidence=[]))
    # Validate the complete graph so dependencies can appear later in the batch.
    scheduler.validate_tasks(updated)
    return deepcopy(updated)


def _read_state(directory, project_id):
    metadata = _read_json(directory, 'project.json')
    if (not isinstance(metadata, dict) or metadata.get('id') != project_id
            or not isinstance(metadata.get('kind'), str) or metadata['kind'] not in TEMPLATES):
        raise ValueError('Invalid project metadata')
    digest = spec_digest(_read_json(directory, 'spec.json'))
    try:
        record = _read_json(directory, BOARD)
    except FileNotFoundError:
        return digest, None
    if (not isinstance(record, dict) or set(record) != RECORD_FIELDS
            or record['project_id'] != project_id or not _valid_digest(record['spec_sha256'])
            or type(record['revision']) is not int or record['revision'] < 1):
        raise ValueError('Invalid stored task board')
    scheduler.validate_tasks(record['tasks'])
    return digest, record


def _projection(project_id, digest, record):
    tasks = record['tasks'] if record else []
    plan = scheduler.schedule(tasks)
    board_digest = record['spec_sha256'] if record else None
    state = 'empty'
    if record:
        state = 'current' if board_digest == digest else 'stale'
        if state == 'stale':
            summary = plan['summary']
            summary['waiting'] += summary['ready']
            summary['ready'] = 0
            plan['ready_task_ids'] = []
            plan['assignments'] = []
    return {'project_id': project_id, 'spec_sha256': digest, 'board_spec_sha256': board_digest,
            'state': state, 'revision': record['revision'] if record else 0, 'tasks': tasks, **plan}


class TaskStore:
    def __init__(self, projects: ProjectStore, job_lookup=None):
        self.projects = projects
        self.job_lookup = job_lookup

    def get(self, project_id):
        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH) as directory:
            digest, record = _read_state(directory, project_id)
            return _projection(project_id, digest, record)

    def _build_verified(self, project_id, digest, tasks, action):
        if action.get('op') != 'complete':
            return False
        if not any(task['id'] == action.get('task_id') and task['gate'] == 'build' for task in tasks):
            return False
        job_id = action.get('job_id')
        if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id) or self.job_lookup is None:
            return False
        try:
            job = self.job_lookup(job_id)
        except (KeyError, FileNotFoundError):
            return False
        return (isinstance(job, dict) and job.get('id') == job_id
                and job.get('project_id') == project_id and job.get('spec_sha256') == digest
                and job.get('status') == 'passed' and job.get('verified') is True)

    def apply(self, project_id, data, *, assert_snapshot=None):
        if not isinstance(data, dict) or set(data) != {'expected_revision', 'spec_sha256', 'action'}:
            raise ValueError('Expected expected_revision, spec_sha256 and action')
        expected = data['expected_revision']
        if type(expected) is not int or expected < 0:
            raise ValueError('expected_revision must be a nonnegative integer')
        if not _valid_digest(data['spec_sha256']):
            raise ValueError('spec_sha256 must be a lowercase SHA-256 digest')
        action = data['action']
        if not isinstance(action, dict):
            raise ValueError('action must be an object')
        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_EX) as directory:
            digest, previous = _read_state(directory, project_id)
            revision = previous['revision'] if previous else 0
            if expected != revision:
                raise FileExistsError('Task board revision changed. Reload the task board.')
            if data['spec_sha256'] != digest:
                raise FileExistsError('Project specification changed. Reload the task board.')
            if assert_snapshot is not None:
                assert_snapshot(directory)
            stale = previous is not None and previous['spec_sha256'] != digest
            if action.get('op') == 'reset':
                if action != {'op': 'reset'} or not stale:
                    raise ValueError('Reset requires an older specification and only the reset operation')
                tasks = []
            else:
                if stale:
                    raise FileExistsError('The task board uses an older specification. Reset explicitly.')
                tasks = previous['tasks'] if previous else []
                if action.get('op') == 'add_batch':
                    tasks = _add_batch(tasks, action)
                else:
                    verified = self._build_verified(project_id, digest, tasks, action)
                    tasks = scheduler.apply_action(tasks, action, build_verified=verified)
            record = {'project_id': project_id, 'spec_sha256': digest,
                      'revision': revision + 1, 'tasks': tasks}
            result = _projection(project_id, digest, record)
            _write_board(directory, record)
            return result
