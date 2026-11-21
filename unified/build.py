"""Build and verify a standalone Godot expedition with streamed-world systems."""
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
from openworld import build as openworld
from world.build import run_stage

COMPONENTS = ('transport', 'range_combat', 'scheduled_population', 'quests', 'economy')
MARKER = 'STUDIO_UNIFIED_QA_JSON '


def validate(spec):
    return openworld.validate(spec)


def _sources():
    base = ROOT / 'openworld'
    files = [base / 'template' / name for name in (
        'openworld.gd', *[f'{part}.gd' for part in openworld.COMPONENTS],
    )]
    files.extend(HERE / 'template' / name for name in (
        'unified.gd', 'unified.tscn', 'unified_qa.gd', *[f'{part}.gd' for part in COMPONENTS],
    ))
    files.extend((ROOT / 'simulation/template/vehicle.gd', ROOT / 'world/template/player.gd'))
    tests = [base / 'tests' / f'test_{part}.gd' for part in openworld.COMPONENTS]
    tests.extend(HERE / 'tests' / f'test_{part}.gd' for part in COMPONENTS)
    project = base / 'template/project.godot'
    for path in [*files, *tests, project]:
        if not path.is_file():
            raise ValueError(f'Required unified runtime or component test is missing: {path.relative_to(ROOT)}')
    return files, tests, project


def _run_scenario(command, reports):
    output = run_stage(command + ['--script', 'res://unified_qa.gd'], reports / 'unified-qa.log', MARKER)
    markers = [line.removeprefix(MARKER) for line in output.splitlines() if line.startswith(MARKER)]
    if len(markers) != 1:
        raise ValueError('Unified QA must emit exactly one report')
    report = json.loads(markers[0])
    if not isinstance(report, dict) or report.get('pass') is not True:
        raise ValueError('Unified QA did not pass')
    checks = report.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('Unified QA did not report its checks')
    factory.write_json(reports / 'unified-qa.json', report)
    print(MARKER + json.dumps(report, separators=(',', ':')), flush=True)
    return report


def build(spec_path, dest, godot='godot', *, unified_qa=False):
    spec = validate(json.loads(Path(spec_path).read_text(encoding='utf-8')))
    if unified_qa:
        fixture = validate(json.loads((HERE / 'demo_spec.json').read_text(encoding='utf-8')))
        if spec != fixture:
            raise ValueError('--unified-qa requires the exact shipped fixture')
    dest = Path(dest).absolute()
    resolved_dest = dest.resolve()
    if any(resolved_dest.is_relative_to(base / part) for base in (HERE, ROOT / 'openworld')
           for part in ('template', 'tests')):
        raise ValueError('Output must be outside source directories')
    files, tests, project = _sources()
    stage = factory.new_staging(dest)
    print('Unified expedition staging:', stage, flush=True)
    try:
        reports = stage / 'reports'
        reports.mkdir()
        (stage / 'tests').mkdir()
        for path in files:
            shutil.copy2(path, stage / path.name)
        for path in tests:
            shutil.copy2(path, stage / 'tests' / path.name)
        project_text = project.read_text(encoding='utf-8')
        project_text = project_text.replace('Studio Frontier Lab', 'Studio Unified Expedition')
        project_text = project_text.replace('res://openworld.tscn', 'res://unified.tscn')
        (stage / 'project.godot').write_text(project_text, encoding='utf-8')
        factory.write_json(stage / 'openworld.json', spec)
        command = [godot, '--headless', '--path', str(stage)]
        run_stage(command + ['--editor', '--import'], reports / 'import.log')
        run_stage(command + ['--quit-after', '10'], reports / 'launch.log', 'STUDIO_UNIFIED_READY')
        fixed = command + ['--fixed-fps', '60']
        for path in tests:
            run_stage(fixed + ['--script', f'res://tests/{path.name}'], reports / f'{path.stem}.log')
        report = _run_scenario(fixed, reports) if unified_qa else None
        cache = stage / '.godot'
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
        factory.write_json(stage / 'manifest.json', {
            'schema': 1, 'status': 'passed', 'kind': 'unified', 'spec': spec,
            'unified_qa': report, 'files': factory.inventory(stage),
        })
        errors = factory.verify_package(stage)
        if errors:
            raise ValueError('; '.join(errors))
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(f'Destination appeared during build: {dest}')
        stage.rename(dest)
        print('UNIFIED_FACTORY_PASS', dest)
    except Exception:
        print('Unified build failed; diagnostics retained:', stage, file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', nargs='?', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--godot', default='godot')
    parser.add_argument('--unified-qa', action='store_true')
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        problems = factory.verify_package(args.verify.absolute())
        print('; '.join(problems) if problems else 'UNIFIED_INTEGRITY_PASS')
        return int(bool(problems))
    if not args.spec or not args.output:
        parser.error('Specify a spec and --output, or --verify')
    build(args.spec, args.output, args.godot, unified_qa=args.unified_qa)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print('Unified factory:', exc, file=sys.stderr)
        sys.exit(1)
