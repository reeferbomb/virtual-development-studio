"""Export the fixed integrated Godot project and optionally verify two isolated runs."""

import argparse
import json
from pathlib import Path
import sys

from cinematic.production.runner import _json_bytes, _output_path, _verify_original_files
from command_center.provenance import spec_digest
from gameplay.runtime_lab import runner as engine_runner


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / 'gameplay/integrated_lab/template'
FILES = ('main.tscn', 'project.godot', 'main.gd', 'session.gd', 'player.gd', 'yard.gd', 'hud.gd', 'qa.gd')
DOMAINS = ('integrated',)
CHECKS = {'integrated': ('movement', 'branch-platform', 'branch-stairs', 'world-consequence',
                         'hud-consistency', 'modal-input', 'retry-isolation', 'deterministic-replay')}
MARKER = b'GRAVEFORGE_INTEGRATED_QA '
SCOPE = ('Scripted headless Godot gameplay, interface state and deterministic replay of the fixed integrated project. '
         'Rendered quality, human enjoyment, device performance and release certification require separate evidence.')


def _parse_marker(raw, code, digest):
    return engine_runner._parse_marker(raw, code, digest, domains=DOMAINS, checks=CHECKS, marker=MARKER)


def run(output, *, engine=False):
    """Export reviewed source into a new private directory and return the report."""
    output = _output_path(output)
    inventory = engine_runner._export(output, template=TEMPLATE, files=FILES)
    digest = spec_digest(inventory)
    report = {'schema_version': 1, 'status': 'exported', 'files': inventory, 'source_sha256': digest,
              'runtime': {'status': 'not_requested', 'scope': SCOPE}}
    if engine:
        first = engine_runner._runtime(output, digest, parser=_parse_marker, scope=SCOPE)
        runtime = {'status': first['status'], 'scope': SCOPE, 'runs': [first]}
        try:
            _verify_original_files(output, inventory)
            if first['status'] == 'passed':
                second = engine_runner._runtime(output, digest, parser=_parse_marker, scope=SCOPE,
                                                log_name='qa-repeat.log')
                runtime['runs'].append(second)
                _verify_original_files(output, inventory)
                if second['status'] != 'passed':
                    runtime.update(status=second['status'], reason='Independent repeat did not pass.')
                elif (first['godot_version'] != second['godot_version']
                      or _json_bytes(first['qa']) != _json_bytes(second['qa'])):
                    runtime.update(status='failed', reason='Independent engine runs produced different observations.')
                else:
                    runtime.update(status='passed', repeat_sha256=spec_digest(first['qa']))
        except ValueError as exc:
            runtime.update(status='failed', reason=str(exc))
        report.update(status=runtime['status'], runtime=runtime)
    (output / 'reports/report.json').write_bytes(_json_bytes(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='new private directory outside the checkout')
    parser.add_argument('--engine', action='store_true', help='explicitly run two isolated fixed Godot QA runs')
    args = parser.parse_args(argv)
    try:
        report = run(args.output, engine=args.engine)
    except (ValueError, OSError):
        print(json.dumps({'status': 'unavailable', 'reason': 'Export requires a new private directory and trusted template files.'}))
        return 2
    print(json.dumps(report, ensure_ascii=True, allow_nan=False))
    return {'exported': 0, 'passed': 0, 'failed': 1, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    sys.exit(main())
