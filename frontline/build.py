"""Build and verify the standalone Frontline City Godot project."""

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
from advanced import build as advanced
from city import layout
from factory import build as factory
from world.build import run_stage

validate = layout.validate
COMPONENTS = ('shared_vehicle', 'shared_lift', 'shared_cover', 'mission_director', 'squad_ai')
MAIN_SCENE = 'frontline.tscn'
READY = 'STUDIO_FRONTLINE_READY'
MARKER = 'STUDIO_FRONTLINE_QA_JSON '
REPORT = 'reports/frontline-qa.json'
SCENARIO_LOG = 'reports/frontline-qa.log'


def _read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _fixture():
    return validate(_read_json(HERE / 'demo_spec.json'))


def _sources():
    runtime, tests, project = advanced._sources()
    frontline_runtime = [HERE / 'template' / name for name in (
        'frontline.gd', MAIN_SCENE, 'frontline_network.gd', 'frontline_qa.gd',
        *(f'{part}.gd' for part in COMPONENTS),
    )]
    frontline_tests = [HERE / 'tests' / f'test_{part}.gd' for part in COMPONENTS]
    for path in (*frontline_runtime, *frontline_tests):
        if not path.is_file():
            raise ValueError(f'Required Frontline City source is missing: {path.relative_to(ROOT)}')
    return runtime + frontline_runtime, tests + frontline_tests, project


def _check_report(report):
    if not isinstance(report, dict) or report.get('pass') is not True:
        raise ValueError('Frontline City scenario QA did not pass')
    checks = report.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('Frontline City scenario QA did not report its checks')
    if any(not isinstance(check, dict) or check.get('status') != 'passed' for check in checks):
        raise ValueError('Frontline City scenario QA reported a check that did not pass')


def _scenario_report(output):
    markers = [line.removeprefix(MARKER) for line in output.splitlines() if line.startswith(MARKER)]
    if len(markers) != 1:
        raise ValueError('Frontline City scenario QA must emit exactly one report')
    report = json.loads(markers[0])
    _check_report(report)
    return report


def _run_scenario(command, stage):
    output = run_stage(command + ['--fixed-fps', '60', '--script', 'res://frontline_qa.gd'],
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
        if manifest.get('kind') != 'frontline' or 'frontline_qa' not in manifest:
            raise ValueError('Package manifest must describe a Frontline City build')
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
                raise ValueError(f'Required Frontline City package file is missing: {relative}')
        project_text = (package / 'project.godot').read_text(encoding='utf-8')
        scene_settings = [line for line in project_text.splitlines() if line.startswith('run/main_scene=')]
        if scene_settings != [f'run/main_scene="res://{MAIN_SCENE}"']:
            raise ValueError('Frontline City must be the package main scene')
        if READY not in (package / 'reports/launch.log').read_text(encoding='utf-8').splitlines():
            raise ValueError('Frontline City launch readiness is missing')

        report_path = package / REPORT
        scenario_path = package / SCENARIO_LOG
        report = manifest['frontline_qa']
        if report is not None:
            if spec != _fixture():
                raise ValueError('Frontline City scenario QA requires the exact shipped fixture')
            _check_report(report)
            if report != _read_json(report_path):
                raise ValueError('Frontline City scenario QA differs from the manifest')
            if report != _scenario_report(scenario_path.read_text(encoding='utf-8')):
                raise ValueError('Frontline City scenario QA differs from the execution log')
        elif report_path.exists() or scenario_path.exists():
            raise ValueError('Frontline City scenario QA is missing from the manifest')
        return []
    except (OSError, ValueError) as exc:
        return [str(exc)]


def build(spec_path, dest, godot='godot', *, frontline_qa=False):
    spec = validate(_read_json(Path(spec_path)))
    if frontline_qa and spec != _fixture():
        raise ValueError('--frontline-qa requires the exact shipped fixture')
    dest = Path(dest).absolute()
    resolved_dest = dest.resolve()
    runtime, tests, project = _sources()
    source_dirs = {path.parent for path in (*runtime, *tests, project)}
    if any(resolved_dest.is_relative_to(directory) for directory in source_dirs):
        raise ValueError('Output must be outside source directories')
    stage = factory.new_staging(dest)
    print('Frontline City staging:', stage, flush=True)
    try:
        reports = stage / 'reports'
        reports.mkdir()
        (stage / 'tests').mkdir()
        for path in runtime:
            shutil.copy2(path, stage / path.name)
        for path in tests:
            shutil.copy2(path, stage / 'tests' / path.name)
        project_text = project.read_text(encoding='utf-8')
        project_text = project_text.replace('Studio Frontier Lab', 'Studio Frontline City')
        project_text = project_text.replace('res://openworld.tscn', f'res://{MAIN_SCENE}')
        (stage / 'project.godot').write_text(project_text, encoding='utf-8')
        factory.write_json(stage / 'city.json', layout.generate(spec))

        command = [godot, '--headless', '--path', str(stage)]
        run_stage(command + ['--editor', '--import'], reports / 'import.log')
        run_stage(command + ['--quit-after', '10'], reports / 'launch.log', READY)
        for path in tests:
            run_stage(command + ['--script', f'res://tests/{path.name}'], reports / f'{path.stem}.log')
        report = _run_scenario(command, stage) if frontline_qa else None

        cache = stage / '.godot'
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
        factory.write_json(stage / 'manifest.json', {
            'schema': 1, 'status': 'passed', 'kind': 'frontline', 'spec': spec,
            'frontline_qa': report, 'files': factory.inventory(stage),
        })
        errors = verify(stage)
        if errors:
            raise ValueError('; '.join(errors))
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(f'Destination appeared during build: {dest}')
        stage.rename(dest)
        print('FRONTLINE_FACTORY_PASS', dest)
    except Exception:
        print('Frontline City build failed; diagnostics retained:', stage, file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', nargs='?', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--godot', default='godot')
    parser.add_argument('--frontline-qa', action='store_true', help='Run the full shipped Frontline City scenario')
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        problems = verify(args.verify.absolute())
        print('; '.join(problems) if problems else 'FRONTLINE_INTEGRITY_PASS')
        return int(bool(problems))
    if not args.spec or not args.output:
        parser.error('Specify a spec and --output, or --verify')
    build(args.spec, args.output, args.godot, frontline_qa=args.frontline_qa)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print('Frontline City factory:', exc, file=sys.stderr)
        sys.exit(1)
