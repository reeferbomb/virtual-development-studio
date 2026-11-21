"""Build and verify the standalone Vertical City Godot project."""
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
from city import build as city_builder, layout
from factory import build as factory
from world.build import run_stage

validate = layout.validate
COMPONENTS = ('interiors', 'transit', 'demolition', 'world_sync')
READY = 'STUDIO_VERTICAL_READY'
MARKER = 'STUDIO_VERTICAL_QA_JSON '
REPORT = 'reports/vertical-qa.json'


def _read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _fixture():
    return validate(_read_json(HERE / 'demo_spec.json'))


def _sources():
    runtime, tests, project = city_builder._sources()
    vertical_runtime = [HERE / 'template' / name for name in (
        'vertical.gd', 'vertical.tscn', 'vertical_qa.gd', *(f'{part}.gd' for part in COMPONENTS),
    )]
    vertical_tests = [HERE / 'tests' / f'test_{part}.gd' for part in COMPONENTS]
    for path in (*vertical_runtime, *vertical_tests):
        if not path.is_file():
            raise ValueError(f'Required Vertical City source is missing: {path.relative_to(ROOT)}')
    return runtime + vertical_runtime, tests + vertical_tests, project


def _check_report(report):
    if not isinstance(report, dict) or report.get('pass') is not True:
        raise ValueError('Vertical City scenario QA did not pass')
    checks = report.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('Vertical City scenario QA did not report its checks')
    if any(not isinstance(check, dict) or check.get('status') != 'passed' for check in checks):
        raise ValueError('Vertical City scenario QA reported a check that did not pass')


def _run_scenario(command, stage):
    output = run_stage(command + ['--fixed-fps', '60', '--script', 'res://vertical_qa.gd'],
                       stage / 'reports/vertical-qa.log', MARKER)
    markers = [line.removeprefix(MARKER) for line in output.splitlines() if line.startswith(MARKER)]
    if len(markers) != 1:
        raise ValueError('Vertical City scenario QA must emit exactly one report')
    report = json.loads(markers[0])
    _check_report(report)
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
        if manifest.get('kind') != 'vertical' or 'vertical_qa' not in manifest:
            raise ValueError('Package manifest must describe a Vertical City build')
        spec = validate(manifest.get('spec'))
        generated = _read_json(package / 'city.json')
        layout.validate_layout(generated)
        if any(generated.get(key) != value for key, value in spec.items()):
            raise ValueError('City layout differs from the manifest spec')
        report_path = package / REPORT
        report = manifest['vertical_qa']
        if report is not None:
            if spec != _fixture():
                raise ValueError('Vertical City scenario QA requires the exact shipped fixture')
            _check_report(report)
            if report != _read_json(report_path):
                raise ValueError('Vertical City scenario QA differs from the manifest')
        elif report_path.exists():
            raise ValueError('Vertical City scenario QA is missing from the manifest')
        return []
    except (OSError, ValueError) as exc:
        return [str(exc)]


def build(spec_path, dest, godot='godot', *, vertical_qa=False):
    spec = validate(_read_json(Path(spec_path)))
    if vertical_qa and spec != _fixture():
        raise ValueError('--vertical-qa requires the exact shipped fixture')
    dest = Path(dest).absolute()
    resolved_dest = dest.resolve()
    sources = (HERE, ROOT / 'city', ROOT / 'openworld', ROOT / 'world')
    if any(resolved_dest.is_relative_to(base / part) for base in sources for part in ('template', 'tests')):
        raise ValueError('Output must be outside source directories')
    runtime, tests, project = _sources()
    stage = factory.new_staging(dest)
    print('Vertical City staging:', stage, flush=True)
    try:
        reports = stage / 'reports'
        reports.mkdir()
        (stage / 'tests').mkdir()
        for path in runtime:
            shutil.copy2(path, stage / path.name)
        for path in tests:
            shutil.copy2(path, stage / 'tests' / path.name)
        project_text = project.read_text(encoding='utf-8')
        project_text = project_text.replace('Studio Frontier Lab', 'Studio Vertical City')
        project_text = project_text.replace('res://openworld.tscn', 'res://vertical.tscn')
        (stage / 'project.godot').write_text(project_text, encoding='utf-8')
        factory.write_json(stage / 'city.json', layout.generate(spec))

        command = [godot, '--headless', '--path', str(stage)]
        run_stage(command + ['--editor', '--import'], reports / 'import.log')
        run_stage(command + ['--quit-after', '10'], reports / 'launch.log', READY)
        for path in tests:
            run_stage(command + ['--script', f'res://tests/{path.name}'], reports / f'{path.stem}.log')
        report = _run_scenario(command, stage) if vertical_qa else None

        cache = stage / '.godot'
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
        factory.write_json(stage / 'manifest.json', {
            'schema': 1, 'status': 'passed', 'kind': 'vertical', 'spec': spec,
            'vertical_qa': report, 'files': factory.inventory(stage),
        })
        errors = verify(stage)
        if errors:
            raise ValueError('; '.join(errors))
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(f'Destination appeared during build: {dest}')
        stage.rename(dest)
        print('VERTICAL_FACTORY_PASS', dest)
    except Exception:
        print('Vertical City build failed; diagnostics retained:', stage, file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', nargs='?', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--godot', default='godot')
    parser.add_argument('--vertical-qa', action='store_true', help='Run the full shipped Vertical City scenario')
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        problems = verify(args.verify.absolute())
        print('; '.join(problems) if problems else 'VERTICAL_INTEGRITY_PASS')
        return int(bool(problems))
    if not args.spec or not args.output:
        parser.error('Specify a spec and --output, or --verify')
    build(args.spec, args.output, args.godot, vertical_qa=args.vertical_qa)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print('Vertical City factory:', exc, file=sys.stderr)
        sys.exit(1)
