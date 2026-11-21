"""Build and verify the standalone Living World Godot project."""
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
from factory import build as factory
from unified import build as unified
from world.build import run_stage

COMPONENTS = ('encounters', 'diplomacy', 'contracts', 'character_animator')
MARKER = 'STUDIO_LIVING_QA_JSON '


def validate(spec):
    checked = unified.validate(spec)
    if checked['capacity'] < 3:
        raise ValueError('capacity must be an integer in 3..120')
    return checked


def _sources():
    files, tests, project = unified._sources()
    runtime = [HERE / 'template' / name for name in (
        'living.gd', 'living.tscn', 'living_qa.gd', *[f'{part}.gd' for part in COMPONENTS],
    )]
    component_tests = [HERE / 'tests' / f'test_{part}.gd' for part in COMPONENTS]
    for path in runtime + component_tests:
        if not path.is_file():
            raise ValueError(f'Required living runtime or component test is missing: {path.relative_to(ROOT)}')
    return files + runtime, tests + component_tests, project


def _run_scenario(command, reports):
    output = run_stage(command + ['--script', 'res://living_qa.gd'], reports / 'living-qa.log', MARKER)
    markers = [line.removeprefix(MARKER) for line in output.splitlines() if line.startswith(MARKER)]
    if len(markers) != 1:
        raise ValueError('Living World QA must emit exactly one report')
    report = json.loads(markers[0])
    if not isinstance(report, dict) or report.get('pass') is not True:
        raise ValueError('Living World QA did not pass')
    checks = report.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('Living World QA did not report its checks')
    if any(not isinstance(check, dict) or check.get('status') != 'passed' for check in checks):
        raise ValueError('Living World QA reported a check that did not pass')
    factory.write_json(reports / 'living-qa.json', report)
    print(MARKER + json.dumps(report, separators=(',', ':')), flush=True)
    return report


def build(spec_path, dest, godot='godot', *, living_qa=False):
    spec = validate(json.loads(Path(spec_path).read_text(encoding='utf-8')))
    if living_qa:
        fixture = validate(json.loads((HERE / 'demo_spec.json').read_text(encoding='utf-8')))
        if spec != fixture:
            raise ValueError('--living-qa requires the exact shipped fixture')
    dest = Path(dest).absolute()
    resolved_dest = dest.resolve()
    sources = (HERE, ROOT / 'unified', ROOT / 'openworld', ROOT / 'simulation', ROOT / 'world')
    if any(resolved_dest.is_relative_to(base / part) for base in sources for part in ('template', 'tests')):
        raise ValueError('Output must be outside source directories')
    files, tests, project = _sources()
    stage = factory.new_staging(dest)
    print('Living World staging:', stage, flush=True)
    try:
        reports = stage / 'reports'
        reports.mkdir()
        (stage / 'tests').mkdir()
        for path in files:
            shutil.copy2(path, stage / path.name)
        for path in tests:
            shutil.copy2(path, stage / 'tests' / path.name)
        project_text = project.read_text(encoding='utf-8')
        project_text = project_text.replace('Studio Frontier Lab', 'Studio Living World')
        project_text = project_text.replace('res://openworld.tscn', 'res://living.tscn')
        (stage / 'project.godot').write_text(project_text, encoding='utf-8')
        factory.write_json(stage / 'openworld.json', spec)
        command = [godot, '--headless', '--path', str(stage)]
        run_stage(command + ['--editor', '--import'], reports / 'import.log')
        run_stage(command + ['--quit-after', '10'], reports / 'launch.log', 'STUDIO_LIVING_READY')
        fixed = command + ['--fixed-fps', '60']
        for path in tests:
            run_stage(fixed + ['--script', f'res://tests/{path.name}'], reports / f'{path.stem}.log')
        report = _run_scenario(fixed, reports) if living_qa else None
        cache = stage / '.godot'
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
        factory.write_json(stage / 'manifest.json', {
            'schema': 1, 'status': 'passed', 'kind': 'living', 'spec': spec,
            'living_qa': report, 'files': factory.inventory(stage),
        })
        errors = factory.verify_package(stage)
        if errors:
            raise ValueError('; '.join(errors))
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(f'Destination appeared during build: {dest}')
        stage.rename(dest)
        print('LIVING_FACTORY_PASS', dest)
    except Exception:
        print('Living World build failed; diagnostics retained:', stage, file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', nargs='?', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--godot', default='godot')
    parser.add_argument('--living-qa', action='store_true')
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        problems = factory.verify_package(args.verify.absolute())
        print('; '.join(problems) if problems else 'LIVING_INTEGRITY_PASS')
        return int(bool(problems))
    if not args.spec or not args.output:
        parser.error('Specify a spec and --output, or --verify')
    build(args.spec, args.output, args.godot, living_qa=args.living_qa)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print('Living World factory:', exc, file=sys.stderr)
        sys.exit(1)
