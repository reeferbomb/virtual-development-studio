"""Run a bounded, reproducible Living World multi-seed build/QA matrix."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import time

from . import build


def run_matrix(output: Path, specs: list[dict], workers: int = 2, godot: str = 'godot') -> dict:
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError('workers must be 1..4')
    if not 1 <= len(specs) <= 16:
        raise ValueError('matrix must contain 1..16 worlds')
    validated = [build.validate(spec) for spec in specs]
    fingerprints = [json.dumps(spec, sort_keys=True) for spec in validated]
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError('matrix contains duplicate specs')
    fixture = build.validate(json.loads((build.HERE / 'demo_spec.json').read_text()))
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)

    def execute(entry):
        index, spec = entry
        job = output / f'{index:02d}-seed-{spec["seed"]}'
        job.mkdir()
        spec_path = job / 'spec.json'
        spec_path.write_text(json.dumps(spec, indent=2) + '\n')
        package = job / 'project'
        args = [sys.executable, str(build.HERE / 'build.py'), str(spec_path), '--output', str(package), '--godot', godot]
        scenario = spec == fixture
        if scenario:
            args.append('--living-qa')
        start = time.monotonic()
        try:
            result = subprocess.run(args, text=True, capture_output=True, timeout=240)
            (job / 'build.log').write_text(result.stdout + result.stderr, encoding='utf-8')
            if result.returncode:
                raise RuntimeError(f'Builder exited {result.returncode}')
            errors = build.factory.verify_package(package)
            if errors:
                raise RuntimeError('; '.join(errors))
            manifest = json.loads((package / 'manifest.json').read_text())
            checks = manifest.get('living_qa')
            if scenario and (not isinstance(checks, dict) or checks.get('pass') is not True):
                raise RuntimeError('Expected fixture scenario evidence is absent')
            return {'spec': spec, 'status': 'passed', 'scenario': 'passed' if scenario else 'not_run',
                    'scenario_checks': len(checks['checks']) if scenario else 0, 'component_suites': len(build._sources()[1]),
                    'artifact': str(package.relative_to(output)), 'seconds': round(time.monotonic() - start, 3)}
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            return {'spec': spec, 'status': 'failed', 'scenario': 'unknown', 'error': str(exc),
                    'seconds': round(time.monotonic() - start, 3)}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(execute, enumerate(validated)))
    report = {'version': 1, 'pass': all(row['status'] == 'passed' for row in rows), 'workers': workers,
              'worlds': rows, 'scope': 'Headless import, launch, component suites and package integrity; exact fixture only runs scenario QA.'}
    build.factory.write_json(output / 'matrix-report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seeds', type=int, nargs='+', default=[237, 238, 239])
    parser.add_argument('--chunk-size', type=int, default=32)
    parser.add_argument('--radius', type=int, default=1)
    parser.add_argument('--capacity', type=int, default=40)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--godot', default='godot')
    args = parser.parse_args()
    specs = [{'seed': seed, 'chunk_size': args.chunk_size, 'radius': args.radius, 'capacity': args.capacity} for seed in args.seeds]
    try:
        result = run_matrix(args.output, specs, args.workers, args.godot)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Matrix: {exc}\n')
    print(json.dumps(result, indent=2))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
