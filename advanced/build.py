"""Build and verify the standalone Advanced City Godot project."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from city import layout
from factory import build as factory
from vertical import build as vertical
from world.build import run_stage

validate = layout.validate
COMPONENTS = ('tower', 'vehicle', 'npc_interactions', 'session_network', 'session_store')
MAIN_SCENE = 'advanced.tscn'
READY = 'STUDIO_ADVANCED_READY'
MARKER = 'STUDIO_ADVANCED_QA_JSON '
REPORT = 'reports/advanced-qa.json'
SCENARIO_LOG = 'reports/advanced-qa.log'


def _read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _fixture():
    return validate(_read_json(HERE / 'demo_spec.json'))


def _sources():
    runtime, tests, project = vertical._sources()
    advanced_runtime = [HERE / 'template' / name for name in (
        'advanced.gd', MAIN_SCENE, 'advanced_qa.gd', *(f'{part}.gd' for part in COMPONENTS),
    )]
    advanced_tests = [HERE / 'tests' / f'test_{part}.gd' for part in COMPONENTS]
    for path in (*advanced_runtime, *advanced_tests):
        if not path.is_file():
            raise ValueError(f'Required Advanced City source is missing: {path.relative_to(ROOT)}')
    return runtime + advanced_runtime, tests + advanced_tests, project


def _check_report(report):
    if not isinstance(report, dict) or report.get('pass') is not True:
        raise ValueError('Advanced City scenario QA did not pass')
    checks = report.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('Advanced City scenario QA did not report its checks')
    if any(not isinstance(check, dict) or check.get('status') != 'passed' for check in checks):
        raise ValueError('Advanced City scenario QA reported a check that did not pass')


def _scenario_report(output):
    markers = [line.removeprefix(MARKER) for line in output.splitlines() if line.startswith(MARKER)]
    if len(markers) != 1:
        raise ValueError('Advanced City scenario QA must emit exactly one report')
    report = json.loads(markers[0])
    _check_report(report)
    return report


def _run_scenario(command, stage):
    output = run_stage(command + ['--fixed-fps', '60', '--script', 'res://advanced_qa.gd'],
                       stage / SCENARIO_LOG, MARKER)
    report = _scenario_report(output)
    factory.write_json(stage / REPORT, report)
    print(MARKER + json.dumps(report, separators=(',', ':')), flush=True)
    return report


def verify(package):
    package = Path(package)
    errors = factory.verify_package(package)
    if errors:
        return errors
    try:
        manifest = _read_json(package / 'manifest.json')
        if manifest.get('kind') != 'advanced' or 'advanced_qa' not in manifest:
            raise ValueError('Package manifest must describe an Advanced City build')
        spec = validate(manifest.get('spec'))
        generated = _read_json(package / 'city.json')
        layout.validate_layout(generated)
        if generated != layout.generate(spec):
            raise ValueError('City layout differs from the manifest spec')

        runtime, tests, _ = _sources()
        required = [path.name for path in runtime]
        required += [f'tests/{path.name}' for path in tests]
        required += [f'reports/{path.stem}.log' for path in tests]
        required += ['project.godot', 'reports/import.log', 'reports/launch.log']
        for relative in required:
            if not (package / relative).is_file():
                raise ValueError(f'Required Advanced City package file is missing: {relative}')
        project_text = (package / 'project.godot').read_text(encoding='utf-8')
        scene_settings = [line for line in project_text.splitlines() if line.startswith('run/main_scene=')]
        if scene_settings != [f'run/main_scene="res://{MAIN_SCENE}"']:
            raise ValueError('Advanced City must be the package main scene')
        if READY not in (package / 'reports/launch.log').read_text(encoding='utf-8').splitlines():
            raise ValueError('Advanced City launch readiness is missing')

        report_path = package / REPORT
        scenario_path = package / SCENARIO_LOG
        report = manifest['advanced_qa']
        if report is not None:
            if spec != _fixture():
                raise ValueError('Advanced City scenario QA requires the exact shipped fixture')
            _check_report(report)
            if report != _read_json(report_path):
                raise ValueError('Advanced City scenario QA differs from the manifest')
            scenario_output = scenario_path.read_text(encoding='utf-8')
            if report != _scenario_report(scenario_output):
                raise ValueError('Advanced City scenario QA differs from the execution log')
        elif report_path.exists() or scenario_path.exists():
            raise ValueError('Advanced City scenario QA is missing from the manifest')
        return []
    except (OSError, ValueError) as exc:
        return [str(exc)]


def build(spec_path, dest, godot='godot', *, advanced_qa=False):
    spec = validate(_read_json(Path(spec_path)))
    if advanced_qa and spec != _fixture():
        raise ValueError('--advanced-qa requires the exact shipped fixture')
    dest = Path(dest).absolute()
    resolved_dest = dest.resolve()
    sources = (HERE, ROOT / 'vertical', ROOT / 'city', ROOT / 'openworld', ROOT / 'world')
    if any(resolved_dest.is_relative_to(base / part) for base in sources for part in ('template', 'tests')):
        raise ValueError('Output must be outside source directories')
    runtime, tests, project = _sources()
    stage = factory.new_staging(dest)
    print('Advanced City staging:', stage, flush=True)
    try:
        reports = stage / 'reports'
        reports.mkdir()
        (stage / 'tests').mkdir()
        for path in runtime:
            shutil.copy2(path, stage / path.name)
        for path in tests:
            shutil.copy2(path, stage / 'tests' / path.name)
        project_text = project.read_text(encoding='utf-8')
        project_text = project_text.replace('Studio Frontier Lab', 'Studio Advanced City')
        project_text = project_text.replace('res://openworld.tscn', f'res://{MAIN_SCENE}')
        (stage / 'project.godot').write_text(project_text, encoding='utf-8')
        factory.write_json(stage / 'city.json', layout.generate(spec))

        command = [godot, '--headless', '--path', str(stage)]
        run_stage(command + ['--editor', '--import'], reports / 'import.log')
        run_stage(command + ['--quit-after', '10'], reports / 'launch.log', READY)
        for path in tests:
            run_stage(command + ['--script', f'res://tests/{path.name}'], reports / f'{path.stem}.log')
        report = _run_scenario(command, stage) if advanced_qa else None

        cache = stage / '.godot'
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
        factory.write_json(stage / 'manifest.json', {
            'schema': 1, 'status': 'passed', 'kind': 'advanced', 'spec': spec,
            'advanced_qa': report, 'files': factory.inventory(stage),
        })
        errors = verify(stage)
        if errors:
            raise ValueError('; '.join(errors))
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(f'Destination appeared during build: {dest}')
        stage.rename(dest)
        print('ADVANCED_FACTORY_PASS', dest)
    except Exception:
        print('Advanced City build failed; diagnostics retained:', stage, file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', nargs='?', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--godot', default='godot')
    parser.add_argument('--advanced-qa', action='store_true', help='Run the full shipped Advanced City scenario')
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        problems = verify(args.verify.absolute())
        print('; '.join(problems) if problems else 'ADVANCED_INTEGRITY_PASS')
        return int(bool(problems))
    if not args.spec or not args.output:
        parser.error('Specify a spec and --output, or --verify')
    build(args.spec, args.output, args.godot, advanced_qa=args.advanced_qa)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print('Advanced City factory:', exc, file=sys.stderr)
        sys.exit(1)
