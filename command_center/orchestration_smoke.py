"""Exercise v21 orchestration over the local HTTP API and a real Godot build."""
import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

from .checkpoint_smoke import _expect, _request, _running_service
from .pipeline import Pipeline
from .projects import ProjectStore
from .scheduler_smoke import Board, _create_project


def check_portfolio(workspace):
    with _running_service(workspace) as port:
        alpha = _create_project(port, 'Portfolio Alpha')
        beta = _create_project(port, 'Portfolio Beta')
        a, b = Board(port, alpha['id']), Board(port, beta['id'])
        a.add('plan', 'Plan the shared world', 'architecture', 2)
        b.add('plan', 'Plan the priority world', 'architecture', 5)
        a.add('review', 'Review the world', 'verification', 3)
        plan = _request(port, '/api/portfolio')
        architect = next(x for x in plan['assignments'] if x['role'] == 'architecture')
        _expect(architect['project_id'], beta['id'], 'Highest priority across projects')
        _expect(architect['board_revision'], b.state['revision'], 'Portfolio revision')
        _expect(architect['spec_sha256'], b.state['spec_sha256'], 'Portfolio spec')
        _expect(architect['model_id'], 'gpt-6.2-astra', 'Canonical specialist model')
        dispatch = plan['dispatch_plan']
        _expect(dispatch['assignments'], plan['assignments'], 'Export contains exactly recommended assignments')
        _expect(dispatch['execution_mode'], 'export_only', 'Portfolio cannot launch agents')
        spawn = next(x for x in dispatch['spawn_args'] if x['task_name'] == 'count_blueprint')
        _expect(beta['id'] in spawn['message'] and b.state['spec_sha256'] in spawn['message'], True,
                'Dispatch carries project and specification identity')
        b.apply('start', task_id='plan')
        occupied = _request(port, '/api/portfolio')
        roles = [x['role'] for x in occupied['assignments']]
        _expect('architecture' in roles, False, 'No duplicate architecture recommendation')
        _expect('architecture' in occupied['occupied_roles'], True, 'Global role occupancy')
        _expect('count_blueprint' in [x['task_name'] for x in occupied['dispatch_plan']['spawn_args']], False,
                'Occupied role withheld from export')
        b.apply('complete', task_id='plan', evidence=['Reviewed the terrain and route specification.'])
        next_plan = _request(port, '/api/portfolio')
        successor = next(x for x in next_plan['assignments'] if x['role'] == 'architecture')
        _expect(successor['project_id'], alpha['id'], 'Next eligible project')
    return {'winning_project': architect['project_id'], 'roles_after_claim': roles,
            'recovered_project': successor['project_id'], 'dispatch_identity_verified': True}


def check_queue(workspace):
    """Hold a controlled fixture builder so queue order can be observed without races."""
    root, storage = workspace / 'fixture-builder', workspace / 'fixture-workspace'
    builder = root / 'multiplayer' / 'build.py'
    builder.parent.mkdir(parents=True)
    builder.write_text('''import pathlib, sys, time
out = pathlib.Path(sys.argv[-1])
if '--verify' in sys.argv:
    sys.exit(0 if (out / 'manifest.json').is_file() else 1)
gate = pathlib.Path(__file__).parents[1] / 'allow'
end = time.monotonic() + 30
while not gate.exists():
    if time.monotonic() >= end:
        sys.exit(2)
    time.sleep(.01)
out.mkdir()
(out / 'manifest.json').write_text('{}')
''')
    projects = ProjectStore(root, storage)
    directories = [projects.directory(projects.create(name, 'multiplayer')['id'])
                   for name in ('Queue Blocker', 'Queue Low', 'Queue High', 'Queue Retry')]
    pipeline = Pipeline(root, storage)
    gate = root / 'allow'
    try:
        blocker = pipeline.submit(directories[0])
        end = time.monotonic() + 10
        while pipeline.get(blocker['id'])['status'] != 'running':
            if time.monotonic() >= end:
                raise RuntimeError('Fixture builder failed to enter running state')
            time.sleep(.01)
        low = pipeline.submit(directories[1], priority=1)
        high = pipeline.submit(directories[2], priority=5)
        canceled = pipeline.submit(directories[3], priority=4)
        _expect(pipeline.cancel(canceled['id'])['status'], 'canceled', 'Cancel queued job')
        retried = pipeline.retry(canceled['id'])
        _expect(retried['retry_of'], canceled['id'], 'Retry retains source identity')
        _expect(retried['id'] != canceled['id'], True, 'Retry creates independent job')
        snapshot = pipeline.queue()
        priorities = [job['priority'] for job in snapshot['queued']]
        _expect(priorities, [5, 4, 1], 'Priority dispatch order')
        _expect(snapshot['running']['id'], blocker['id'], 'Running build is not preempted')
        gate.touch()
        end = time.monotonic() + 15
        while pipeline.queue()['counts']['queued'] or pipeline.queue()['counts']['running']:
            if time.monotonic() >= end:
                raise RuntimeError('Fixture queue did not drain')
            time.sleep(.02)
        ordered = sorted((pipeline.get(j['id']) for j in (low, high, retried)), key=lambda j: j['started_at'])
        completed_order = [j['priority'] for j in ordered]
        _expect(completed_order, priorities, 'Actual serial execution order')
        counts = pipeline.queue()['counts']
        _expect(counts['passed'], 4, 'All four fixture builds passed')
        _expect(counts['canceled'], 1, 'Cancelled source remains in history')
    finally:
        gate.touch(exist_ok=True)
        pipeline.worker.shutdown(wait=True)
    return {'queued_priorities': priorities, 'completion_order': completed_order,
            'canceled': counts['canceled'], 'passed': counts['passed'],
            'retry_links_source': True, 'fixture': 'Controlled lightweight builder'}


def _wait_job(port, job_id):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        state = _request(port, f'/api/jobs/{job_id}')
        if state['status'] not in ('queued', 'running'):
            return state
        time.sleep(.1)
    raise RuntimeError('Timed out waiting for the real world build')


def _release_action(port, route, snapshot, action, status=200):
    return _request(port, route, 'PUT', {'expected_revision': snapshot['revision'],
                    'spec_sha256': snapshot['spec_sha256'], 'action': action}, expected_status=status)


def check_release(workspace):
    with _running_service(workspace) as port:
        project = _create_project(port, 'Release Acceptance')
        project_route = f'/api/projects/{project["id"]}'
        route = project_route + '/releases'
        initial = _request(port, route)
        _expect((initial['revision'], initial['active_state']), (0, 'empty'), 'Initial register')
        job = _request(port, project_route + '/build', 'POST', {'priority': 5}, expected_status=202)
        done = _wait_job(port, job['id'])
        _expect((done['status'], done['verified'], done['priority']), ('passed', True, 5), 'Verified priority job')
        _expect([c['exit_code'] for c in done['commands']], [0, 0], 'Real builder and verifier')
        queue = _request(port, '/api/queue')
        _expect(queue['counts']['passed'], 1, 'Queue counts verified job')
        promoted = _release_action(port, route, initial, {'op': 'promote', 'job_id': job['id']})
        release = promoted['releases'][0]
        _expect((promoted['active_state'], promoted['active_release_id']), ('current', release['id']), 'Promoted release')
        _expect(release['job_id'], job['id'], 'Release retains actual builder identity')
        package = workspace / done['output']
        manifest = package / 'manifest.json'
        _expect(release['manifest_sha256'], hashlib.sha256(manifest.read_bytes()).hexdigest(), 'Release manifest seal')
        _expect(release['manifest_sha256'], done['manifest_sha256'], 'Original build seal matches promotion')
        _release_action(port, route, initial, {'op': 'promote', 'job_id': job['id']}, 409)
        other = _create_project(port, 'Wrong Release Project')
        other_route = f'/api/projects/{other["id"]}/releases'
        other_initial = _request(port, other_route)
        _release_action(port, other_route, other_initial, {'op': 'promote', 'job_id': job['id']}, 400)
        _expect(_request(port, other_route), other_initial, 'Foreign promotion left registry unchanged')

    with _running_service(workspace) as port:
        restored = _request(port, route)
        _expect(restored, promoted, 'Release history after restart')
        # Corrupt a single disposable generated asset, then restore it for the stale-spec check.
        asset = package / json.loads(manifest.read_text())['files'][0]['path']
        original = asset.read_bytes()
        try:
            asset.write_bytes(original + b'\ntampered')
            invalid = _request(port, route)
            _expect(invalid['active_state'], 'invalid', 'Tampered product cannot remain active/current')
            _release_action(port, route, invalid, {'op': 'activate', 'release_id': release['id']}, 400)
        finally:
            asset.write_bytes(original)
        _expect(_request(port, route)['active_state'], 'current', 'Restored package matches seal')
        project['spec']['terrain']['amplitude'] += .25
        _request(port, project_route + '/spec', 'PUT', {'spec': project['spec']})
        stale = _request(port, route)
        _expect(stale['active_state'], 'stale', 'Spec edit invalidates release eligibility')
        _release_action(port, route, stale, {'op': 'activate', 'release_id': release['id']}, 400)
        _release_action(port, route, stale, {'op': 'promote', 'job_id': job['id']}, 400)

    return {'job_id': job['id'], 'job_status': done['status'], 'priority': done['priority'],
            'commands': [{'stage': c['stage'], 'exit_code': c['exit_code']} for c in done['commands']],
            'release_id': release['id'], 'manifest_sha256': release['manifest_sha256'],
            'restored_release_state': restored['active_state'], 'tampered_release_state': invalid['active_state'],
            'edited_release_state': stale['active_state'], 'foreign_promotion_rejected': True,
            'revision_conflict_rejected': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='studio-orchestration-') as temporary:
        workspace = Path(temporary)
        portfolio = check_portfolio(workspace / 'portfolio')
        queue = check_queue(workspace / 'queue')
        release = check_release(workspace / 'release')
    report = json.dumps({'status': 'passed', 'portfolio': portfolio, 'queue': queue,
                         'release': release}, indent=2) + '\n'
    if args.output:
        args.output.write_text(report, encoding='utf-8')
    print(report, end='')


if __name__ == '__main__':
    main()
