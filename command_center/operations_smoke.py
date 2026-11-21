"""Exercise claimed orders, reviewed handoffs, release evidence and recovery over HTTP."""
import argparse
import json
import tempfile
from pathlib import Path

from .checkpoint_smoke import _expect, _request, _running_service
from .orchestration_smoke import _release_action, _wait_job
from .provenance import spec_digest
from .recovery import verify_recovery
from .scheduler_smoke import Board, _create_project


def check_operations(workspace):
    with _running_service(workspace) as port:
        project = _create_project(port, 'Operations Fixture')
        route = '/api/projects/' + project['id']
        board = Board(port, project['id'])
        board.add('verified-build', 'Build fixture', 'build_operations', 5, gate='build')
        _expect(_request(port, route + '/work-orders')['orders'], [], 'Unclaimed tasks have no orders')
        board.apply('start', task_id='verified-build')
        old = _request(port, route + '/work-orders')['orders'][0]
        _expect(old['spawn_args']['model'], 'gpt-6.2-sol', 'Claimed builder model')
        board.add('manual-check', 'Inspect fixture', 'verification', 3)
        order = _request(port, route + '/work-orders')['orders'][0]
        _expect(order['order_id'] != old['order_id'], True, 'Board revision invalidates order')
        handoffs = _request(port, route + '/handoffs')

        def handoff(snapshot, action, status=200):
            return _request(port, route + '/handoffs', 'POST', {
                'expected_revision': snapshot['revision'], 'spec_sha256': snapshot['spec_sha256'],
                'action': action}, expected_status=status)

        report = {'op': 'submit', 'task_id': 'verified-build', 'order_id': old['order_id'],
                  'outcome': 'progress', 'summary': 'Fixture prepared.',
                  'evidence': ['Fixture spec reviewed.'], 'changed_paths': [], 'next_action': 'Run builder.'}
        handoff(handoffs, report, 409)
        _expect(_request(port, route + '/handoffs'), handoffs, 'Stale order makes no mutation')
        report['order_id'] = order['order_id']
        handoffs = handoff(handoffs, report)
        pending_id = handoffs['items'][0]['id']
        job = _request(port, route + '/build', 'POST', {'priority': 5}, expected_status=202)
        done = _wait_job(port, job['id'])
        _expect((done['status'], done['verified']), ('passed', True), 'Real Godot build verified')
        report.update(outcome='completed', summary='Fixture build verified.',
                      evidence=['Verified build ' + done['id']], next_action='Lead reviews build gate.')
        handoffs = handoff(handoffs, report)
        handoffs = handoff(handoffs, {'op': 'review', 'handoff_id': handoffs['items'][0]['id'],
                                      'decision': 'accepted', 'note': 'Verified job reviewed.'})
        _expect(_request(port, board.route), board.state, 'Handoff review does not alter task state')
        board.apply('complete', task_id='verified-build', evidence=report['evidence'], job_id=done['id'])
        releases = _request(port, route + '/releases')
        _release_action(port, route + '/releases', releases, {'op': 'promote', 'job_id': done['id']})
        dossier = _request(port, route + '/dossier')
        _expect(dossier['report_sha256'], spec_digest(dossier['report']), 'Dossier integrity')
        _expect(dossier['status'] != 'ready', True, 'Incomplete manual gate cannot count as ready')
        recovery = _request(port, route + '/recovery')
        _expect(verify_recovery(recovery), True, 'Recovery integrity')
        _expect(recovery['records']['handoffs.json'] is not None, True, 'Recovery contains handoff ledger')

    with _running_service(workspace) as port:
        _expect(_request(port, route + '/handoffs'), handoffs, 'Handoffs persisted across restart')
        project['spec']['terrain']['amplitude'] += .25
        _request(port, route + '/spec', 'PUT', {'spec': project['spec']})
        historical = _request(port, route + '/handoffs')
        handoff(historical, {'op': 'review', 'handoff_id': pending_id,
                             'decision': 'accepted', 'note': 'Old evidence.'}, 409)
        _expect(_request(port, route + '/handoffs'), historical, 'Historical review makes no mutation')
        _expect(_request(port, route + '/work-orders')['orders'], [], 'Old orders not dispatchable')
    return {'build_verified': True, 'stale_order_rejected': True,
            'handoff_did_not_complete_task': True, 'recovery_verified': True,
            'historical_review_rejected': True, 'dossier_status': dossier['status'],
            'dossier_sha256': dossier['report_sha256'], 'handoff_count': len(handoffs['items'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='studio-operations-') as temporary:
        report = {'status': 'passed', **check_operations(Path(temporary))}
    rendered = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    print(rendered, end='')


if __name__ == '__main__':
    main()
