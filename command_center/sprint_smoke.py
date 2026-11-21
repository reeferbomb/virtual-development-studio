"""Exercise v23 planning and history with an actual build in a disposable workspace."""
import argparse
import json
import tempfile
from pathlib import Path

from .checkpoint_smoke import _expect, _request, _running_service
from .orchestration_smoke import _wait_job
from .scheduler_smoke import _create_project
from .supervisor_smoke import _defect_action


def _apply_plan(port, route, plan, status=200):
    return _request(port, route, 'POST', {'expected_revision': plan['board_revision'],
                    'spec_sha256': plan['spec_sha256'], 'plan_id': plan['plan_id']}, expected_status=status)


def _capture(port, route, history, note, status=200):
    return _request(port, route, 'POST', {'expected_revision': history['revision'],
                    'spec_sha256': history['spec_sha256'], 'note': note}, expected_status=status)


def check_sprint(workspace):
    with _running_service(workspace) as port:
        project = _create_project(port, 'Sprint Acceptance Yard')
        root = f'/api/projects/{project["id"]}'
        sprint, history = root + '/sprint', root + '/evidence-history'
        board, defects = root + '/tasks', root + '/defects'
        initial_board = _request(port, board)
        preview = _request(port, sprint)
        _expect(preview['status'], 'ready', 'Initial sprint is actionable')
        _expect(_request(port, sprint), preview, 'Stable preview')
        _expect(_request(port, board), initial_board, 'Preview does not mutate board')
        initial_history = _request(port, history)
        _expect(initial_history['items'], [], 'Project has no invented audit history')
        first = _capture(port, history, initial_history, 'Initial smoke fixture; no prior build.')
        _expect(first['items'][0]['status'], 'pending', 'Captured initial audit')
        _expect(_request(port, sprint), preview, 'History-only capture does not change the plan')
        _capture(port, history, initial_history, 'Stale capture', 409)
        defect = _defect_action(port, defects, _request(port, defects), {
            'op': 'add', 'title': 'Smoke fixture defect', 'severity': 'critical',
            'description': 'Synthetic acceptance blocker, not a real gameplay defect.',
            'evidence': ['Synthetic fixture recorded to verify replanning.']})
        _expect(_request(port, root + '/acceptance')['status'], 'blocked', 'Critical defect blocks readiness')
        changed = _request(port, sprint)
        _expect(changed['plan_id'] != preview['plan_id'], True, 'Evidence changes plan identity')
        _apply_plan(port, sprint, preview, 409)
        _expect(_request(port, board), initial_board, 'Stale preview has no side effect')
        applied = _apply_plan(port, sprint, changed)
        _expect(applied['revision'], initial_board['revision'] + 1, 'One atomic board write')
        _expect({t['id'] for t in applied['tasks']}, {t['id'] for t in changed['tasks']}, 'Exact preview tasks added')
        _expect(all(t['status'] == 'pending' for t in applied['tasks']), True, 'No task claimed by preview application')
        _apply_plan(port, sprint, changed, 409)
        _expect(_request(port, board), applied, 'Duplicate plan apply cannot change board')
        second = _capture(port, history, first, 'Observed critical defect and applied plan, no tasks claimed.')
        _expect(second['items'][0]['status'], 'blocked', 'Captured blocked audit')
        _expect(second['items'][1], first['items'][0], 'Prior snapshot is immutable')
        job = _request(port, root + '/build', 'POST', {'priority': 5}, expected_status=202)
        job = _wait_job(port, job['id'])
        _expect((job['status'], job['verified']), ('passed', True), 'Actual verified Godot build')
        _expect(_request(port, root + '/acceptance')['status'], 'blocked', 'Build cannot override open defect')
        _defect_action(port, defects, defect, {'op': 'resolve', 'defect_id': defect['items'][0]['id'],
                                             'evidence': ['Cleared synthetic fixture after verifying blocker behavior.']})

    with _running_service(workspace) as port:
        _expect(_request(port, history), second, 'History persisted across restart')
        _expect(_request(port, board), applied, 'Atomic plan persisted across restart')
        _expect(_request(port, root + '/acceptance')['status'] != 'ready', True, 'Still missing acceptance evidence')
        project['spec']['terrain']['amplitude'] += .25
        _request(port, root + '/spec', 'PUT', {'spec': project['spec']})
        historical = _request(port, history)
        _expect(historical['items'], second['items'], 'Prior spec snapshots remain immutable')
        _expect(historical['spec_sha256'] != second['spec_sha256'], True, 'New specification digest')
        _expect(_request(port, sprint)['status'], 'blocked', 'Stale board must be reviewed before planning')
        _capture(port, history, second, 'Old specification cannot capture', 409)
        _expect(_request(port, root + '/acceptance')['status'] != 'ready', True, 'Historical evidence cannot accept new spec')
    return {'status': 'passed', 'planned_tasks': len(applied['tasks']), 'plan_id': changed['plan_id'],
            'stale_preview_rejected': True, 'old_snapshot_status': first['items'][0]['status'],
            'blocked_snapshot_status': second['items'][0]['status'], 'build_verified': job['verified'],
            'build_job_id': job['id'], 'historical_snapshots': len(historical['items']),
            'historical_capture_rejected': True, 'board_revision': applied['revision']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='studio-sprint-') as path:
        result = check_sprint(Path(path))
    report = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(report, encoding='utf-8')
    print(report, end='')


if __name__ == '__main__':
    main()
