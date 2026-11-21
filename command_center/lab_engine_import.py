"""Probe a trusted GLB with an installed Godot 4 editor in an offline temporary project."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import selectors
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time

from .lab_artifact import inspect_glb, objects, read_chunks, read_glb_bytes, require
from .training_lab import reject_duplicate_keys


PROFILE = 'godot-import-glb-v1'
SOURCE_NAME = 'source_asset.glb'
SCRIPT_NAME = 'probe.gd'
MARKER = 'GRAVEFORGE_IMPORT_'
MAX_OUTPUT = 128 * 1024
CORE_FIELDS = {'asset', 'accessors', 'animations', 'buffers', 'bufferViews', 'extras',
               'materials', 'meshes', 'nodes', 'scene', 'scenes', 'skins'}
COUNTS = ('mesh_instances', 'skeletons', 'bones', 'animation_players', 'animations')
SCENE_LIMITS = {'declared_nodes': 4096, 'declared_mesh_instances': 1024}

PROJECT = '''config_version=5

[application]
config/name="Graveforge Import Probe"

[debug]
file_logging/enable_file_logging=false

[rendering]
renderer/rendering_method="gl_compatibility"
'''

SCRIPT = '''extends SceneTree

const SOURCE = "res://source_asset.glb"

func _initialize() -> void:
    var args := OS.get_cmdline_user_args()
    if args.size() != 1:
        quit(2)
        return
    var scene := ResourceLoader.load(SOURCE, "PackedScene") as PackedScene
    if scene == null:
        quit(3)
        return
    var instance := scene.instantiate()
    if instance == null:
        quit(4)
        return
    var inventory := {"mesh_instances": 0, "skeletons": 0, "bones": 0,
        "animation_players": 0, "animations": 0}
    var pending: Array[Node] = [instance]
    while not pending.is_empty():
        var node: Node = pending.pop_back()
        if node is MeshInstance3D and node.mesh != null:
            inventory.mesh_instances += 1
        if node is Skeleton3D:
            inventory.skeletons += 1
            inventory.bones += node.get_bone_count()
        if node is AnimationPlayer:
            inventory.animation_players += 1
            for animation in node.get_animation_list():
                if animation != &"RESET":
                    inventory.animations += 1
        pending.append_array(node.get_children(true))
    instance.free()
    inventory.sha256 = FileAccess.get_sha256(SOURCE)
    print("GRAVEFORGE_IMPORT_" + args[0] + " " + JSON.stringify(inventory))
    quit()
'''


def _finite_float(value):
    return type(value) in (int, float) and -3.4028234663852886e38 <= value <= 3.4028234663852886e38


def _vector(value, size, label):
    require(isinstance(value, list) and len(value) == size and all(map(_finite_float, value)),
            f'Invalid {label} vector')
    return value


def _validate_import_fields(doc):
    # The data-only profiles do not inspect every field consumed by scene import.
    require(doc.keys() <= CORE_FIELDS, 'GLB contains fields outside the offline import profile')
    require('animations' not in doc or 'skins' in doc, 'The engine profile requires skins for animated GLBs')
    nodes = objects(doc, 'nodes')
    for node in nodes:
        require('camera' not in node, 'Camera nodes are outside the offline import profile')
        if 'matrix' in node:
            require(not any(key in node for key in ('translation', 'rotation', 'scale')),
                    'A node matrix cannot be combined with translation, rotation or scale')
            matrix = _vector(node['matrix'], 16, 'node matrix')
            require(matrix[3::4] == [0, 0, 0, 1], 'Expected an affine node matrix')
        for field, size in (('translation', 3), ('rotation', 4), ('scale', 3)):
            if field in node:
                values = _vector(node[field], size, f'node {field}')
                if field == 'rotation':
                    require(math.isclose(math.hypot(*values), 1.0, rel_tol=1e-4),
                            'Node rotation must be a unit quaternion')
    for material in objects(doc, 'materials'):
        require(material.get('alphaMode', 'OPAQUE') in ('OPAQUE', 'MASK', 'BLEND'), 'Invalid material alphaMode')
        require(type(material.get('doubleSided', False)) is bool, 'Invalid material doubleSided')
        cutoff = material.get('alphaCutoff', 0.5)
        require(_finite_float(cutoff) and cutoff >= 0, 'Invalid material alphaCutoff')
        pbr = material.get('pbrMetallicRoughness', {})
        require(isinstance(pbr, dict), 'Invalid material pbrMetallicRoughness')
        for field, size, values in (('baseColorFactor', 4, pbr), ('emissiveFactor', 3, material)):
            if field in values:
                require(all(0 <= channel <= 1 for channel in _vector(values[field], size, field)),
                        f'{field} components must be between 0 and 1')
        for field in ('metallicFactor', 'roughnessFactor'):
            value = pbr.get(field, 1)
            require(_finite_float(value) and 0 <= value <= 1, f'Invalid material {field}')
    return {'declared_nodes': len(nodes), 'declared_mesh_instances': sum('mesh' in node for node in nodes)}


def _source_reports(doc, source):
    reports = []
    if 'skins' in doc:
        from .lab_rig import inspect_rig
        reports.append(inspect_rig(source))
    if 'animations' in doc:
        from .lab_animation import inspect_animation
        reports.append(inspect_animation(source))
    return reports or [inspect_glb(source)]


def _installed_godot():
    # Ignore relative PATH entries, including implicit lookups from the current directory.
    path = os.pathsep.join(entry for entry in os.get_exec_path() if os.path.isabs(entry))
    for name in ('godot4', 'godot'):
        if executable := shutil.which(name, path=path):
            return os.path.realpath(executable)
    return None


def _offline_prefix():
    if sys.platform == 'linux' and (unshare := shutil.which('unshare', path=os.defpath)):
        return [unshare, '--user', '--map-current-user', '--net', '--']
    return None


def _sandbox_env(directory):
    env = {'LANG': 'C.UTF-8', 'PATH': os.defpath}
    for name in ('HOME', 'TMPDIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME',
                 'XDG_RUNTIME_DIR', 'XDG_STATE_HOME'):
        path = directory / name.lower()
        path.mkdir(mode=0o700)
        env[name] = str(path)
    return env


def _run_bounded(command, directory, env, *, timeout, max_output=MAX_OUTPUT):
    deadline = time.monotonic() + timeout
    output = bytearray()
    with subprocess.Popen(command, cwd=directory, env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True) as proc:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise RuntimeError('Godot process timed out')
                    chunk = os.read(proc.stdout.fileno(), min(8192, max_output - len(output) + 1))
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > max_output:
                        raise RuntimeError('Godot process exceeded the output limit')
            code = proc.wait(timeout=max(0, deadline - time.monotonic()))
        except BaseException as exc:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if isinstance(exc, subprocess.TimeoutExpired):
                raise RuntimeError('Godot process timed out') from exc
            raise
    return subprocess.CompletedProcess(command, code, stdout=bytes(output))


def _observed_scene(output, token, digest):
    prefix = (MARKER + token + ' ').encode('ascii')
    matches = [line[len(prefix):] for line in output.splitlines() if line.startswith(prefix)]
    require(len(matches) == 1, 'Godot did not emit exactly one verified scene marker')
    marker = json.loads(matches[0], object_pairs_hook=reject_duplicate_keys)
    require(isinstance(marker, dict) and marker.keys() == {'sha256', *COUNTS} and
            marker['sha256'] == digest, 'Godot scene marker does not match the verified GLB')
    require(all(type(marker[key]) is int and 0 <= marker[key] <= 0xffffffff for key in COUNTS),
            'Godot scene marker contains invalid inventory counts')
    return {key: marker[key] for key in COUNTS}


def _check(report, name, measured, limit, status):
    report['checks'].append({'id': name, 'measured': measured, 'limit': limit, 'status': status})


def _stop(report, status, name, note, measured=False, limit=True):
    _check(report, name, measured, limit, status)
    return dict(report, status=status, note=note)


def _probe_scene(report, doc, project):
    offline = _offline_prefix()
    if offline is None:
        return _stop(report, 'unavailable', 'offline_environment',
                     'Offline engine import requires Linux with util-linux unshare and user network namespaces.')
    godot = _installed_godot()
    if godot is None:
        return _stop(report, 'unavailable', 'godot_version', 'Godot 4 editor executable was not found on PATH.')

    env = _sandbox_env(project.parent)
    try:
        version = _run_bounded([*offline, godot, '--version'], project, env, timeout=5)
    except (OSError, RuntimeError) as exc:
        return _stop(report, 'unavailable', 'godot_version', f'Cannot start the isolated Godot version check. {exc}')
    if version.returncode and version.stdout.startswith(b'unshare:'):
        return _stop(report, 'unavailable', 'offline_environment', 'Cannot open an isolated Linux network namespace.')
    version_text = version.stdout.strip()
    if version.returncode or not re.fullmatch(rb'4\.\d+(?:\.\d+)?\.[A-Za-z0-9_.-]{1,100}', version_text):
        return _stop(report, 'unavailable', 'godot_version', 'The isolated executable did not identify as Godot 4.')
    report['measurements']['godot_version'] = version_text.decode('ascii')
    _check(report, 'godot_version', 4, 4, 'pass')

    (project / 'project.godot').write_text(PROJECT, encoding='utf-8')
    (project / SCRIPT_NAME).write_text(SCRIPT, encoding='utf-8')
    command = [*offline, godot, '--headless', '--path', str(project), '--log-file', os.devnull]
    try:
        imported = _run_bounded([*command, '--editor', '--import'], project, env, timeout=30)
    except (OSError, RuntimeError) as exc:
        return _stop(report, 'fail', 'editor_import', str(exc))
    if imported.returncode != 0:
        return _stop(report, 'fail', 'editor_import', 'Godot editor import returned a failing exit code.',
                     measured=imported.returncode, limit=0)
    if not (project / (SOURCE_NAME + '.import')).is_file():
        return _stop(report, 'fail', 'editor_import', 'Godot produced no import remap for the GLB.')
    _check(report, 'editor_import', imported.returncode, 0, 'pass')

    try:
        token = secrets.token_hex(16)
        loaded = _run_bounded([*command, '--script', f'res://{SCRIPT_NAME}', '--', token], project, env, timeout=10)
        if loaded.returncode != 0:
            return _stop(report, 'fail', 'packed_scene', 'Godot scene probe returned a failing exit code.',
                         measured=loaded.returncode, limit=0)
        inventory = _observed_scene(loaded.stdout, token, report['sha256'])
    except (OSError, RuntimeError, ValueError, RecursionError) as exc:
        return _stop(report, 'fail', 'packed_scene', str(exc))
    _check(report, 'packed_scene', True, True, 'pass')
    report['measurements'].update(inventory)

    minimums = {'mesh_instances': 1, 'skeletons': int('skins' in doc), 'animations': len(doc.get('animations', []))}
    for field, minimum in minimums.items():
        _check(report, field, inventory[field], minimum, 'pass' if inventory[field] >= minimum else 'fail')
    return dict(report, status='fail' if any(check['status'] == 'fail' for check in report['checks']) else 'pass',
                note='Godot loaded and instantiated the imported PackedScene. '
                     'Inventory checks use minimum counts. The animation count excludes the RESET pose. '
                     'Visual quality, animation playback and game behavior require separate review.')


def inspect_engine_import(path):
    """Preflight one bounded GLB and verify an actual offline Godot import when available."""
    report = {'profile': PROFILE, 'status': 'unavailable', 'sha256': None, 'measurements': {}, 'checks': []}
    if not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_NONBLOCK'):
        return _stop(report, 'unavailable', 'offline_environment', 'The host lacks safe regular-file reading support.')
    try:
        raw = read_glb_bytes(path)
        report['sha256'] = hashlib.sha256(raw).hexdigest()
        report['measurements']['file_bytes'] = len(raw)
        doc, _ = read_chunks(raw)
        counts = _validate_import_fields(doc)
    except (OSError, ValueError, OverflowError, RecursionError, struct.error) as exc:
        return _stop(report, 'unavailable', 'source_preflight', str(exc))

    try:
        with tempfile.TemporaryDirectory(prefix='graveforge-godot-') as directory:
            project = Path(directory).resolve() / 'project'
            project.mkdir(mode=0o700)
            source = project / SOURCE_NAME
            source.write_bytes(raw)
            preflights = _source_reports(doc, source)
            for preflight in preflights:
                if preflight['sha256'] != report['sha256']:
                    return _stop(report, 'unavailable', 'source_preflight', 'Copied GLB failed the digest check.')
                if preflight['status'] == 'unavailable':
                    return _stop(report, 'unavailable', 'source_preflight', preflight['note'])
            report['measurements']['source_profiles'] = [item['profile'] for item in preflights]
            for preflight in preflights:
                for check in preflight['checks']:
                    if check['status'] == 'fail':
                        report['checks'].append(dict(check, id=f"{preflight['profile']}.{check['id']}"))
            if report['checks']:
                return _stop(report, 'fail', 'source_preflight', 'The GLB exceeds an applicable source profile budget.')
            _check(report, 'source_preflight', True, True, 'pass')
            report['measurements'].update(counts)
            for name, limit in SCENE_LIMITS.items():
                _check(report, name, counts[name], limit, 'pass' if counts[name] <= limit else 'fail')
            if any(check['status'] == 'fail' for check in report['checks']):
                return dict(report, status='fail', note='The GLB exceeds the offline import scene limits.')
            return _probe_scene(report, doc, project)
    except OSError as exc:
        return _stop(report, 'unavailable', 'temporary_workspace', f'Cannot use the temporary Godot project. {exc}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', metavar='PATH', help='a trusted self-contained static or skinned GLB')
    report = inspect_engine_import(parser.parse_args(argv).path)
    print(json.dumps(report, indent=2, allow_nan=False))
    return {'pass': 0, 'fail': 1, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
