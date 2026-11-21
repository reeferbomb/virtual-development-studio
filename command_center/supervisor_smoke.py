"""Run independent supervisor acceptance against a disposable Studio workspace."""
import argparse
import json
import tempfile
from pathlib import Path

from .checkpoint_smoke import _expect, _request, _running_service
from .orchestration_smoke import _wait_job, _release_action
from .scheduler_smoke import _create_project


def _defect_action(port, route, snapshot, action, status=200):
    return _request(port, route, 'PUT', {'expected_revision': snapshot['revision'],
                    'spec_sha256': snapshot['spec_sha256'], 'action': action}, expected_status=status)


def check_defects(workspace):
    with _running_service(workspace) as port:
        project = _create_project(port, 'Supervisor Defect Fixture')
        root = f'/api/projects/{project["id"]}'
        route = root + '/defects'
        initial = _request(port, route)
        _expect((initial['revision'], initial['items']), (0, []), 'New defect log')
        initial_audit = _request(port, root + '/supervisor')
        _expect(initial_audit['status'], 'pending', 'No build evidence cannot pass audit')
        add = {'op': 'add', 'title': 'Fixture acceptance blocker', 'severity': 'critical',
               'description': 'Synthetic acceptance fixture: test that critical defects block the audit.',
               'evidence': ['Operator recorded the synthetic blocker for this acceptance test.']}
        saved = _defect_action(port, route, initial, add)
        issue = saved['items'][0]
        blocked = _request(port, root + '/supervisor')
        _expect(blocked['status'], 'blocked', 'Open critical defect blocks supervisor')
        _expect(_request(port, route), saved, 'Audit has no automatic mutation')
        _defect_action(port, route, initial, add, 409)
        resolved = _defect_action(port, route, saved, {'op': 'resolve', 'defect_id': issue['id'],
                    'evidence': ['Acceptance fixture inspected; synthetic blocker intentionally cleared.']})
        _expect(resolved['items'][0]['status'], 'resolved', 'Resolution persisted')
        _expect(len(resolved['items'][0]['evidence']), 2, 'Both lifecycle notes retained')
        _expect(_request(port, root + '/supervisor')['status'] != 'blocked', True, 'Resolved defect no longer blocks')

    with _running_service(workspace) as port:
        restored = _request(port, route)
        _expect(restored, resolved, 'Defect log survives restart')
        project['spec']['terrain']['amplitude'] += .25
        _request(port, root + '/spec', 'PUT', {'spec': project['spec']})
        historical = _request(port, route)
        _expect(historical['summary']['historical_resolved'], 1, 'Historical defect retained')
        _expect(historical['summary']['current_open'], 0, 'Old defect not counted for new spec')
        _defect_action(port, route, historical, {'op': 'reopen', 'defect_id': issue['id'],
                       'evidence': ['Should not alter historical evidence.']}, 409)
        _expect(_request(port, route), historical, 'Historical mutation rejected without changes')
    return {'initial_status': initial_audit['status'], 'blocked_status': blocked['status'],
            'restored_status': restored['items'][0]['status'], 'historical_resolved': historical['summary']['historical_resolved'],
            'cas_conflict_rejected': True, 'historical_mutation_rejected': True}


def _check(audit, identifier):
    return next(item['status'] for item in audit['checks'] if item['id'] == identifier)


def check_verified_build(workspace):
    with _running_service(workspace) as port:
        project = _create_project(port, 'Supervisor Real Build')
        root = f'/api/projects/{project["id"]}'
        initial = _request(port, root + '/performance')
        _expect(initial['counts']['total'], 0, 'No initial timing samples')
        _expect(initial['regression'], None, 'No invented performance baseline')
        job = _request(port, root + '/build', 'POST', {'priority': 5}, expected_status=202)
        done = _wait_job(port, job['id'])
        _expect((done['status'], done['verified']), ('passed', True), 'Real Godot build passed')
        performance = _request(port, root + '/performance')
        _expect(performance['counts']['passed'], 1, 'One verified job in current scope')
        _expect(performance['regression'], None, 'One job does not establish regression')
        sample = performance['samples'][0]
        _expect(sample['job_id'], job['id'], 'Timing source identity')
        actual = {stage['stage']: stage['duration_seconds'] for stage in done['commands']}
        _expect(sample['build_seconds'], actual['build'], 'Measured build stage duration')
        _expect(sample['verify_seconds'], actual['verify'], 'Measured verify stage duration')
        initial_registry = _request(port, root + '/releases')
        _release_action(port, root + '/releases', initial_registry, {'op': 'promote', 'job_id': job['id']})
        audit = _request(port, root + '/supervisor')
        build_check = _check(audit, 'build')
        release_check = _check(audit, 'release')
        _expect((build_check, release_check), ('pass', 'pass'), 'Current build and release evidence')
        package = workspace / done['output']
        manifest = json.loads((package / 'manifest.json').read_text())
        artifact = package / manifest['files'][0]['path']
        original = artifact.read_bytes()
        try:
            artifact.write_bytes(original + b'\nacceptance tamper')
            tampered = _request(port, root + '/supervisor')
            _expect(tampered['status'], 'blocked', 'Damaged active release blocks audit')
            _expect(_check(tampered, 'release'), 'fail', 'Release integrity check fails')
        finally:
            artifact.write_bytes(original)
        project['spec']['terrain']['amplitude'] += .25
        _request(port, root + '/spec', 'PUT', {'spec': project['spec']})
        after_edit = _request(port, root + '/supervisor')
        _expect(_check(after_edit, 'build') != 'pass', True, 'Prior spec build cannot pass current audit')
        _expect(_request(port, root + '/performance')['counts']['total'], 0, 'Old samples excluded after spec edit')
    return {'job_id': job['id'], 'build_check': build_check, 'release_check': release_check,
            'tampered_status': tampered['status'], 'edited_build_check': _check(after_edit, 'build'),
            'build_seconds': sample['build_seconds'], 'verify_seconds': sample['verify_seconds'],
            'queue_seconds': sample['queue_seconds'], 'regression': performance['regression']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='studio-supervisor-') as path:
        root = Path(path)
        results = {'status': 'passed', 'defects': check_defects(root / 'defects'),
                   'verified_build': check_verified_build(root / 'build')}
    report = json.dumps(results, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(report, encoding='utf-8')
    print(report, end='')


if __name__ == '__main__':
    main()
