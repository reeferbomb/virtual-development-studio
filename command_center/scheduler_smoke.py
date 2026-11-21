"""Exercise Studio's scheduler through a loopback server and a real Godot world build."""

import argparse
import json
import tempfile
import time
from pathlib import Path

from .checkpoint_smoke import _expect, _request, _running_service
from .provenance import spec_digest


def _create_project(port, name):
    return _request(port, '/api/projects', 'POST', {'name': name, 'kind': 'world'},
                    expected_status=201)


class Board:
    """A client retaining the revision and spec identity it actually observed."""

    def __init__(self, port, project_id):
        self.port = port
        self.project_route = f'/api/projects/{project_id}'
        self.route = self.project_route + '/tasks'
        self.state = _request(port, self.route)

    def _payload(self, seen, op, fields):
        return {'expected_revision': seen['revision'], 'spec_sha256': seen['spec_sha256'],
                'action': {'op': op, **fields}}

    def apply(self, op, **fields):
        previous = self.state
        self.state = _request(self.port, self.route, 'PUT', self._payload(previous, op, fields))
        _expect(self.state['revision'], previous['revision'] + 1, f'{op} revision')
        _expect(self.state['project_id'], previous['project_id'], f'{op} project identity')
        _expect(self.state['spec_sha256'], previous['spec_sha256'], f'{op} spec identity')
        return self.state

    def reject(self, op, *, status=400, seen=None, **fields):
        payload = self._payload(self.state if seen is None else seen, op, fields)
        response = _request(self.port, self.route, 'PUT', payload, expected_status=status)
        _expect(bool(response.get('error')), True, f'{op} rejection includes a reason')
        _expect(_request(self.port, self.route), self.state, f'Board after rejected {op}')
        return response['error']

    def add(self, task_id, title, role, priority, *, depends_on=(), gate='manual'):
        return self.apply('add', task={'id': task_id, 'title': title, 'role': role,
                                       'priority': priority, 'depends_on': list(depends_on),
                                       'gate': gate})

    def task(self, task_id):
        return next(task for task in self.state['tasks'] if task['id'] == task_id)


def check_workflow(workspace):
    with _running_service(workspace) as port:
        project = _create_project(port, 'Scheduler Workflow')
        project_id = project['id']
        board = Board(port, project_id)
        initial = board.state
        _expect((initial['project_id'], initial['spec_sha256'], initial['state'], initial['revision']),
                (project_id, spec_digest(project['spec']), 'empty', 0), 'New board identity')
        board.add('layout', 'Inspect the world layout', 'architecture', 4)
        board.add('terrain', 'Review terrain amplitude', 'architecture', 3)
        board.add('review', 'Verify the layout review', 'verification', 5, depends_on=['layout'])
        ready_before = board.state['ready_task_ids']
        _expect(ready_before, ['layout', 'terrain'], 'Ready order before the prerequisite finishes')
        _expect([a['task_id'] for a in board.state['assignments']], ['layout'],
                'Highest priority ready task for the idle architect')
        dependency_error = board.reject('start', task_id='review')
        board.reject('start', task_id='layout', status=409, seen=initial)
        board.apply('start', task_id='layout')
        role_error = board.reject('start', task_id='terrain')
        _expect(board.state['assignments'], [], 'Assignments while the only ready role is busy')

        board.apply('block', task_id='layout', reason='Waiting for the project spec review')
        _expect((board.task('layout')['status'], board.task('layout')['reason']),
                ('blocked', 'Waiting for the project spec review'), 'Blocked layout and reason')
        board.apply('requeue', task_id='layout')
        _expect(board.task('layout')['status'], 'pending', 'Requeued layout')
        board.apply('reassign', task_id='terrain', role='gameplay')
        reassigned_role = board.task('terrain')['role']
        _expect(reassigned_role, 'gameplay', 'Reassigned terrain review')
        board.apply('start', task_id='layout')
        evidence_error = board.reject('complete', task_id='layout', evidence=[])
        _expect(board.task('layout')['attempts'], 2, 'Both layout starts counted')
        board.apply('start', task_id='terrain')
        before_restart = board.state
        _expect(before_restart['summary']['running'], 2, 'Two distinct roles working concurrently')

    with _running_service(workspace) as port:
        board = Board(port, project_id)
        _expect(board.state, before_restart, 'Full board restored on service restart')
        evidence = ['Inspected spawn and goal positions in the saved world spec']
        board.apply('complete', task_id='layout', evidence=evidence)
        _expect(board.task('layout')['evidence'], evidence, 'Persisted completion evidence')
        ready_after = board.state['ready_task_ids']
        _expect(ready_after, ['review'], 'Review unlocked after completing its prerequisite')
        board.apply('start', task_id='review')
        board.apply('complete', task_id='review', evidence=['Compared the layout review to the spec'])
        board.apply('complete', task_id='terrain', evidence=['Read the saved terrain amplitude'])
        completed = board.state
        _expect(completed['summary']['completed'], 3, 'Completed task count')

        previous = board.add('followup', 'Review the final world', 'verification', 3)
        _expect(previous['ready_task_ids'], ['followup'], 'Ready work before the edit')
        board.reject('reset')
        project['spec']['terrain']['amplitude'] += 0.25
        edited = _request(port, board.project_route + '/spec', 'PUT', {'spec': project['spec']})
        board = Board(port, project_id)
        stale = board.state
        _expect(stale['state'], 'stale', 'Board after editing its project spec')
        _expect(stale['tasks'], previous['tasks'], 'Historical tasks on stale board')
        _expect(stale['spec_sha256'], spec_digest(edited['spec']), 'Edited spec identity')
        _expect(stale['board_spec_sha256'], completed['spec_sha256'], 'Historical board identity')
        _expect((stale['ready_task_ids'], stale['assignments']), ([], []), 'Stale work suppressed')
        _expect(stale['summary']['ready'], 0, 'Stale board has no dispatchable work')
        board.reject('start', task_id='followup', status=409)
        board.reject('reset', seen=previous, status=409)
        reset = board.apply('reset')
        _expect((reset['state'], reset['tasks'], reset['board_spec_sha256']),
                ('current', [], stale['spec_sha256']), 'Reset bound to edited specification')
        _expect(_request(port, board.route), reset, 'Reset persisted')

    return {'project_id': project_id, 'spec_sha256': initial['spec_sha256'],
            'ready_before_prerequisite': ready_before, 'ready_after_prerequisite': ready_after,
            'dependency_rejection': dependency_error, 'busy_role_rejection': role_error,
            'empty_evidence_rejection': evidence_error, 'reassigned_role': reassigned_role,
            'running_at_restart': before_restart['summary']['running'],
            'restored_revision': before_restart['revision'], 'completed_revision': completed['revision'],
            'completed_tasks': completed['summary']['completed'], 'revision_conflict_status': 409,
            'stale_state': stale['state'], 'reset_revision': reset['revision'],
            'reset_spec_sha256': reset['spec_sha256']}


def _verified_job(port, board):
    job = _request(port, board.project_route + '/build', 'POST', {}, expected_status=202)
    job_route = '/api/jobs/' + job['id']
    deadline = time.monotonic() + 180
    while job['status'] in ('queued', 'running'):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"World build {job['id']} did not finish in 180 seconds")
        time.sleep(0.25)
        job = _request(port, job_route)
    if job['status'] != 'passed' or job['verified'] is not True:
        log = _request(port, job_route + '/log')['log']
        raise RuntimeError(f"World build {job['id']} failed: {job['error']}\n{log}")
    _expect([(command['stage'], command['exit_code']) for command in job['commands']],
            [('build', 0), ('verify', 0)], 'Separate successful build and verification commands')
    return job


def check_build_gate(workspace):
    with _running_service(workspace) as port:
        project = _create_project(port, 'Scheduler Build Gate')
        board = Board(port, project['id'])
        board.add('release', 'Verify the generated world', 'build_operations', 5, gate='build')
        board.apply('start', task_id='release')
        evidence = ['Godot route QA and the world package integrity check passed']
        missing_ref = board.reject('complete', task_id='release', evidence=evidence)
        missing_job = board.reject('complete', task_id='release', evidence=evidence, job_id='0' * 32)
        job = _verified_job(port, board)
        snapshot_path = workspace / 'jobs' / job['id'] / 'spec.json'
        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
        current_spec = _request(port, board.project_route)['spec']
        _expect(snapshot, current_spec, 'Built snapshot equals live project specification')
        _expect((job['project_id'], job['spec_sha256']), (project['id'], spec_digest(current_spec)),
                'Verified job project and spec identity')
        _expect(job['spec_sha256'], board.state['spec_sha256'], 'Verified job belongs to current board')
        report = workspace / job['output'] / 'reports' / 'route-qa.json'
        route_qa = json.loads(report.read_text(encoding='utf-8'))
        _expect(route_qa['pass'], True, 'Generated world route QA')
        complete = {'task_id': 'release', 'evidence': evidence, 'job_id': job['id']}
        board.reject('complete', task_id='release', evidence=[], job_id=job['id'])
        board.apply('complete', **complete)
        finished = board.task('release')
        _expect((finished['status'], finished['job_id'], finished['evidence']),
                ('completed', job['id'], evidence), 'Build-backed completion')

        other = _create_project(port, 'Scheduler Other World')
        foreign = Board(port, other['id'])
        _expect(foreign.state['spec_sha256'], job['spec_sha256'], 'Control project has identical spec')
        foreign.add('release', 'Verify this world', 'build_operations', 5, gate='build')
        foreign.apply('start', task_id='release')
        foreign_error = foreign.reject('complete', **complete)

        current_spec['terrain']['amplitude'] += 0.25
        _request(port, board.project_route + '/spec', 'PUT', {'spec': current_spec})
        board = Board(port, project['id'])
        board.apply('reset')
        board.add('release', 'Verify the edited world', 'build_operations', 5, gate='build')
        board.apply('start', task_id='release')
        stale_error = board.reject('complete', **complete)
        _expect(board.task('release')['status'], 'running', 'Old job leaves new task open')

    return {'project_id': job['project_id'], 'job_id': job['id'], 'spec_sha256': job['spec_sha256'],
            'job_status': job['status'], 'verified': job['verified'], 'completed_task': finished['id'],
            'commands': [{'stage': c['stage'], 'exit_code': c['exit_code']} for c in job['commands']],
            'route_qa': route_qa, 'missing_reference_rejection': missing_ref,
            'unknown_job_rejection': missing_job, 'foreign_project_rejection': foreign_error,
            'obsolete_spec_rejection': stale_error}


def smoke(workspace):
    return {'status': 'passed', 'workflow': check_workflow(workspace),
            'build_gate': check_build_gate(workspace)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Also write the JSON report to this path')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='studio-scheduler-smoke-') as temporary:
        report = json.dumps(smoke(Path(temporary)), indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding='utf-8')
    print(report, end='')


if __name__ == '__main__':
    main()
