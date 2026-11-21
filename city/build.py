"""Build and verify the standalone Metropolis Godot project."""
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
from world.build import run_stage

validate = layout.validate
COMPONENTS = ('traffic', 'civilians', 'city_network')
MARKER = 'STUDIO_CITY_QA_JSON '


def _read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _fixture():
    return validate(_read_json(HERE / 'demo_spec.json'))


def _sources():
    runtime = [
        ROOT / 'world/template/player.gd',
        ROOT / 'openworld/template/persistence.gd',
        *[HERE / 'template' / name for name in (
            'city.gd', 'city.tscn', 'city_qa.gd', *(f'{part}.gd' for part in COMPONENTS),
        )],
    ]
    tests = [HERE / 'tests' / f'test_{part}.gd' for part in COMPONENTS]
    project = ROOT / 'openworld/template/project.godot'
    for path in (*runtime, *tests, project):
        if not path.is_file():
            raise ValueError(f'Required city source is missing: {path.relative_to(ROOT)}')
    profile = HERE / 'template/city_profile.gd'
    if profile.is_file():
        runtime.append(profile)
    return runtime, tests, project


def _check_report(report):
    if not isinstance(report, dict) or report.get('pass') is not True:
        raise ValueError('City scenario QA did not pass')
    checks = report.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('City scenario QA did not report its checks')
    if any(not isinstance(check, dict) or check.get('status') != 'passed' for check in checks):
        raise ValueError('City scenario QA reported a check that did not pass')


def _run_scenario(command, reports):
    output = run_stage(command + ['--fixed-fps', '60', '--script', 'res://city_qa.gd'],
                       reports / 'city-qa.log', MARKER)
    markers = [line.removeprefix(MARKER) for line in output.splitlines() if line.startswith(MARKER)]
    if len(markers) != 1:
        raise ValueError('City scenario QA must emit exactly one report')
    report = json.loads(markers[0])
    _check_report(report)
    factory.write_json(reports / 'city-qa.json', report)
    print(MARKER + json.dumps(report, separators=(',', ':')), flush=True)
    return report


def verify(package):
    errors = factory.verify_package(package)
    if errors:
        return errors
    try:
        manifest = _read_json(package / 'manifest.json')
        if manifest.get('kind') != 'city' or 'city_qa' not in manifest:
            raise ValueError('Package manifest must describe a city build')
        spec = validate(manifest.get('spec'))
        generated = _read_json(package / 'city.json')
        layout.validate_layout(generated)
        if any(generated.get(key) != value for key, value in spec.items()):
            raise ValueError('City spec differs from the manifest')
        report_path = package / 'reports/city-qa.json'
        report = manifest['city_qa']
        if report is not None:
            _check_report(report)
            if report != _read_json(report_path):
                raise ValueError('City scenario QA differs from the manifest')
        elif report_path.exists():
            raise ValueError('City scenario QA is missing from the manifest')
        return []
    except (OSError, ValueError) as exc:
        return [str(exc)]


def build(spec_path, dest, godot='godot', *, city_qa=False):
    spec = validate(_read_json(Path(spec_path)))
    if city_qa and spec != _fixture():
        raise ValueError('--city-qa requires the exact shipped fixture')
    dest = Path(dest).absolute()
    resolved_dest = dest.resolve()
    sources = (HERE, ROOT / 'openworld', ROOT / 'world')
    if any(resolved_dest.is_relative_to(base / part) for base in sources for part in ('template', 'tests')):
        raise ValueError('Output must be outside source directories')
    runtime, tests, project = _sources()
    stage = factory.new_staging(dest)
    print('City staging:', stage, flush=True)
    try:
        reports = stage / 'reports'
        reports.mkdir()
        (stage / 'tests').mkdir()
        for path in runtime:
            shutil.copy2(path, stage / path.name)
        for path in tests:
            shutil.copy2(path, stage / 'tests' / path.name)
        project_text = project.read_text(encoding='utf-8')
        project_text = project_text.replace('Studio Frontier Lab', 'Studio Metropolis')
        project_text = project_text.replace('res://openworld.tscn', 'res://city.tscn')
        (stage / 'project.godot').write_text(project_text, encoding='utf-8')
        factory.write_json(stage / 'city.json', layout.generate(spec))

        command = [godot, '--headless', '--path', str(stage)]
        run_stage(command + ['--editor', '--import'], reports / 'import.log')
        run_stage(command + ['--quit-after', '10'], reports / 'launch.log', 'STUDIO_CITY_READY')
        for path in tests:
            run_stage(command + ['--script', f'res://tests/{path.name}'], reports / f'{path.stem}.log')
        report = _run_scenario(command, reports) if city_qa else None

        cache = stage / '.godot'
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
        factory.write_json(stage / 'manifest.json', {
            'schema': 1, 'status': 'passed', 'kind': 'city', 'spec': spec,
            'city_qa': report, 'files': factory.inventory(stage),
        })
        errors = verify(stage)
        if errors:
            raise ValueError('; '.join(errors))
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(f'Destination appeared during build: {dest}')
        stage.rename(dest)
        print('CITY_FACTORY_PASS', dest)
    except Exception:
        print('City build failed; diagnostics retained:', stage, file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', nargs='?', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--godot', default='godot')
    parser.add_argument('--city-qa', action='store_true')
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        problems = verify(args.verify.absolute())
        print('; '.join(problems) if problems else 'CITY_INTEGRITY_PASS')
        return int(bool(problems))
    if not args.spec or not args.output:
        parser.error('Specify a spec and --output, or --verify')
    build(args.spec, args.output, args.godot, city_qa=args.city_qa)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print('City factory:', exc, file=sys.stderr)
        sys.exit(1)
