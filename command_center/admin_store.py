"""Private, revision-checked local history for registry and tribunal events."""

from contextlib import contextmanager
from copy import deepcopy
import errno
import fcntl
import json
import math
import os
from pathlib import Path
import secrets
import stat

from .checkpoints import _locked_directory
from .projects import _safe_path
from .provenance import spec_digest
from .training_lab import reject_duplicate_keys


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
STREAMS = ('registry', 'tribunal')
GENESIS = '0' * 64
MAX_EVENTS = 1024
MAX_EVENT_BYTES = 128 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_EVENT_DEPTH = 16
MAX_EVENT_NODES = 20_000
_DOCUMENT_FIELDS = {'schema_version', 'revision', 'head_sha256', 'events'}
_ROW_FIELDS = {'revision', 'stream', 'event', 'previous_sha256', 'event_sha256'}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def _event_data(event):
    if type(event) is not dict:
        raise ValueError('An admin event must be a JSON object.')
    count = text_bytes = 0

    def visit(value, depth):
        nonlocal count, text_bytes
        count += 1
        if count > MAX_EVENT_NODES or depth > MAX_EVENT_DEPTH:
            raise ValueError('Admin event exceeds structural limits.')
        kind = type(value)
        if kind is str:
            if len(value) > MAX_EVENT_BYTES:
                raise ValueError('Admin event exceeds the byte limit.')
            try:
                text_bytes += len(value.encode('utf-8'))
            except UnicodeError as exc:
                raise ValueError('Admin event contains invalid Unicode.') from exc
            if text_bytes > MAX_EVENT_BYTES:
                raise ValueError('Admin event exceeds the byte limit.')
        elif kind is dict:
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError('Admin JSON object keys must be strings.')
                visit(key, depth + 1)
                visit(item, depth + 1)
        elif kind is list:
            for item in value:
                visit(item, depth + 1)
        elif not (value is None or kind is bool or (kind is int and -(2 ** 63) <= value < 2 ** 63)
                  or (kind is float and math.isfinite(value))):
            raise ValueError('Admin events must contain bounded, finite JSON values.')

    visit(event, 0)
    raw = _canonical(event)
    if len(raw) > MAX_EVENT_BYTES:
        raise ValueError('Admin event exceeds the byte limit.')
    return raw


def _path(path):
    supplied = _safe_path(Path(path).absolute())
    target = Path(os.path.abspath(supplied))
    if target.is_relative_to(ROOT) or target == target.parent:
        raise ValueError('Choose a private journal file outside the Studio checkout.')
    return target


@contextmanager
def _private_parent(path, lock):
    # The directory descriptor stays stable across atomic replacement of the journal file.
    with _locked_directory(path.parent, lock) as directory:
        info = os.fstat(directory)
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ValueError('The journal parent must be owned by the current user without shared write access.')
        yield directory


def _finite(literal):
    value = float(literal)
    if not math.isfinite(value):
        raise ValueError('Journal contains a non-finite number.')
    return value


def _document(directory, name):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
    except FileNotFoundError:
        return {'schema_version': SCHEMA_VERSION, 'revision': 0, 'head_sha256': GENESIS, 'events': []}
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError('Journal must not be a symbolic link.') from exc
        raise
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or info.st_mode & 0o7077):
            raise ValueError('Journal must be a private regular file owned by the current user.')
        if info.st_size > MAX_FILE_BYTES:
            raise ValueError('Journal exceeds the storage limit.')
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('Journal exceeds the storage limit.')
    try:
        saved = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicate_keys,
                           parse_float=_finite, parse_constant=_finite)
    except (ValueError, RecursionError) as exc:
        raise ValueError('Expected bounded UTF-8 JSON with unique fields and finite numbers.') from exc
    _verify(saved)
    return saved


def _verify(saved):
    if (type(saved) is not dict or set(saved) != _DOCUMENT_FIELDS or type(saved['schema_version']) is not int
            or saved['schema_version'] != SCHEMA_VERSION or type(saved['revision']) is not int
            or type(saved['events']) is not list or not 0 <= saved['revision'] == len(saved['events']) <= MAX_EVENTS):
        raise ValueError('Invalid journal schema or revision.')
    previous = GENESIS
    for revision, row in enumerate(saved['events'], 1):
        if (type(row) is not dict or set(row) != _ROW_FIELDS or type(row['revision']) is not int
                or row['revision'] != revision or type(row['stream']) is not str or row['stream'] not in STREAMS
                or row['previous_sha256'] != previous):
            raise ValueError('Journal event chain is out of order or invalid.')
        _event_data(row['event'])
        claimed = row['event_sha256']
        if spec_digest({key: value for key, value in row.items() if key != 'event_sha256'}) != claimed:
            raise ValueError('Journal event digest mismatch.')
        previous = claimed
    if saved['head_sha256'] != previous:
        raise ValueError('Journal head digest mismatch.')


def _write(directory, name, saved):
    raw = _canonical(saved) + b'\n'
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('Journal exceeds the storage limit.')
    stage = f'.admin-journal-{secrets.token_hex(16)}.tmp'
    fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, name, src_dir_fd=directory, dst_dir_fd=directory)
        # A directory sync error can leave the new revision visible. Reload before retrying.
        os.fsync(directory)
    finally:
        try:
            os.unlink(stage, dir_fd=directory)
        except FileNotFoundError:
            pass


def _snapshot(saved, validator):
    state = {'revision': saved['revision'], 'events': saved['events']}
    if validator is not None:
        if not callable(validator):
            raise ValueError('Journal validator must be callable.')
        if validator(deepcopy(state)) is False:
            raise ValueError('Journal validator rejected the snapshot.')
    return state


def load(path, *, validator=None):
    """Read and verify a journal in an existing private parent directory."""
    target = _path(path)
    with _private_parent(target, fcntl.LOCK_SH) as directory:
        return _snapshot(_document(directory, target.name), validator)


def append(path, expected_revision, stream, event, *, validator=None):
    """Append one event by CAS, validating a copy of the candidate before commit."""
    if type(expected_revision) is not int or not 0 <= expected_revision <= MAX_EVENTS:
        raise ValueError('Expected revision must be a bounded nonnegative integer.')
    if type(stream) is not str or stream not in STREAMS:
        raise ValueError('Unknown admin journal stream.')
    payload = json.loads(_event_data(event))
    target = _path(path)
    with _private_parent(target, fcntl.LOCK_EX) as directory:
        saved = _document(directory, target.name)
        if saved['revision'] != expected_revision:
            raise FileExistsError('Journal revision changed. Reload before appending.')
        if expected_revision == MAX_EVENTS:
            raise ValueError('Journal reached its event limit.')
        row = {'revision': expected_revision + 1, 'stream': stream, 'event': payload,
               'previous_sha256': saved['head_sha256']}
        row['event_sha256'] = spec_digest(row)
        saved['events'].append(row)
        saved.update(revision=row['revision'], head_sha256=row['event_sha256'])
        snapshot = _snapshot(saved, validator)
        _write(directory, target.name, saved)
        return snapshot
