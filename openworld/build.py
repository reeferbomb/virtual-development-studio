"""Build and verify a standalone streamed world and its actual Godot test evidence."""
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
from world.build import run_stage

FIELDS = {'seed', 'chunk_size', 'radius', 'capacity'}
COMPONENTS = ('streaming', 'population', 'inventory', 'factions', 'persistence')
MARKER = 'STUDIO_OPENWORLD_QA_JSON '


def validate(spec):
    if not isinstance(spec, dict) or set(spec) != FIELDS:
        raise ValueError('Open world requires seed, chunk_size, radius and capacity')
    for field, lo, hi in [('seed', 0, 2**31-1), ('chunk_size', 16, 64), ('radius', 1, 2), ('capacity', 1, 120)]:
        value = spec[field]
        if type(value) is not int or not lo <= value <= hi:
            raise ValueError(f'{field} must be an integer in {lo}..{hi}')
    return dict(spec)


def build(spec_path, dest, godot='godot', *, openworld_qa=False):
    spec = validate(json.loads(Path(spec_path).read_text(encoding='utf-8')))
    fixture = validate(json.loads((HERE / 'demo_spec.json').read_text(encoding='utf-8')))
    if openworld_qa and spec != fixture:
        raise ValueError('--openworld-qa requires the exact shipped fixture')
    dest = Path(dest).absolute()
    if any(dest.is_relative_to(HERE / part) for part in ('template', 'tests')):
        raise ValueError('Output must be outside source directories')
    files = [HERE / 'template' / name for name in (*[f'{part}.gd' for part in COMPONENTS], 'project.godot', 'openworld.gd', 'openworld.tscn', 'openworld_qa.gd')]
    tests = [HERE / 'tests' / f'test_{part}.gd' for part in COMPONENTS]
    if any(not path.is_file() for path in files + tests):
        raise ValueError('Required open-world runtime or component test is missing')
    stage = factory.new_staging(dest)
    print('Open world staging:', stage, flush=True)
    try:
        reports = stage / 'reports'
        reports.mkdir()
        (stage / 'tests').mkdir()
        for path in files:
            shutil.copy2(path, stage / path.name)
        for path in tests:
            shutil.copy2(path, stage / 'tests' / path.name)
        shutil.copy2(ROOT / 'world/template/player.gd', stage / 'player.gd')
        factory.write_json(stage / 'openworld.json', spec)
        cmd = [godot, '--headless', '--path', str(stage)]
        run_stage(cmd + ['--editor', '--import'], reports / 'import.log')
        run_stage(cmd + ['--quit-after', '10'], reports / 'launch.log', 'STUDIO_OPENWORLD_READY')
        fixed = cmd + ['--fixed-fps', '60']
        for path in tests:
            run_stage(fixed + ['--script', f'res://tests/{path.name}'], reports / f'{path.stem}.log')
        qa = None
        if openworld_qa:
            log = reports / 'openworld-qa.log'
            result = run_stage(fixed + ['--script', 'res://openworld_qa.gd'], log, MARKER)
            markers = [line[len(MARKER):] for line in result.splitlines() if line.startswith(MARKER)]
            if len(markers) != 1:
                raise ValueError('Open-world QA must emit exactly one report')
            qa = json.loads(markers[0])
            if not isinstance(qa, dict) or qa.get('pass') is not True or not isinstance(qa.get('checks'), list) or not qa['checks']:
                raise ValueError('Open-world QA did not pass')
            factory.write_json(reports / 'openworld-qa.json', qa)
            print(MARKER + json.dumps(qa, separators=(',', ':')), flush=True)
        cache = stage / '.godot'
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
        factory.write_json(stage / 'manifest.json', {'schema': 1, 'status': 'passed', 'kind': 'openworld', 'spec': spec, 'openworld_qa': qa, 'files': factory.inventory(stage)})
        if factory.verify_package(stage) or dest.exists() or dest.is_symlink():
            raise ValueError('Package verification or destination safety check failed')
        stage.rename(dest)
        print('OPENWORLD_FACTORY_PASS', dest)
    except Exception:
        print('Open-world build failed; diagnostics retained:', stage, file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', nargs='?', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--godot', default='godot')
    parser.add_argument('--openworld-qa', action='store_true')
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        problems = factory.verify_package(args.verify.absolute())
        print('; '.join(problems) if problems else 'OPENWORLD_INTEGRITY_PASS')
        return int(bool(problems))
    if not args.spec or not args.output:
        parser.error('Specify a spec and --output, or --verify')
    build(args.spec, args.output, args.godot, openworld_qa=args.openworld_qa)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print('Open-world factory:', exc, file=sys.stderr)
        sys.exit(1)
