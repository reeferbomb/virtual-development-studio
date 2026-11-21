"""Run the planning workflow with a real verified Godot build and restart."""
import argparse
import json
import tempfile
from pathlib import Path

from .checkpoint_smoke import _expect, _request, _running_service
from .orchestration_smoke import _release_action, _wait_job
from .provenance import spec_digest
from .scheduler_smoke import Board, _create_project
from .sprint_smoke import _apply_plan, _capture


def check_planning(workspace):
    with _running_service(workspace) as port:
        project = _create_project(port, 'Planning Fixture')
        root = '/api/projects/' + project['id']
        route = root + '/blueprint'
        board = Board(port, project['id'])
        _expect(_request(port, root + '/forecast')['status'], 'empty', 'Initial empty forecast')
        preview = _request(port, route)
        _expect(preview['status'], 'ready', 'Blueprint is available')
        _expect(_request(port, board.route), board.state, 'Planning preview is read-only')
        board.state = _apply_plan(port, route, preview)
        tasks = {t['role']: t['id'] for t in board.state['tasks']}
        _expect(len(tasks), 6, 'Every specialist has one task')
        _expect(board.state['revision'], 1, 'Single atomic blueprint mutation')
        _expect(all(t['status'] == 'pending' for t in board.state['tasks']), True, 'No automatic claims')
        _apply_plan(port, route, preview, 409)
        _expect(_request(port, board.route), board.state, 'Duplicate preview made no changes')
        _expect(_request(port, route)['status'], 'applied', 'Blueprint remains inspectable')

        initial_forecast = _request(port, root + '/forecast')
        _expect(initial_forecast['remaining_tasks'], 6, 'All tasks remaining')
        _expect(len(initial_forecast['waves']), 4, 'Four dependency waves')
        _expect(initial_forecast['unscheduled'], [], 'No initial blockers')

        def complete(role, evidence):
            identifier = tasks[role]
            board.apply('start', task_id=identifier)
            board.apply('complete', task_id=identifier, evidence=[evidence])

        complete('architecture', 'Inspected fixture specification and dependencies.')
        board.apply('start', task_id=tasks['content'])
        board.apply('block', task_id=tasks['content'], reason='Synthetic fixture blocker.')
        impact = _request(port, root + '/dependency-impact')
        _expect(impact['blocked'][0]['task_id'], tasks['content'], 'Direct blocked task')
        _expect({tasks['build_operations'], tasks['verification']}.issubset(impact['affected_task_ids']),
                True, 'Downstream build and verification affected')
        forecast = _request(port, root + '/forecast')
        _expect({tasks['content'], tasks['build_operations'], tasks['verification']}.issubset(forecast['unscheduled']),
                True, 'Blocked subtree is unschedulable')
        _expect(_request(port, root + '/preflight')['status'], 'blocked', 'Blocker stops preflight')
        board.apply('requeue', task_id=tasks['content'])
        for role in ('content', 'gameplay', 'ui'):
            complete(role, 'Synthetic fixture task reviewed by smoke controller.')
        _expect(_request(port, root + '/dependency-impact')['blocked'], [], 'Explicit recovery clears blocker')
        board.apply('start', task_id=tasks['build_operations'])
        job = _request(port, root + '/build', 'POST', {'priority': 5}, expected_status=202)
        done = _wait_job(port, job['id'])
        _expect((done['status'], done['verified']), ('passed', True), 'Verified real Godot build')
        board.apply('complete', task_id=tasks['build_operations'], evidence=['Verified fixture job.'], job_id=done['id'])
        _release_action(port, root + '/releases', _request(port, root + '/releases'),
                        {'op': 'promote', 'job_id': done['id']})
        complete('verification', 'Fixture verification and promoted package reviewed.')
        finished = _request(port, root + '/forecast')
        _expect((finished['remaining_tasks'], finished['waves'], finished['unscheduled']),
                (0, [], []), 'Completed forecast is empty')
        _expect(_request(port, root + '/preflight')['status'] != 'ready', True, 'Missing captured audit keeps release pending')
        history = root + '/evidence-history'
        _capture(port, history, _request(port, history), 'Reviewed the complete synthetic planning fixture.')
        preflight = _request(port, root + '/preflight')
        _expect(preflight['report_sha256'], spec_digest(preflight['report']), 'Preflight seal')
        _expect(preflight['status'], _request(port, root + '/dossier')['status'], 'Preflight agrees with current dossier')
        _expect(_request(port, board.route), board.state, 'Preflight did not change tasks')

    with _running_service(workspace) as port:
        _expect(_request(port, root + '/forecast'), finished, 'Completed forecast persists')
        _expect(_request(port, root + '/preflight'), preflight, 'Preflight persists across restart')
        project['spec']['terrain']['amplitude'] += .25
        _request(port, root + '/spec', 'PUT', {'spec': project['spec']})
        _expect(_request(port, route)['status'], 'blocked', 'Stale board blocks blueprint')
        _expect(_request(port, root + '/forecast')['status'], 'stale', 'Spec edit invalidates forecast')
        _expect(_request(port, root + '/preflight')['status'] != 'ready', True, 'Old build cannot release new spec')
    return {'planned_tasks': len(tasks), 'duplicate_apply_rejected': True,
            'blocker_propagated': True, 'verified_build': True, 'completed_forecast': True,
            'preflight_integrity': True, 'stale_preflight_rejected': True,
            'final_preflight_status': preflight['status']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='studio-planning-') as directory:
        report = {'status': 'passed', **check_planning(Path(directory))}
    rendered = json.dumps(report, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    print(rendered, end='')


if __name__ == '__main__':
    main()
