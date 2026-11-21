"""Exercise blueprint approval and advisory planning routes through local HTTP."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path

from command_center.checkpoint_smoke import _request, _running_service
from command_center.provenance import spec_digest


def _exchange(port, path, method='GET', data=None, headers=None):
    body = json.dumps(data) if data is not None else None
    if headers is None:
        headers = {'Content-Type': 'application/json', 'X-Studio-Request': '1'} if body is not None else {}
    connection = HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        connection.request(method, path, body, headers)
        with connection.getresponse() as response:
            return response.status, json.load(response)
    finally:
        connection.close()


class PlanningHTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='studio-planning-http-')
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)

    def project(self, port, name):
        project = _request(port, '/api/projects', 'POST', {'name': name, 'kind': 'world'}, expected_status=201)
        route = f"/api/projects/{project['id']}"
        directory = self.workspace / 'projects' / project['id']
        return project, route, directory

    @staticmethod
    def approval(preview):
        return {'expected_revision': preview['board_revision'], 'spec_sha256': preview['spec_sha256'],
                'plan_id': preview['plan_id']}

    @staticmethod
    def files(directory):
        return {file.name: file.read_bytes() for file in directory.iterdir()}

    def test_blueprint_approval_uses_exact_project_revision_and_spec(self):
        with _running_service(self.workspace) as port, _running_service(self.workspace) as second_port:
            project, route, directory = self.project(port, 'Planning Yard')
            _, other_route, other_directory = self.project(port, 'Other Planning Yard')
            blueprint = route + '/blueprint'
            tasks = route + '/tasks'
            previews = [_request(port, path + '/blueprint') for path in (route, other_route)]
            preview, other = previews
            self.assertEqual(preview['status'], 'ready')
            self.assertEqual(preview['spec_sha256'], other['spec_sha256'])
            self.assertNotEqual(preview['plan_id'], other['plan_id'])
            approval = self.approval(preview)

            history = _request(port, route + '/evidence-history', 'POST', {
                'expected_revision': 0, 'spec_sha256': preview['spec_sha256'],
                'note': 'Captured evidence when reviewing the saved project plan.',
            })
            before = self.files(directory)
            other_before = self.files(other_directory)
            _request(port, other_route + '/blueprint', 'POST', approval, expected_status=409)
            for invalid in ({}, {**approval, 'expected_revision': True}, {**approval, 'expected_revision': -1},
                            {**approval, 'plan_id': 'invalid'}, {**approval, 'spec_sha256': 'a'},
                            {**approval, 'tasks': preview['tasks']}):
                with self.subTest(invalid=invalid):
                    _request(port, blueprint, 'POST', invalid, expected_status=400)
            for changed in ({'expected_revision': 1}, {'spec_sha256': '0' * 64}, {'plan_id': '0' * 64}):
                with self.subTest(changed=changed):
                    _request(port, blueprint, 'POST', {**approval, **changed}, expected_status=409)
            self.assertEqual(self.files(directory), before)
            self.assertEqual(self.files(other_directory), other_before)

            with ThreadPoolExecutor(max_workers=2) as pool:
                requests = [pool.submit(_exchange, p, blueprint, 'POST', approval) for p in (port, second_port)]
                responses = dict(call.result() for call in requests)
            self.assertEqual(set(responses), {200, 409})
            applied = responses[200]
            self.assertEqual(applied['revision'], approval['expected_revision'] + 1)
            self.assertEqual(applied['tasks'], [dict(task, status='pending', attempts=0, reason=None,
                                                     job_id=None, evidence=[]) for task in preview['tasks']])
            self.assertEqual(_request(port, blueprint)['status'], 'applied')
            _request(port, blueprint, 'POST', approval, expected_status=409)
            self.assertEqual(_request(second_port, tasks), applied)
            self.assertEqual(_request(port, '/api/jobs'), [])
            self.assertEqual(_request(port, route + '/work-orders')['orders'], [])
            self.assertEqual(_request(port, route + '/evidence-history'), history)
            current = self.files(directory)
            self.assertIsNotNone(current.pop('task-board.json', None))
            self.assertEqual(current, before)
            self.assertEqual(self.files(other_directory), other_before)

            project['spec']['terrain']['amplitude'] += 0.25
            _request(port, route + '/spec', 'PUT', {'spec': project['spec']})
            after_edit = self.files(directory)
            self.assertEqual(_request(second_port, blueprint)['status'], 'blocked')
            _request(second_port, blueprint, 'POST', approval, expected_status=409)
            self.assertEqual(_request(port, tasks)['state'], 'stale')
            self.assertEqual(self.files(directory), after_edit)

    def test_planning_routes_are_local_read_only_and_fail_closed(self):
        with _running_service(self.workspace) as port:
            project, route, directory = self.project(port, 'Read-only Planning Yard')
            before = self.files(directory)
            projections = {}
            for resource, status in (('blueprint', 'ready'), ('forecast', 'empty'),
                                     ('dependency-impact', 'empty'), ('preflight', 'pending')):
                with self.subTest(resource=resource):
                    path = route + '/' + resource
                    first = _request(port, path)
                    projections[resource] = first
                    self.assertEqual((first['project_id'], first['spec_sha256'], first['status']),
                                     (project['id'], spec_digest(project['spec']), status))
                    self.assertEqual(_request(port, path), first)
                    self.assertEqual(_exchange(port, path, headers={'Host': 'external.invalid'})[0], 403)
                    self.assertEqual(_exchange(port, path, headers={'Origin': 'http://external.invalid'})[0], 403)
                    _request(port, '/api/projects/missing/' + resource, expected_status=404)
                    _request(port, path, 'PUT', {}, expected_status=404)
                    if resource != 'blueprint':
                        _request(port, path, 'POST', {}, expected_status=404)

            path = route + '/blueprint'
            approval = self.approval(projections['blueprint'])
            for headers in ({'Content-Type': 'application/json'},
                            {'Content-Type': 'application/json', 'X-Studio-Request': '1',
                             'Origin': 'http://external.invalid'}):
                self.assertEqual(_exchange(port, path, 'POST', approval, headers)[0], 403)
            self.assertEqual(self.files(directory), before)

            corrupt = b'{invalid JSON'
            (directory / 'task-board.json').write_bytes(corrupt)
            for resource, status in (('blueprint', 'blocked'), ('forecast', 'unavailable'),
                                     ('dependency-impact', 'unavailable'), ('preflight', 'blocked')):
                with self.subTest(corrupt_resource=resource):
                    self.assertEqual(_request(port, route + '/' + resource)['status'], status)
            _request(port, path, 'POST', approval, expected_status=409)
            self.assertEqual(self.files(directory), {**before, 'task-board.json': corrupt})
            self.assertEqual(_request(port, '/api/jobs'), [])


if __name__ == '__main__':
    unittest.main()
