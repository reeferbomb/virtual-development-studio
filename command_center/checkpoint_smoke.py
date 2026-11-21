"""Verify checkpoint persistence, conflicts, and new runs over local HTTP."""

import argparse
import json
import tempfile
import threading
from contextlib import contextmanager
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

from .provenance import spec_digest
from .server import ROOT, StudioService, create_server


@contextmanager
def _running_service(workspace):
    service = StudioService(ROOT, workspace)
    try:
        with create_server(service, 0) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield server.server_port
            finally:
                server.shutdown()
                thread.join()
    finally:
        service.pipeline.worker.shutdown(wait=True)


def _expect(actual, expected, check):
    if actual != expected:
        raise RuntimeError(f'{check}. Expected {expected!r}, received {actual!r}')


def _request(port, route, method='GET', data=None, *, expected_status=HTTPStatus.OK):
    connection = HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        headers = {}
        body = None
        if data is not None:
            body = json.dumps(data)
            headers = {'Content-Type': 'application/json', 'X-Studio-Request': '1'}
        connection.request(method, route, body, headers)
        with connection.getresponse() as response:
            result = json.load(response)
            _expect(response.status, expected_status, f'{method} {route} returned {result!r}')
            return result
    finally:
        connection.close()


def smoke(workspace):
    with _running_service(workspace) as port:
        project = _request(port, '/api/projects', 'POST',
                           {'name': 'Checkpoint Smoke Yard', 'kind': 'world'},
                           expected_status=HTTPStatus.CREATED)
        project_id = project['id']
        project_route = f'/api/projects/{project_id}'
        route = f'{project_route}/checkpoint'
        digest = spec_digest(project['spec'])

        empty = _request(port, route)
        _expect(empty, {'project_id': project_id, 'spec_sha256': digest, 'state': 'empty',
                        'revision': 0, 'checkpoint': None, 'target_seconds': 18000,
                        'remaining_seconds': 18000}, 'New project checkpoint')
        recorded = {
            'spec_sha256': digest,
            'elapsed_seconds': 360,
            'status': 'paused',
            'completed_work': ['Created the smoke world project'],
            'verification_evidence': ['The project API returned the saved world specification'],
            'remaining_work': ['Review the saved terrain amplitude'],
            'next_action': 'Open the world spec and review terrain.amplitude',
        }
        request = {**recorded, 'expected_revision': empty['revision']}
        saved = _request(port, route, 'PUT', request)
        _expect(saved['state'], 'current', 'Saved checkpoint state')
        _expect(saved['project_id'], project_id, 'Saved checkpoint project ID')
        _expect(saved['spec_sha256'], digest, 'Saved checkpoint spec digest')
        _expect(saved['revision'], 1, 'Saved checkpoint revision')
        _expect(saved['remaining_seconds'], 17640, 'Remaining recorded active time')
        _expect({key: saved['checkpoint'][key] for key in recorded}, recorded, 'Saved checkpoint fields')

    with _running_service(workspace) as port:
        restored = _request(port, route)
        _expect(restored, saved, 'Checkpoint restored from the same workspace')

        _request(port, route, 'PUT', request, expected_status=HTTPStatus.CONFLICT)
        _expect(_request(port, route), restored, 'Checkpoint after a revision conflict')

        project['spec']['terrain']['amplitude'] += 0.25
        changed = _request(port, f'{project_route}/spec', 'PUT', {'spec': project['spec']})
        current_digest = spec_digest(changed['spec'])
        stale = _request(port, route)
        _expect(stale, {**restored, 'state': 'stale', 'spec_sha256': current_digest,
                        'remaining_seconds': None}, 'Checkpoint against the changed project spec')

        reset_record = {
            'expected_revision': stale['revision'],
            'spec_sha256': current_digest,
            'elapsed_seconds': 0,
            'status': 'in_progress',
            'completed_work': [],
            'verification_evidence': [],
            'remaining_work': ['Verify the edited world spec'],
            'next_action': 'Validate the edited terrain amplitude',
        }
        _request(port, route, 'PUT', reset_record, expected_status=HTTPStatus.CONFLICT)
        _expect(_request(port, route), stale, 'Stale checkpoint before explicit reset')

        reset = _request(port, route, 'PUT', {**reset_record, 'reset_for_spec_change': True})
        _expect(reset['state'], 'current', 'Reset checkpoint state')
        _expect(reset['revision'], 2, 'Reset checkpoint revision')
        _expect(reset['remaining_seconds'], 18000, 'Remaining time after reset')
        _expect({key: reset['checkpoint'][key] for key in recorded},
                {key: reset_record[key] for key in recorded}, 'Reset checkpoint fields')
        _expect(_request(port, route), reset, 'Checkpoint after reset')

        completed = _request(port, route, 'PUT', {
            **reset_record,
            'expected_revision': reset['revision'],
            'elapsed_seconds': 480,
            'status': 'completed',
            'completed_work': ['Verified the edited world spec'],
            'verification_evidence': ['The edited spec digest matched the checkpoint'],
            'remaining_work': [],
            'next_action': '',
        })
        _expect(completed['checkpoint']['status'], 'completed', 'Completed run status')
        _expect(completed['remaining_seconds'], 17520, 'Unused active time at completion')
        new_run = _request(port, route, 'PUT', {
            **reset_record,
            'expected_revision': completed['revision'],
            'start_new_run': True,
            'remaining_work': ['Review the world again in the next activation'],
            'next_action': 'Open the saved world spec',
        })
        _expect(new_run['revision'], completed['revision'] + 1, 'New run revision')
        _expect(new_run['spec_sha256'], current_digest, 'New run spec digest')
        _expect(new_run['checkpoint']['elapsed_seconds'], 0, 'New run elapsed time')
        _expect(new_run['remaining_seconds'], 18000, 'New run remaining time')
        _expect(_request(port, route), new_run, 'Checkpoint after starting a new run')

    return {
        'status': 'passed',
        'project_id': project_id,
        'initial_state': empty['state'],
        'saved_revision': saved['revision'],
        'restored_revision': restored['revision'],
        'recorded_active_seconds': restored['checkpoint']['elapsed_seconds'],
        'remaining_seconds_after_restart': restored['remaining_seconds'],
        'revision_conflict_status': int(HTTPStatus.CONFLICT),
        'changed_spec_state': stale['state'],
        'remaining_seconds_for_changed_spec': stale['remaining_seconds'],
        'stale_write_status': int(HTTPStatus.CONFLICT),
        'reset_revision': reset['revision'],
        'reset_remaining_seconds': reset['remaining_seconds'],
        'completed_revision': completed['revision'],
        'new_run_revision': new_run['revision'],
        'new_run_remaining_seconds': new_run['remaining_seconds'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Also write the JSON report to this path')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='studio-checkpoint-smoke-') as workspace:
        report = json.dumps(smoke(Path(workspace)), indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding='utf-8')
    print(report, end='')


if __name__ == '__main__':
    main()
