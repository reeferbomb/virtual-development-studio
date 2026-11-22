"""Export and twice verify original deterministic living-world Godot fixtures."""

import argparse
import json
from pathlib import Path
import sys

from cinematic.production.runner import _json_bytes, _output_path, _verify_original_files
from command_center.provenance import spec_digest
from gameplay.runtime_lab import runner as engine_runner


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / 'gameplay/world_lab/template'
DOMAINS = ('decision', 'squad', 'encounters', 'journal', 'citizens', 'missions')
FILES = ('project.godot', 'qa.gd', *(f'{domain}.gd' for domain in DOMAINS))
CHECKS = {
    'decision': ('observed-goals', 'utility-ties', 'switch-margin', 'survival-preemption', 'memory-bounds',
                 'route-fallback', 'route-recovery', 'goal-completion'),
    'squad': ('role-work', 'slot-deconfliction', 'path-continuity', 'local-observation',
              'observation-expiry', 'pressure-recovery', 'disabled-handoff'),
    'encounters': ('seeded-choice', 'warning-window', 'spawn-eligibility', 'arrival-recheck',
                   'wave-budget', 'cooldown', 'sequence-recovery', 'deterministic-reset'),
    'journal': ('discovery-gating', 'branch-exclusivity', 'optional-tracking', 'focus-reconciliation',
                'failure-guidance', 'retry-reset', 'completion', 'handheld-layout'),
    'citizens': ('day-night-schedule', 'routed-commutes', 'service-capacity', 'weather-disruption',
                 'gradual-catch-up', 'district-consequences', 'deterministic-replay'),
    'missions': ('seeded-replay', 'route-variation', 'dependency-validation', 'route-reachability',
                 'resource-budget', 'mission-progression', 'bounded-recovery', 'probe-cleanup'),
}
MARKER = b'GRAVEFORGE_WORLD_QA '
SCOPE = ('Fixed original Godot headless gameplay simulations, not rendered visual quality, '
         'real-player experience, hardware performance or release certification.')


def _parse_marker(raw, code, digest):
    return engine_runner._parse_marker(raw, code, digest, domains=DOMAINS, checks=CHECKS, marker=MARKER)


def run(output, *, engine=False):
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
                elif first['godot_version'] != second['godot_version'] or first['qa'] != second['qa']:
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
