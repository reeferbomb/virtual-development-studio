"""Editable project records for the local Studio command center."""
import fcntl
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cinematic import build as cinematic
from factory import build as factory
from gameplay import build as gameplay
from world import build as world


TEMPLATES = {
    'assets': 'factory/demo_spec.json',
    'world': 'world/demo_spec.json',
    'gameplay': 'gameplay/demo_spec.json',
    'multiplayer': None,
    'cinematic': 'cinematic/sequence.json',
    'simulation': 'simulation/demo_spec.json',
    'openworld': 'openworld/demo_spec.json',
    'unified': 'unified/demo_spec.json',
    'living': 'living/demo_spec.json',
    'city': 'city/demo_spec.json',
    'vertical': 'vertical/demo_spec.json',
    'advanced': 'advanced/demo_spec.json',
    'frontline': 'frontline/demo_spec.json',
}
PROJECT_ID = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
PROJECT_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,79}')


def validate_spec(root, kind, spec):
    """Check the editable JSON using the same constraints as the build CLI."""
    if not isinstance(kind, str) or kind not in TEMPLATES:
        raise ValueError('Unknown project kind')
    try:
        json.dumps(spec, allow_nan=False)
        if kind == 'gameplay':
            source = Path(root) / 'world/demo/training_yard'
            if factory.verify_package(source):
                raise ValueError('Training yard integrity check failed')
            gameplay.validate(spec, json.loads((source / 'level.json').read_text(encoding='utf-8')))
        elif kind == 'simulation':
            from simulation import build as simulation
            source = Path(root) / 'simulation/demo/expedition_world'
            if factory.verify_package(source):
                raise ValueError('Expedition world integrity check failed')
            simulation.validate(spec, json.loads((source / 'level.json').read_text(encoding='utf-8')))
        elif kind == 'openworld':
            from openworld import build as openworld
            openworld.validate(spec)
        elif kind == 'unified':
            from unified import build as unified
            unified.validate(spec)
        elif kind == 'living':
            from living import build as living
            living.validate(spec)
        elif kind in ('city', 'vertical', 'advanced', 'frontline'):
            from city import layout
            layout.validate(spec)
        elif kind == 'multiplayer':
            if spec != {}:
                raise ValueError('Multiplayer uses a fixed, empty spec object')
        else:
            validators = {'assets': factory.validate_spec, 'world': world.validate, 'cinematic': cinematic.validate}
            validators[kind](spec)
    except (TypeError, OverflowError, RecursionError) as exc:
        raise ValueError('Invalid JSON specification') from exc
    return spec


def _safe_path(path):
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('Project storage must not contain symbolic links')
    return path


def _read(path):
    return json.loads(_safe_path(path).read_text(encoding='utf-8'))


def _write(path, value):
    _safe_path(path)
    handle = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.write('\n')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class ProjectStore:
    def __init__(self, root: Path, workspace: Path):
        self.root = Path(root).resolve()
        workspace = _safe_path(Path(workspace).absolute()).resolve()
        if workspace.is_relative_to(self.root) or self.root.is_relative_to(workspace / 'projects'):
            raise ValueError('Choose a separate project workspace')
        self.projects = _safe_path(workspace / 'projects')
        self.projects.mkdir(parents=True, exist_ok=True)

    def _path(self, identifier):
        if not isinstance(identifier, str) or len(identifier) > 80 or not PROJECT_ID.fullmatch(identifier):
            raise ValueError('Invalid project ID')
        return _safe_path(self.projects / identifier)

    def directory(self, identifier):
        path = self._path(identifier)
        if not path.is_dir():
            raise FileNotFoundError('Project does not exist')
        return path

    def _metadata(self, directory):
        metadata = _read(directory / 'project.json')
        if (not isinstance(metadata, dict) or metadata.get('id') != directory.name
                or metadata.get('kind') not in TEMPLATES):
            raise ValueError('Invalid project metadata')
        return metadata

    def get(self, identifier):
        directory = self.directory(identifier)
        return {**self._metadata(directory), 'spec': _read(directory / 'spec.json')}

    def list(self):
        return [self._metadata(self.directory(path.name))
                for path in sorted(_safe_path(self.projects).iterdir())
                if PROJECT_ID.fullmatch(path.name) and not path.is_symlink() and path.is_dir()]

    def create(self, name, kind):
        if not isinstance(name, str) or not PROJECT_NAME.fullmatch(name) or name != name.strip():
            raise ValueError('Use a 1–80 character project name starting with a letter or digit')
        if not isinstance(kind, str) or kind not in TEMPLATES:
            raise ValueError('Unknown project kind')
        identifier = re.sub(r'[ _-]+', '-', name.lower()).rstrip('-')
        destination = self._path(identifier)
        template = TEMPLATES[kind]
        spec = validate_spec(self.root, kind, _read(self.root / template) if template else {})
        metadata = {'id': identifier, 'name': name, 'kind': kind,
                    'created_at': datetime.now(timezone.utc).isoformat()}
        # Publish both files together. The directory lock serializes duplicate creators.
        with tempfile.TemporaryDirectory(prefix='.create-', dir=self.projects) as tmp:
            staged = Path(tmp) / identifier
            staged.mkdir()
            _write(staged / 'project.json', metadata)
            _write(staged / 'spec.json', spec)
            lock = os.open(self.projects, os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if _safe_path(destination).exists():
                    raise FileExistsError('Project ID already exists')
                staged.rename(destination)
            finally:
                os.close(lock)
        return {**metadata, 'spec': spec}

    def save_spec(self, identifier, spec):
        directory = self.directory(identifier)
        # Checkpoint writers use this same directory lock so the project digest
        # cannot change while a checkpoint is validated and committed.
        lock = os.open(directory, os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            metadata = self._metadata(directory)
            validate_spec(self.root, metadata['kind'], spec)
            _write(directory / 'spec.json', spec)
            return {**metadata, 'spec': spec}
        finally:
            os.close(lock)
