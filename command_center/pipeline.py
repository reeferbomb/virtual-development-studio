"""Serialized, local builder jobs with durable snapshots and command evidence."""

import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .checkpoints import _locked_directory
from .projects import PROJECT_ID, validate_spec
from .provenance import spec_digest


_BUILDERS = {'assets': 'factory', 'world': 'world', 'gameplay': 'gameplay',
             'multiplayer': 'multiplayer', 'cinematic': 'cinematic', 'simulation': 'simulation',
             'openworld': 'openworld', 'unified': 'unified', 'living': 'living', 'city': 'city',
             'vertical': 'vertical', 'advanced': 'advanced', 'frontline': 'frontline'}
_FIXTURE_SCENARIOS = ('openworld', 'unified', 'living', 'city', 'vertical', 'advanced', 'frontline')
STATUSES = ('queued', 'running', 'passed', 'failed', 'canceled')
TIMEOUT_SECONDS = 900
LOG_TAIL_BYTES = 64 * 1024


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Expected regular file: {path.name}')
    return json.loads(path.read_text(encoding='utf-8'))


def _write(path, data):
    temp = path.with_name(f'.{uuid.uuid4().hex}.tmp')
    try:
        with temp.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


def _priority(value):
    if type(value) is not int or not 1 <= value <= 5:
        raise ValueError('Priority must be an integer from 1 through 5')
    return value


def _dispatch_order(state):
    # Legacy jobs have no sequence and precede new submissions at the same priority.
    return (-state['priority'], state.get('queue_sequence', 0),
            state.get('created_at', ''), state['id'])


class Pipeline:
    def __init__(self, root: Path, workspace: Path):
        self.root = Path(root).resolve()
        self.workspace = Path(workspace).resolve()
        self.jobs = self.workspace / 'jobs'
        self.jobs.mkdir(exist_ok=True, parents=True)
        if self.jobs.is_symlink():
            raise ValueError('Jobs directory may not be a symbolic link')
        self.execution = self.jobs / '.execution'
        self.execution.mkdir(mode=0o700, exist_ok=True)
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='studio-build')
        self._draining = False
        with _locked_directory(self.jobs, fcntl.LOCK_EX):
            states = self.list()
            self._recover_running(states)
            if any(state['status'] == 'queued' for state in states):
                self._wake_locked()

    def _recover_running(self, states):
        for state in states:
            if state['status'] != 'running':
                continue
            directory = self._directory(state['id'])
            try:
                with _locked_directory(directory, fcntl.LOCK_EX | fcntl.LOCK_NB):
                    # Completion can race the initial directory scan. Refresh the caller's
                    # view after acquiring the lease, before changing any published result.
                    current = self.get(state['id'])
                    state.clear()
                    state.update(current)
                    if state['status'] != 'running':
                        continue
                    state.update(status='failed', verified=False, finished_at=_now(), output=None,
                                 error='Studio stopped before this job completed')
                    _write(directory / 'job.json', state)
            except BlockingIOError:
                continue

    def _directory(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r'[0-9a-f]{32}', job_id):
            raise ValueError('Invalid job ID')
        directory = self.jobs / job_id
        if directory.resolve() != directory or not directory.is_dir():
            raise KeyError(job_id)
        return directory

    def get(self, job_id):
        state = _read(self._directory(job_id) / 'job.json')
        if not isinstance(state, dict) or state.get('id') != job_id or state.get('status') not in STATUSES:
            raise ValueError('Invalid job record')
        state['priority'] = _priority(state.get('priority', 3))
        seq = state.get('queue_sequence', 0)
        if type(seq) is not int or seq < 0 or not isinstance(state.get('created_at', ''), str):
            raise ValueError('Invalid job order')
        return state

    def list(self):
        states = []
        for path in self.jobs.iterdir():
            if not re.fullmatch(r'[0-9a-f]{32}', path.name) or path.is_symlink() or not (path / 'job.json').is_file():
                continue
            try:
                state = self.get(path.name)
            except (ValueError, RecursionError) as exc:
                # Expose the unreadable record without replacing evidence or dispatching it.
                state = dict(id=path.name, status='failed', error=str(exc), priority=3,
                             verified=False, project_id=None, kind=None, created_at='',
                             started_at=None, finished_at=None, output=None, commands=[])
            states.append(state)
        return sorted(states, key=lambda state: state.get('created_at', ''), reverse=True)

    def queue(self):
        with _locked_directory(self.jobs, fcntl.LOCK_SH):
            states = self.list()
            counts = dict.fromkeys(STATUSES, 0)
            for state in states:
                counts[state['status']] += 1
            return dict(running=next((s for s in states if s['status'] == 'running'), None),
                        queued=sorted((s for s in states if s['status'] == 'queued'), key=_dispatch_order),
                        counts=counts)

    def log(self, job_id):
        path = self._directory(job_id) / 'build.log'
        if path.is_symlink():
            raise ValueError('Invalid log path')
        if not path.is_file():
            return ''
        with path.open('rb') as stream:
            stream.seek(max(0, os.fstat(stream.fileno()).st_size - LOG_TAIL_BYTES))
            return stream.read(LOG_TAIL_BYTES).decode('utf-8', errors='replace')

    def _project(self, project_dir):
        project = Path(project_dir).absolute()
        if (project.resolve() != project or project.parent != self.workspace / 'projects'
                or not PROJECT_ID.fullmatch(project.name) or len(project.name) > 80):
            raise ValueError('Expected a workspace project directory')
        return project

    def _kind(self, project):
        metadata = _read(project / 'project.json')
        if (not isinstance(metadata, dict) or metadata.get('id') != project.name
                or not isinstance(metadata.get('kind'), str) or metadata['kind'] not in _BUILDERS):
            raise ValueError('Invalid project metadata')
        return metadata['kind']

    def _snapshot(self, state):
        directory = self._directory(state['id'])
        spec = _read(directory / 'spec.json')
        if spec_digest(spec) != state.get('spec_sha256'):
            raise ValueError('Job specification snapshot does not match its digest')
        validate_spec(self.root, state.get('kind'), spec)

    def submit(self, project_dir: Path, priority=3):
        return self._submit(self._project(project_dir), _priority(priority))

    def _submit(self, project, priority, original=None):
        # Lock in project -> queue order, including the live-spec check and publication.
        with _locked_directory(project, fcntl.LOCK_SH):
            kind = self._kind(project)
            spec = _read(project / 'spec.json')
            digest = spec_digest(spec)
            if original and (kind != original.get('kind') or digest != original.get('spec_sha256')):
                raise FileExistsError('The project specification or kind has changed')
            validate_spec(self.root, kind, spec)
            with _locked_directory(self.jobs, fcntl.LOCK_EX) as jobs_fd:
                sequence = 1 + max((s.get('queue_sequence', 0) for s in self.list()), default=0)
                # Arrange the wake-up before publishing: a closed executor must not leave
                # a job that was reported as rejected but could run on a future restart.
                self._wake_locked()
                job_id = uuid.uuid4().hex
                state = dict(id=job_id, project_id=project.name, kind=kind, status='queued',
                             priority=priority, queue_sequence=sequence, created_at=_now(),
                             started_at=None, finished_at=None, verified=False, output=None,
                             commands=[], error=None, spec_sha256=digest)
                if original:
                    state['retry_of'] = original['id']
                with tempfile.TemporaryDirectory(prefix='.submit-', dir=self.jobs) as temporary:
                    staged = Path(temporary) / job_id
                    staged.mkdir(mode=0o700)
                    _write(staged / 'spec.json', spec)
                    _write(staged / 'job.json', state)
                    staged.rename(self.jobs / job_id)
                    os.fsync(jobs_fd)
                return state

    def cancel(self, job_id):
        with _locked_directory(self.jobs, fcntl.LOCK_EX):
            state = self.get(job_id)
            if state['status'] != 'queued':
                raise FileExistsError('Only queued jobs can be canceled')
            state.update(status='canceled', verified=False, finished_at=_now())
            _write(self._directory(job_id) / 'job.json', state)
            return state

    def retry(self, job_id):
        original = self.get(job_id)
        if original['status'] not in ('failed', 'canceled'):
            raise FileExistsError('Only failed or canceled jobs can be retried')
        project_id = original.get('project_id')
        if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
            raise ValueError('Invalid job project')
        self._snapshot(original)
        project = self._project(self.workspace / 'projects' / project_id)
        return self._submit(project, original['priority'], original)

    def _wake_locked(self):
        if not self._draining:
            self.worker.submit(self._drain)
            self._draining = True

    def _drain(self):
        try:
            while True:
                with ExitStack() as lease:
                    with _locked_directory(self.jobs, fcntl.LOCK_EX):
                        states = self.list()
                        self._recover_running(states)
                        queued = (s for s in states if s['status'] == 'queued')
                        state = min(queued, key=_dispatch_order, default=None)
                        if state is None or any(s['status'] == 'running' for s in states):
                            self._draining = False
                            return
                        directory = self._directory(state['id'])
                        lease.enter_context(_locked_directory(directory, fcntl.LOCK_EX))
                        if (state.get('commands') != [] or state.get('started_at') is not None
                                or state.get('finished_at') is not None or state.get('verified') is not False
                                or state.get('output') is not None or os.path.lexists(directory / 'build.log')
                                or os.path.lexists(directory / 'output')):
                            state.update(status='failed', verified=False, finished_at=_now(), output=None,
                                         error='Queued job already contains execution evidence')
                            _write(directory / 'job.json', state)
                            continue
                        state.update(status='running', started_at=_now())
                        _write(directory / 'job.json', state)
                    self._run(state['id'])
        except BaseException:
            with _locked_directory(self.jobs, fcntl.LOCK_EX):
                self._draining = False
            raise

    @contextmanager
    def _execution_lease(self):
        # The child inherits this descriptor. After an abrupt Studio exit a surviving
        # builder keeps the workspace exclusive until it exits. Bound restart waits.
        with _locked_directory(self.execution, fcntl.LOCK_UN) as descriptor:
            deadline = time.monotonic() + TIMEOUT_SECONDS
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Timed out waiting for the previous build process to exit')
                    time.sleep(min(0.1, remaining))
            yield descriptor

    def _commands(self, kind, directory):
        builder = [sys.executable, str(self.root / _BUILDERS[kind] / 'build.py')]
        args = [] if kind == 'multiplayer' else [str(directory / 'spec.json')]
        if kind == 'world':
            args += ['--assets', str(self.root / 'demo' / 'first-batch'), '--route-qa']
        if kind in ('gameplay', 'multiplayer'):
            args += ['--world', str(self.root / 'world' / 'demo' / 'training_yard')]
        if kind == 'gameplay':
            fixture = self.root / 'gameplay' / 'tactical_spec.json'
            if fixture.is_file() and _read(fixture) == _read(directory / 'spec.json'):
                args += ['--tactical-qa']
        if kind == 'simulation':
            args += ['--world', str(self.root / 'simulation/demo/expedition_world')]
            if _read(self.root / 'simulation/demo_spec.json') == _read(directory / 'spec.json'):
                args += ['--simulation-qa']
        if kind in _FIXTURE_SCENARIOS and _read(self.root / kind / 'demo_spec.json') == _read(directory / 'spec.json'):
            args += [f'--{kind}-qa']
        output = str(directory / 'output')
        return [('build', builder + args + ['--output', output]),
                ('verify', builder + ['--verify', output])]

    def _run(self, job_id):
        directory = self._directory(job_id)
        state = self.get(job_id)
        try:
            project_id = state.get('project_id')
            if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
                raise ValueError('Invalid job project')
            project = self._project(self.workspace / 'projects' / project_id)
            if self._kind(project) != state.get('kind'):
                raise ValueError('Job does not match project metadata')
            self._snapshot(state)
            with self._execution_lease() as execution_fd, (directory / 'build.log').open('xb', buffering=0) as log:
                for stage, argv in self._commands(state['kind'], directory):
                    log.write(('\n' + stage + ' ' + json.dumps(argv) + '\n').encode())
                    start = time.monotonic()
                    command = dict(stage=stage, argv=argv, exit_code=None,
                                   duration_seconds=None, timed_out=False)
                    state['commands'].append(command)
                    _write(directory / 'job.json', state)
                    try:
                        proc = subprocess.Popen(argv, cwd=self.root, stdin=subprocess.DEVNULL,
                                                stdout=log, stderr=subprocess.STDOUT,
                                                start_new_session=True, pass_fds=(execution_fd,))
                        try:
                            proc.wait(timeout=TIMEOUT_SECONDS)
                        except subprocess.TimeoutExpired:
                            command['timed_out'] = True
                            if os.name == 'posix':
                                try:
                                    os.killpg(proc.pid, signal.SIGKILL)
                                except ProcessLookupError:
                                    pass
                            else:
                                proc.kill()
                            proc.wait()
                        command['exit_code'] = proc.returncode
                    finally:
                        command['duration_seconds'] = round(time.monotonic() - start, 3)
                    if command['timed_out']:
                        raise RuntimeError(f'{stage} timed out')
                    if command['exit_code'] != 0:
                        raise RuntimeError(f"{stage} exited with code {command['exit_code']}")
            output = directory / 'output'
            if not output.is_dir() or output.is_symlink():
                raise ValueError('Builder produced no output directory')
            manifest = output / 'manifest.json'
            if manifest.is_symlink() or not manifest.is_file():
                raise ValueError('Builder produced no regular manifest.json')
            state['manifest_sha256'] = hashlib.sha256(manifest.read_bytes()).hexdigest()
            tactical_report = output / 'reports' / 'tactical-qa.json'
            if state['kind'] == 'gameplay' and tactical_report.is_file():
                state['tactical_qa'] = _read(tactical_report)
            simulation_report = output / 'reports' / 'simulation-qa.json'
            if state['kind'] == 'simulation' and simulation_report.is_file():
                state['simulation_qa'] = _read(simulation_report)
            kind = state['kind']
            if kind in _FIXTURE_SCENARIOS:
                report = output / 'reports' / f'{kind}-qa.json'
                if report.is_file():
                    state[f'{kind}_qa'] = _read(report)
            state.update(status='passed', verified=True, output=str(output.relative_to(self.workspace)))
        except Exception as exc:
            state.update(status='failed', verified=False, error=str(exc))
        finally:
            state['finished_at'] = _now()
            _write(directory / 'job.json', state)
