"""Export a private Godot cutscene project, with optional offline headless QA."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

from command_center.lab_engine_import import (
    MAX_OUTPUT, _installed_godot, _offline_prefix, _run_bounded, _sandbox_env,
)
from command_center.training_lab import MAX_BYTES, _validate_data, reject_duplicate_keys

from .plan import compile_plan


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / 'cinematic/production/template'
FIXTURE = ROOT / 'cinematic/demo/nightfall_patrol'
FIXTURE_MANIFEST_SHA256 = '3a65056d9575c40e107460cdbc6ab3ad628cecb7f03f02f4feab5a22629a4523'
ASSET_FILES = ('assets/animated_actor.glb', 'assets/city.glb', 'assets/footstep.wav')
TEMPLATE_FILES = ('production.gd', 'production.tscn', 'caption_overlay.gd', 'production_qa.gd', 'project.godot')
QA_MARKER = b'STUDIO_PRODUCTION_QA_JSON'
QA_CHECKS = frozenset(('production-scene', 'bindings', 'wrong-trigger', 'entry', 'pause', 'resume',
                       'skip', 'skip-guard', 'interrupt', 'retry', 'timeline', 'skeletal-motion',
                       'completion', 'completion-guard'))
RUNTIME_SCOPE = 'Godot headless clean import and scripted cutscene playback checks'


def _read_regular(path, limit, label):
    def open_regular(name, flags):
        return os.open(name, flags | os.O_NONBLOCK | os.O_NOFOLLOW)

    try:
        with open(path, 'rb', opener=open_regular) as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError(f'{label} must be a regular file.')
            raw = stream.read(limit + 1)
    except OSError as exc:
        raise ValueError(f'{label} must be a readable regular file.') from exc
    if len(raw) > limit:
        raise ValueError(f'{label} exceeds the byte limit.')
    return raw


def _decode_json(raw, label):
    def finite_float(literal):
        value = float(literal)
        if not math.isfinite(value):
            raise ValueError('Nonfinite JSON number')
        return value

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicate_keys,
                           parse_float=finite_float, parse_constant=finite_float)
        # Reject escaped lone surrogates as well as invalid UTF-8 in the source bytes.
        json.dumps(value, ensure_ascii=False).encode('utf-8')
    except (ValueError, RecursionError) as exc:
        raise ValueError(f'{label} requires valid UTF-8 JSON with unique keys and finite numbers.') from exc
    return value


def _read_input(path, label):
    raw = _read_regular(path, MAX_BYTES, label)
    value = _decode_json(raw, label)
    try:
        _validate_data(value)
    except ValueError as exc:
        raise ValueError(f'{label} must be a bounded JSON object.') from exc
    return value, hashlib.sha256(raw).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def _output_path(path):
    original = Path(path).absolute()
    if any(part.is_symlink() for part in (original, *original.parents)):
        raise ValueError('Choose an output path without symbolic links.')
    target = Path(os.path.abspath(original))
    if target.is_relative_to(ROOT):
        raise ValueError('Choose an output directory outside the Studio checkout.')
    if target.exists():
        raise ValueError('Refusing to overwrite an existing output path.')
    return target


def _source_files():
    raw_manifest = _read_regular(FIXTURE / 'manifest.json', MAX_BYTES, 'Sealed fixture manifest')
    if hashlib.sha256(raw_manifest).hexdigest() != FIXTURE_MANIFEST_SHA256:
        raise ValueError('The sealed fixture manifest differs from the original Studio manifest.')
    manifest = _decode_json(raw_manifest, 'Sealed fixture manifest')
    inventory = {row['path']: row for row in manifest['files']}

    def verified_asset(path):
        record = inventory[path]
        raw = _read_regular(FIXTURE / path, record['bytes'], f'Sealed fixture {path}')
        if len(raw) != record['bytes'] or hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise ValueError(f'Sealed fixture {path} differs from its manifest.')
        return raw

    files = {name: verified_asset(name) for name in ASSET_FILES}
    records = _decode_json(verified_asset('assets/provenance.json'), 'Sealed fixture provenance')
    selected = [row for row in records if f"assets/{row['path']}" in files]
    files['assets/provenance.json'] = _json_bytes({
        'source_package': manifest['sequence'],
        'source_manifest_sha256': FIXTURE_MANIFEST_SHA256,
        'assets': selected,
    })
    # Only the Studio's fixed, reviewed project source is eligible for execution.
    if TEMPLATE.resolve() != TEMPLATE:
        raise ValueError('The production template must be in the Studio checkout.')
    for name in TEMPLATE_FILES:
        files[name] = _read_regular(TEMPLATE / name, MAX_BYTES, f'Production template {name}')
    files['LICENSE'] = _read_regular(ROOT / 'LICENSE', MAX_BYTES, 'Studio license')
    return files


def _parse_qa(output, returncode, production_sha256):
    if len(output) > MAX_OUTPUT:
        raise ValueError('Godot QA output exceeds the byte limit.')
    markers = [line for line in output.splitlines() if line.lstrip().startswith(QA_MARKER)]
    prefix = QA_MARKER + b' '
    if len(markers) != 1 or not markers[0].startswith(prefix):
        raise ValueError('Godot must emit exactly one production QA marker.')
    qa = _decode_json(markers[0][len(prefix):], 'Godot QA marker')
    if (type(qa) is not dict or qa.keys() != {'schema_version', 'production_sha256', 'pass', 'checks'}
            or type(qa['schema_version']) is not int or qa['schema_version'] != 1
            or qa['production_sha256'] != production_sha256 or type(qa['pass']) is not bool
            or type(qa['checks']) is not list or not 1 <= len(qa['checks']) <= 64):
        raise ValueError('Godot QA marker has invalid fields or a different production digest.')
    ids, names = set(), set()
    for row in qa['checks']:
        if (type(row) is not dict or row.keys() != {'id', 'name', 'status', 'detail'}
                or type(row['id']) is not str or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', row['id'])
                or type(row['name']) is not str or not row['name'].strip() or len(row['name']) > 128
                or row['status'] not in ('passed', 'failed')
                or type(row['detail']) is not str or len(row['detail']) > 2048):
            raise ValueError('Godot QA contains an invalid check.')
        if row['id'] in ids or row['name'] in names:
            raise ValueError('Godot QA contains duplicate checks.')
        ids.add(row['id'])
        names.add(row['name'])
    passed = all(row['status'] == 'passed' for row in qa['checks'])
    if qa['pass'] != passed or returncode != (0 if passed else 1) or (passed and ids != QA_CHECKS):
        raise ValueError('Godot QA checks, summary or exit code disagree.')
    return qa


def _engine_step(project, env, steps, name, command, timeout):
    step = {'id': name}
    steps.append(step)
    try:
        result = _run_bounded(command, project, env, timeout=timeout, max_output=MAX_OUTPUT)
    except (OSError, RuntimeError) as exc:
        step['error'] = str(exc) if isinstance(exc, RuntimeError) else 'Could not launch the Godot process.'
        return None
    relative = f'reports/{name}.log'
    (project / relative).write_bytes(result.stdout)
    step.update({'log': relative, 'exit_code': result.returncode,
                 'log_sha256': hashlib.sha256(result.stdout).hexdigest()})
    return result


def _has_engine_error(output):
    return any(line.lstrip().startswith((b'ERROR:', b'SCRIPT ERROR:')) for line in output.splitlines())


def _verify_runtime(project, production_sha256):
    runtime = {'status': 'unavailable', 'scope': RUNTIME_SCOPE, 'steps': []}
    offline = _offline_prefix()
    godot = _installed_godot()
    if offline is None or godot is None:
        reason = ('Offline runtime QA requires Linux user network namespaces.' if offline is None
                  else 'A local Godot executable was not found on PATH.')
        return dict(runtime, reason=reason)

    try:
        with tempfile.TemporaryDirectory(prefix='.engine-', dir=project / 'reports') as workspace:
            env = _sandbox_env(Path(workspace))
            steps = runtime['steps']
            command = [*offline, godot]
            version = _engine_step(project, env, steps, 'version', [*command, '--version'], 5)
            if version is None or version.returncode or not re.fullmatch(
                    rb'4\.\d+(?:\.\d+)?\.[A-Za-z0-9_.-]{1,100}', version.stdout.strip()):
                return dict(runtime, reason='Could not start and identify Godot 4 in an offline network namespace.')
            runtime.update(status='failed', godot_version=version.stdout.strip().decode('ascii'),
                           isolation='Linux user network namespace')
            command += ['--headless', '--path', str(project)]
            imported = _engine_step(project, env, steps, 'import', [*command, '--editor', '--import'], 60)
            if imported is None or imported.returncode or _has_engine_error(imported.stdout):
                return dict(runtime, reason='Godot clean import failed.')
            if any(not (project / (name + '.import')).is_file() for name in ASSET_FILES):
                return dict(runtime, reason='Godot did not generate all three asset import remaps.')
            qa = _engine_step(project, env, steps, 'qa', [*command, '--script', 'res://production_qa.gd'], 30)
            if qa is None:
                return dict(runtime, reason='Godot did not finish scripted QA.')
            try:
                runtime['qa'] = _parse_qa(qa.stdout, qa.returncode, production_sha256)
            except ValueError as exc:
                return dict(runtime, reason=str(exc))
            if _has_engine_error(qa.stdout):
                return dict(runtime, reason='Godot emitted an engine error during scripted QA.')
            if not runtime['qa']['pass']:
                return dict(runtime, reason='Godot scripted QA reported failed checks.')
            return dict(runtime, status='passed')
    except OSError:
        return dict(runtime, reason='Could not prepare or record the private Godot run.')


def _verify_original_files(output, inventory):
    for row in inventory:
        try:
            raw = _read_regular(output / row['path'], row['bytes'], row['path'])
        except ValueError as exc:
            raise ValueError(f"The generated file {row['path']} is missing or changed after engine QA.") from exc
        if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError(f"The generated file {row['path']} changed after engine QA.")


def run_production(plan, bindings, output, *, engine=False):
    """Build the trusted project in a new private directory and return its report."""
    output = _output_path(output)
    submission, plan_digest = _read_input(plan, 'Plan')
    scene_bindings, bindings_digest = _read_input(bindings, 'Bindings')
    document = _json_bytes(compile_plan(submission, scene_bindings))
    files = _source_files()
    files['production.json'] = document
    inventory = [{'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                 for name, raw in sorted(files.items())]

    output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the requested destination exclusively before writing any local evidence.
    output.mkdir(mode=0o700)
    (output / 'assets').mkdir()
    (output / 'reports').mkdir()
    (output / 'reports/.gdignore').touch()
    for name, raw in files.items():
        (output / name).write_bytes(raw)

    report = {'schema_version': 1, 'status': 'exported',
              'inputs': {'plan_sha256': plan_digest, 'bindings_sha256': bindings_digest},
              'source_manifest_sha256': FIXTURE_MANIFEST_SHA256, 'files': inventory,
              'runtime': {'status': 'not_requested', 'scope': RUNTIME_SCOPE, 'steps': []}}
    if engine:
        runtime = _verify_runtime(output, hashlib.sha256(document).hexdigest())
        try:
            _verify_original_files(output, inventory)
        except ValueError as exc:
            runtime.update(status='failed', reason=str(exc))
        report.update(status=runtime['status'], runtime=runtime)
    (output / 'reports/report.json').write_bytes(_json_bytes(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path, help='local Cutscene Lab submission JSON')
    parser.add_argument('bindings', type=Path, help='local camera and actor bindings JSON')
    parser.add_argument('--output', type=Path, required=True, help='new private directory outside the checkout')
    parser.add_argument('--engine', action='store_true', help='run isolated clean import and Godot headless QA')
    args = parser.parse_args(argv)
    try:
        report = run_production(args.plan, args.bindings, args.output, engine=args.engine)
    except (ValueError, OSError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2
    print(_json_bytes(report).decode('utf-8'), end='')
    return {'exported': 0, 'passed': 0, 'failed': 1, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
