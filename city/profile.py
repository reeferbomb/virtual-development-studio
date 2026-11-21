"""Profile verified city packages without changing the packages themselves."""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from . import build


MARKER = 'STUDIO_CITY_PROFILE_JSON '


def profile_package(package: Path, godot: str = 'godot') -> dict:
    package = Path(package).resolve()
    errors = build.verify(package)
    if errors:
        raise ValueError('Invalid city package: ' + '; '.join(errors))
    if not (package / 'city_profile.gd').is_file():
        raise ValueError('Package does not include the city profiler')
    with tempfile.TemporaryDirectory(prefix='city-profile-') as tmp:
        project = Path(tmp) / 'project'
        shutil.copytree(package, project)
        command = [godot, '--headless', '--path', str(project)]
        prepare = subprocess.run(command + ['--editor', '--import'], text=True, capture_output=True, timeout=120)
        if prepare.returncode:
            raise ValueError('City profiler import failed: ' + prepare.stderr[-1000:])
        result = subprocess.run(command + ['--fixed-fps', '60', '--script', 'res://city_profile.gd'], text=True, capture_output=True, timeout=120)
        rows = [line.removeprefix(MARKER) for line in result.stdout.splitlines() if line.startswith(MARKER)]
        if result.returncode or len(rows) != 1:
            raise ValueError('City profiler failed: ' + result.stderr[-1000:])
        data = json.loads(rows[0])
        values = [data.get(k) for k in ('mean_ms', 'p50_ms', 'p95_ms', 'p99_ms', 'max_ms')]
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values) or data.get('samples') != 600:
            raise ValueError('Invalid profiling measurements')
        if not values[1] <= values[2] <= values[3] <= values[4]:
            raise ValueError('Invalid profiling percentiles')
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packages', type=Path, nargs='+')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--godot', default='godot')
    args = parser.parse_args()
    if not 1 <= len(args.packages) <= 4:
        parser.error('Profile between one and four packages')
    if args.output and args.output.exists():
        parser.error('Output file already exists')
    try:
        report = {'version': 1, 'scope': 'Local headless CPU callback measurements only, not GPU or device benchmarks.',
                  'profiles': [profile_package(path, args.godot) for path in args.packages]}
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            build.factory.write_json(args.output, report)
        print(json.dumps(report, indent=2))
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f'City profiler: {exc}\n')


if __name__ == '__main__':
    main()
