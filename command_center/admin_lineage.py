"""Local, read-only source observations and deterministic release/proposal reports.

A Git content fingerprint covers the literal bytes, paths, types and executable
bits of tracked and non-ignored untracked worktree entries. Symbolic links
contribute link text. No Git materialization or clean filters are applied.
Index identity is recorded separately, including conflicts. Archive/media
fingerprints cover opaque file bytes. Neither observation establishes origin
or approval by itself.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import subprocess
import time


_MAX_BYTES = 1024 * 1024 * 1024
_MAX_ENTRIES = 20_000
_MAX_OUTPUT = 8 * 1024 * 1024
_GIT_SECONDS = 10
_COMMIT = re.compile(r'(?:[a-f0-9]{40}|[a-f0-9]{64})\Z')
_SHA = re.compile(r'[a-f0-9]{64}\Z')
_RELATIONS = ('same', 'ahead', 'behind', 'diverged', 'unknown')
_PROPOSAL_STATUSES = ('proposed', 'under_review', 'accepted', 'deferred', 'rejected')


def project_tag(project, version):
    """Construct a project version tag, without creating a Git ref."""
    if not isinstance(project, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', project) or len(project) > 64:
        raise ValueError('Invalid project slug')
    if not isinstance(version, str) or not re.fullmatch(r'v[0-9]+(?:\.[0-9]+){0,3}(?:-[a-z0-9]+(?:[.-][a-z0-9]+)*)?', version) or len(version) > 64:
        raise ValueError('Invalid version label')
    return f'project/{project}/{version}'


def _repo(path):
    root = Path(path).resolve(strict=True)
    if not root.is_dir() or not (root / '.git').exists():
        raise ValueError('An explicit Git worktree root is required')
    return root


def _git(root, *args, allowed=(0,)):
    # Fixed system search path and isolated Git environment. Only internal
    # plumbing commands are used. Disable lazy fetch and all transport helpers.
    binary = shutil.which('git', path=os.defpath)
    if not binary:
        raise ValueError('Local Git is unavailable')
    env = {'PATH': os.defpath, 'LC_ALL': 'C', 'HOME': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_OPTIONAL_LOCKS': '0', 'GIT_ALLOW_PROTOCOL': '',
           'GIT_NO_LAZY_FETCH': '1', 'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_GRAFT_FILE': '/dev/null',
           'GIT_TERMINAL_PROMPT': '0'}
    command = [binary, '--no-pager', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
               '-c', 'core.untrackedCache=false', '-c', 'core.commitGraph=false',
               '-c', 'protocol.allow=never', '-C', os.fspath(root), *args]
    end = time.monotonic() + _GIT_SECONDS
    with subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as process:
        try:
            output = bytearray()
            with selectors.DefaultSelector() as poll:
                poll.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = end - time.monotonic()
                    if remaining <= 0 or not poll.select(remaining):
                        raise ValueError('Git inspection timed out')
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > _MAX_OUTPUT:
                        raise ValueError('Git inspection output is too large')
            code = process.wait(timeout=max(0, end - time.monotonic()))
            if code not in allowed:
                raise ValueError('Git could not inspect the local source')
            return code, bytes(output)
        except subprocess.TimeoutExpired as exc:
            raise ValueError('Git inspection timed out') from exc
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def _manifest(root):
    head = _git(root, 'rev-parse', '--verify', 'HEAD^{commit}')[1].strip().decode('ascii')
    if not _COMMIT.fullmatch(head):
        raise ValueError('Invalid HEAD identity')
    tree = _git(root, 'ls-tree', '-r', '-z', '--full-tree', head)[1]
    index = _git(root, 'ls-files', '--stage', '-z')[1]
    others = _git(root, 'ls-files', '--others', '--exclude-standard', '-z')[1]
    return head, tree, index, others


def _entries(raw):
    if raw and (not raw.endswith(b'\0') or raw.count(b'\0') > _MAX_ENTRIES):
        raise ValueError('Unsupported or oversized source manifest')
    return raw[:-1].split(b'\0') if raw else []


def _records(raw, index=False):
    result = {}
    for row in _entries(raw):
        header, path = row.split(b'\t', 1)
        mode, middle, last = header.split(b' ')
        if mode not in (b'100644', b'100755', b'120000'):
            raise ValueError('Only regular files and symbolic links can be captured; inspect submodules separately')
        if index:
            digest, stage = middle, last
        else:
            digest, stage = last, b'0'
        result.setdefault(path, []).append((stage, mode, digest))
    return result


@contextmanager
def _parent_fd(root_fd, parts):
    """Pin every intermediate directory and never traverse a worktree symlink."""
    parent = os.dup(root_fd)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        yield parent
    finally:
        os.close(parent)


def _identity(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _read_file(parent, name, remaining, git_hash=None):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > remaining:
            raise ValueError('Source must be a bounded regular file')
        digest = hashlib.sha256()
        blob = None
        if git_hash:
            blob = hashlib.new(git_hash, b'blob %d\0' % info.st_size)
        size = 0
        while chunk := stream.read(min(1024 * 1024, info.st_size - size + 1)):
            size += len(chunk)
            if size > info.st_size:
                raise ValueError('Source changed during capture')
            digest.update(chunk)
            if blob is not None:
                blob.update(chunk)
        after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if size != info.st_size or _identity(info) != _identity(after):
            raise ValueError('Source changed during capture')
    return info, digest.hexdigest(), blob.hexdigest().encode() if blob else None


def _work_entry(directory, path, git_hash, remaining):
    parts = path.split(b'/')
    if any(part in (b'', b'.', b'..', b'.git') for part in parts):
        raise ValueError('Invalid or unsupported nested source path')
    try:
        with _parent_fd(directory, parts[:-1]) as parent:
            info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(parts[-1], dir_fd=parent)
                if len(target) > remaining:
                    raise ValueError('Source exceeds byte limit')
                if _identity(info) != _identity(os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)):
                    raise ValueError('Symbolic link changed during capture')
                blob = hashlib.new(git_hash, b'blob %d\0' % len(target) + target)
                return b'120000', blob.hexdigest().encode(), hashlib.sha256(target).hexdigest(), len(target), _identity(info)
            if stat.S_ISDIR(info.st_mode):
                # A tracked file may have been replaced by an ordinary directory;
                # Git enumerates any new contents in the untracked manifest.
                return None
            info, digest, blob = _read_file(parent, parts[-1], remaining, git_hash)
            mode = b'100755' if info.st_mode & stat.S_IXUSR else b'100644'
            return mode, blob, digest, info.st_size, _identity(info)
    except (FileNotFoundError, NotADirectoryError):
        return None


def _work_identity(directory, path):
    parts = path.split(b'/')
    try:
        with _parent_fd(directory, parts[:-1]) as parent:
            info = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            return None if stat.S_ISDIR(info.st_mode) else _identity(info)
    except (FileNotFoundError, NotADirectoryError):
        return None


def capture_git(repo, project, version):
    """Capture a Git worktree with a committed HEAD; never refresh its index."""
    tag = project_tag(project, version)
    root = _repo(repo)
    if os.fsdecode(_git(root, 'rev-parse', '--show-toplevel')[1].removesuffix(b'\n')) != str(root):
        raise ValueError('Requested directory is not the worktree root')
    manifest = _manifest(root)
    head, tree, index, others = manifest
    committed, staged = _records(tree), _records(index, index=True)
    untracked = set(_entries(others))
    paths = set(staged) | untracked
    if len(paths) > _MAX_ENTRIES:
        raise ValueError('Source contains too many entries')
    digest = hashlib.sha256(b'graveforge-worktree-v1\0')
    git_hash = 'sha1' if len(head) == 40 else 'sha256'
    files = size = changed = 0
    identities = {}
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for path in sorted(paths):
            entry = _work_entry(root_fd, path, git_hash, _MAX_BYTES - size)
            if entry is None:
                if path in untracked:
                    raise ValueError('Untracked source changed during capture')
                changed += path in staged
                identities[path] = None
                continue
            mode, blob, sha, length, identities[path] = entry
            files += 1
            size += length
            digest.update(mode + b'\0' + path + b'\0' + bytes.fromhex(sha))
            if path in staged and staged[path] != [(b'0', mode, blob)]:
                changed += 1
        if manifest != _manifest(root) or any(_work_identity(root_fd, p) != token for p, token in identities.items()):
            raise ValueError('Source changed during capture')
    finally:
        os.close(root_fd)
    staged_count = sum(staged.get(p) != committed.get(p) for p in staged.keys() | committed.keys())
    return {'schema_version': 1, 'kind': 'git', 'project': project, 'version': version, 'tag': tag,
            'source': str(root), 'commit': head, 'sha256': digest.hexdigest(),
            'dirty': bool(staged_count or changed or untracked), 'file_count': files, 'byte_count': size,
            'index_sha256': hashlib.sha256(index).hexdigest(), 'staged_count': staged_count,
            'worktree_count': changed, 'untracked_count': len(untracked)}


def fingerprint_archive(path, project, version):
    """Hash a regular archive, media file or other candidate without opening its format."""
    tag = project_tag(project, version)
    raw = Path(path)
    parent = raw.parent.resolve(strict=True)
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        info, digest, _ = _read_file(directory, raw.name, _MAX_BYTES)
    finally:
        os.close(directory)
    return {'schema_version': 1, 'kind': 'archive', 'project': project, 'version': version,
            'tag': tag, 'source': str(parent / raw.name), 'commit': None, 'sha256': digest,
            'dirty': None, 'file_count': 1, 'byte_count': info.st_size}


def git_ancestry(repo, base_commit, candidate_commit):
    """Report candidate relative to base, checking both supplied full IDs locally."""
    root = _repo(repo)
    for oid in (base_commit, candidate_commit):
        if not isinstance(oid, str) or not _COMMIT.fullmatch(oid):
            return 'unknown'
        code, obj_type = _git(root, 'cat-file', '-t', oid, allowed=(0, 1, 128))
        if code or obj_type.strip() != b'commit':
            return 'unknown'
    if base_commit == candidate_commit:
        return 'same'
    for first, second, relation in ((base_commit, candidate_commit, 'ahead'),
                                    (candidate_commit, base_commit, 'behind')):
        code, _ = _git(root, 'merge-base', '--is-ancestor', first, second, allowed=(0, 1, 128))
        if code == 0:
            return relation
        if code != 1:
            return 'unknown'
    if _git(root, 'rev-parse', '--is-shallow-repository')[1].strip() == b'true':
        return 'unknown'
    return 'diverged'


def _source(record):
    if not isinstance(record, dict) or record.get('schema_version') != 1:
        raise ValueError('Invalid source record')
    if record.get('tag') != project_tag(record.get('project'), record.get('version')):
        raise ValueError('Invalid project tag')
    if not isinstance(record.get('source'), str) or not record['source']:
        raise ValueError('Source identity is required')
    if not isinstance(record.get('sha256'), str) or not _SHA.fullmatch(record['sha256']):
        raise ValueError('Invalid content SHA-256')
    if record.get('kind') == 'archive':
        if record.get('commit') is None and record.get('dirty') is None:
            return
    elif record.get('kind') == 'git':
        oid, index = record.get('commit'), record.get('index_sha256')
        if (type(record.get('dirty')) is bool and isinstance(oid, str) and _COMMIT.fullmatch(oid)
                and isinstance(index, str) and _SHA.fullmatch(index)):
            return
    raise ValueError('Invalid source provenance')


def compare_sources(base, candidate, ancestry='unknown'):
    """Pure comparison. Equal labels alone prove neither content nor ancestry."""
    _source(base)
    _source(candidate)
    if ancestry not in _RELATIONS:
        raise ValueError('Invalid Git relation')
    git_pair = base['kind'] == candidate['kind'] == 'git'
    if not git_pair:
        ancestry = 'unknown'
    if git_pair and ancestry != 'unknown' and (ancestry == 'same') != (base['commit'] == candidate['commit']):
        raise ValueError('Git relation contradicts the supplied commits')
    same_bytes = base['sha256'] == candidate['sha256'] if base['kind'] == candidate['kind'] else None
    equivalent = same_bytes is True and (not git_pair or
                 (base['commit'], base['index_sha256'], base['dirty']) ==
                 (candidate['commit'], candidate['index_sha256'], candidate['dirty']))
    same_tag = base['tag'] == candidate['tag']
    collision = same_tag and not equivalent
    uncertain = (base['project'] == candidate['project'] and not equivalent
                 and ancestry in ('unknown', 'diverged'))
    review = collision or uncertain
    return {'tag': candidate['tag'], 'same_project_tag': same_tag, 'same_source': base['source'] == candidate['source'],
            'same_content': same_bytes, 'equivalent': equivalent, 'ancestry': ancestry,
            'tag_collision': collision, 'quarantine': review, 'disposition': 'quarantine' if review else 'retain'}


def release_eligibility(canonical, candidate, ancestry='unknown'):
    """Advise against shared releases from any source other than the named canonical checkout."""
    result = compare_sources(canonical, candidate, ancestry)
    eligible = (result['same_project_tag'] and result['same_source'] and result['equivalent']
                and candidate['kind'] == 'git' and candidate['dirty'] is False)
    return {'eligible': eligible, 'tag': candidate['tag'], 'quarantine': result['quarantine'],
            'reason': 'clean_canonical_checkout' if eligible else 'canonical_capture_required'}


def triage_proposal(owner, source, status='proposed'):
    """Return a bounded proposal record. Recording a status never creates a release."""
    for label, value in (('owner', owner), ('source', source)):
        if not isinstance(value, str) or not value.strip() or len(value) > 512 or not value.isprintable():
            raise ValueError(f'Invalid proposal {label}')
    if status not in _PROPOSAL_STATUSES:
        raise ValueError('Invalid proposal status')
    return {'owner': owner, 'source': source, 'status': status}
