"""Explicit local releases bound to verified job outputs and project specifications."""
import fcntl
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from factory import build as factory

from .checkpoints import _locked_directory
from .projects import TEMPLATES
from .provenance import spec_digest
from .task_store import MAX_FILE_BYTES, _read_json


REGISTRY = 'releases.json'
RECORD_FIELDS = {'project_id', 'revision', 'releases', 'active_release_id'}
RELEASE_FIELDS = {'id', 'job_id', 'spec_sha256', 'created_at', 'manifest_sha256', 'output'}


def _hex(value, length):
    return isinstance(value, str) and len(value) == length and re.fullmatch('[0-9a-f]+', value) is not None


def _output(job_id):
    return f'jobs/{job_id}/output'


def _read_registry(directory, project_id):
    try:
        record = _read_json(directory, REGISTRY)
    except FileNotFoundError:
        return dict(project_id=project_id, revision=0, releases=[], active_release_id=None)
    if (not isinstance(record, dict) or set(record) != RECORD_FIELDS
            or record['project_id'] != project_id or type(record['revision']) is not int
            or not isinstance(record['releases'], list) or not record['releases']
            or record['revision'] < len(record['releases'])):
        raise ValueError('Invalid release registry')
    ids, jobs = set(), set()
    for release in record['releases']:
        if (not isinstance(release, dict) or set(release) != RELEASE_FIELDS
                or not _hex(release['id'], 32) or not _hex(release['job_id'], 32)
                or release['id'] in ids or release['job_id'] in jobs
                or not _hex(release['spec_sha256'], 64) or not _hex(release['manifest_sha256'], 64)
                or release['output'] != _output(release['job_id'])
                or not isinstance(release['created_at'], str)
                or datetime.fromisoformat(release['created_at']).utcoffset() is None):
            raise ValueError('Invalid stored release')
        ids.add(release['id'])
        jobs.add(release['job_id'])
    if not _hex(record['active_release_id'], 32) or record['active_release_id'] not in ids:
        raise ValueError('Invalid active release ID')
    return record


def _write_registry(directory, record):
    raw = (json.dumps(record, indent=2, allow_nan=False) + '\n').encode()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('Release registry exceeds the storage limit')
    name = f'.releases-{secrets.token_hex(16)}.tmp'
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(name, flags, 0o600, dir_fd=directory)
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


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_ctime_ns)


def _raise_walk_error(error):
    raise error


def _package_tree(directory, snapshot=None):
    """Walk from a pinned directory and copy only safely opened regular files."""
    identities = {}
    for relative, dirs, files, parent in os.fwalk('.', dir_fd=directory, onerror=_raise_walk_error):
        identities[relative] = _identity(os.fstat(parent))
        if snapshot is not None:
            (snapshot / relative).mkdir(exist_ok=True)
        for name in dirs:
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError('Release output contains an unsafe directory')
        for name in files:
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('Release output must contain regular files')
            key = os.path.join(relative, name)
            identities[key] = _identity(info)
            if snapshot is not None:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                with os.fdopen(fd, 'rb') as source:
                    if _identity(os.fstat(fd)) != identities[key]:
                        raise ValueError('Release package changed during verification')
                    with (snapshot / key).open('xb') as target:
                        shutil.copyfileobj(source, target)
    return identities


def _package_seal(job_directory):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open('output', flags, dir_fd=job_directory)
    try:
        # The shared verifier accepts paths and reopens files by name. A private
        # snapshot prevents live symlink substitutions from redirecting those reads.
        with tempfile.TemporaryDirectory(prefix='studio-release-check-') as temporary:
            snapshot = Path(temporary)
            original = _package_tree(directory, snapshot)
            errors = factory.verify_package(snapshot)
            if errors:
                raise ValueError('Release package failed integrity verification: ' + '; '.join(errors))
            seal = factory.hash_file(snapshot / 'manifest.json')
            if (original != _package_tree(directory)
                    or _identity(os.stat('output', dir_fd=job_directory, follow_symlinks=False))
                    != original['.']):
                raise ValueError('Release package changed during verification')
            return seal
    finally:
        os.close(directory)


class ReleaseStore:
    def __init__(self, projects, pipeline):
        self.projects = projects
        if pipeline.jobs != projects.projects.parent / 'jobs':
            raise ValueError('Release jobs and projects must share a workspace')
        self.jobs = pipeline.jobs

    def _verified_seal(self, project_id, kind, digest, job_id):
        try:
            with _locked_directory(self.jobs / job_id, fcntl.LOCK_SH | fcntl.LOCK_NB) as directory:
                job = _read_json(directory, 'job.json')
                if (not isinstance(job, dict) or job.get('id') != job_id or job.get('kind') != kind
                        or job.get('project_id') != project_id or job.get('spec_sha256') != digest
                        or job.get('status') != 'passed' or job.get('verified') is not True
                        or job.get('output') != _output(job_id)):
                    raise ValueError('Release requires a passed, verified job for this project and specification')
                if spec_digest(_read_json(directory, 'spec.json')) != digest:
                    raise ValueError('Job specification snapshot differs from the project')
                seal = _package_seal(directory)
                # Pre-v21 jobs have no build-time seal. Explicit promotion seals
                # their verified package for all subsequent reads and activations.
                if 'queue_sequence' in job or 'manifest_sha256' in job:
                    if job.get('manifest_sha256') != seal:
                        raise ValueError('Release manifest differs from the verified build')
                with _locked_directory(self.jobs / job_id, fcntl.LOCK_SH | fcntl.LOCK_NB) as live:
                    if (not os.path.samestat(os.fstat(directory), os.fstat(live))
                            or _read_json(live, 'job.json') != job
                            or spec_digest(_read_json(live, 'spec.json')) != digest):
                        raise ValueError('Release job changed during verification')
                return seal
        except BlockingIOError as exc:
            raise ValueError('Build job is still in use. Retry after it finishes.') from exc
        except (OSError, RecursionError) as exc:
            raise ValueError('Release job or package is unavailable for verification') from exc

    @staticmethod
    def _read_state(directory, project_id):
        project = _read_json(directory, 'project.json')
        if (not isinstance(project, dict) or project.get('id') != project_id
                or not isinstance(project.get('kind'), str) or project['kind'] not in TEMPLATES):
            raise ValueError('Invalid project metadata')
        digest = spec_digest(_read_json(directory, 'spec.json'))
        return project['kind'], digest, _read_registry(directory, project_id)

    def _check_release(self, project_id, kind, digest, release):
        if release['spec_sha256'] != digest:
            raise ValueError('Release belongs to an older specification')
        if self._verified_seal(project_id, kind, digest, release['job_id']) != release['manifest_sha256']:
            raise ValueError('Release manifest differs from its recorded seal')

    def get(self, project_id):
        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_SH) as directory:
            kind, digest, record = self._read_state(directory, project_id)
            active = next((r for r in record['releases'] if r['id'] == record['active_release_id']), None)
            state = 'empty'
            if active:
                if active['spec_sha256'] != digest:
                    state = 'stale'
                else:
                    try:
                        self._check_release(project_id, kind, digest, active)
                        state = 'current'
                    except ValueError:
                        state = 'invalid'
            return {**record, 'spec_sha256': digest, 'active_state': state}

    def apply(self, project_id, data):
        if (not isinstance(data, dict) or set(data) != {'expected_revision', 'spec_sha256', 'action'}
                or type(data['expected_revision']) is not int or data['expected_revision'] < 0
                or not _hex(data['spec_sha256'], 64)):
            raise ValueError('Supply a nonnegative expected_revision, lowercase spec_sha256 and release action')
        action = data['action']
        if not isinstance(action, dict) or action.get('op') not in ('promote', 'activate'):
            raise ValueError('Unknown release action')
        key = 'job_id' if action['op'] == 'promote' else 'release_id'
        if set(action) != {'op', key} or not _hex(action[key], 32):
            raise ValueError(f'Supply only the release operation and a valid {key}')

        with _locked_directory(self.projects.directory(project_id), fcntl.LOCK_EX) as directory:
            kind, digest, record = self._read_state(directory, project_id)
            if data['expected_revision'] != record['revision']:
                raise FileExistsError('Release registry revision changed. Reload releases.')
            if data['spec_sha256'] != digest:
                raise FileExistsError('Project specification changed. Reload releases.')
            if action['op'] == 'promote':
                job_id = action['job_id']
                if any(r['job_id'] == job_id for r in record['releases']):
                    raise ValueError('A release already exists for this job')
                seal = self._verified_seal(project_id, kind, digest, job_id)
                release = dict(id=secrets.token_hex(16), job_id=job_id, spec_sha256=digest,
                               created_at=datetime.now(timezone.utc).isoformat(),
                               manifest_sha256=seal, output=_output(job_id))
                record['releases'].append(release)
            else:
                release = next((r for r in record['releases'] if r['id'] == action['release_id']), None)
                if release is None:
                    raise ValueError('Unknown release ID for this project')
                self._check_release(project_id, kind, digest, release)
            if release['id'] != record['active_release_id']:
                record['active_release_id'] = release['id']
                record['revision'] += 1
                _write_registry(directory, record)
            return {**record, 'spec_sha256': digest, 'active_state': 'current'}
