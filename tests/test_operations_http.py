"""Exercise project operations through the loopback Studio API."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path

from command_center.checkpoint_smoke import _running_service
from command_center.recovery import verify_recovery


class OperationsHTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='studio-operations-http-')
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)

    @staticmethod
    def exchange(port, path, method, data, headers=None):
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

    def request(self, port, path, method='GET', data=None, *, status=200, headers=None):
        received, result = self.exchange(port, path, method, data, headers)
        self.assertEqual(received, status, f'{method} {path}: {result}')
        if status >= 400:
            self.assertTrue(result['error'])
        return result

    def project(self, port, name='Operations Yard'):
        project = self.request(port, '/api/projects', 'POST', {'name': name, 'kind': 'world'}, status=201)
        return project, f"/api/projects/{project['id']}"

    @staticmethod
    def update(record, action):
        return {'expected_revision': record['revision'], 'spec_sha256': record['spec_sha256'], 'action': action}

    def task(self, port, route, board, op, **fields):
        return self.request(port, route + '/tasks', 'PUT', self.update(board, {'op': op, **fields}))

    def claim(self, port, route):
        board = self.request(port, route + '/tasks')
        board = self.task(port, route, board, 'add', task={
            'id': 'review-yard', 'title': 'Review the yard', 'role': 'verification',
            'priority': 3, 'depends_on': [], 'gate': 'manual',
        })
        self.assertEqual(self.request(port, route + '/work-orders')['orders'], [])
        return self.task(port, route, board, 'start', task_id='review-yard')

    def order(self, port, route, board):
        projected = self.request(port, route + '/work-orders')
        self.assertEqual(projected['state'], 'current')
        self.assertEqual(projected['board_revision'], board['revision'])
        order, = projected['orders']
        self.assertRegex(order['order_id'], r'^[0-9a-f]{64}$')
        return order

    def submit(self, ledger, order):
        return self.update(ledger, {
            'op': 'submit', 'task_id': order['task_id'], 'order_id': order['order_id'],
            'outcome': 'completed', 'summary': 'Reviewed the fixture terrain.',
            'evidence': ['The fixture route has a clear approach.'],
            'changed_paths': ['world/demo_spec.json'],
            'next_action': 'Review the terrain check and record task completion.',
        })

    @staticmethod
    def contents(directory):
        return {file.name: file.read_bytes() for file in directory.iterdir()}

    def test_routes_enforce_local_scope_and_exports_are_read_only(self):
        with _running_service(self.workspace) as port:
            project, route = self.project(port)
            directory = self.workspace / 'projects' / project['id']
            before = self.contents(directory)
            digest = self.request(port, route + '/tasks')['spec_sha256']
            for resource in ('work-orders', 'handoffs', 'dossier', 'recovery'):
                with self.subTest(resource=resource):
                    path = route + '/' + resource
                    result = self.request(port, path, headers={'Origin': f'http://127.0.0.1:{port}'})
                    self.assertEqual((result['project_id'], result['spec_sha256']), (project['id'], digest))
                    self.assertEqual(self.request(port, path), result)
                    self.request(port, path, headers={'Host': 'external.invalid'}, status=403)
                    self.request(port, path, headers={'Origin': 'http://external.invalid'}, status=403)
                    self.request(port, '/api/projects/missing/' + resource, status=404)
                    self.request(port, path, 'PUT', {}, status=404)
                    if resource != 'handoffs':
                        self.request(port, path, 'POST', {}, status=404)
            self.assertEqual(self.contents(directory), before)
            self.assertEqual(self.request(port, '/api/jobs'), [])

    def test_handoffs_bind_to_current_claim_and_persist_after_restart(self):
        with _running_service(self.workspace) as port:
            project, route = self.project(port)
            _, other = self.project(port, 'Separate Operations Yard')
            board, other_board = self.claim(port, route), self.claim(port, other)
            self.assertEqual(board['spec_sha256'], other_board['spec_sha256'])
            initial_order = self.order(port, route, board)
            other_order = self.order(port, other, other_board)
            self.assertNotEqual(initial_order['order_id'], other_order['order_id'])
            path = route + '/handoffs'
            empty = self.request(port, path)
            self.assertEqual((empty['revision'], empty['items']), (0, []))
            original_submit = self.submit(empty, initial_order)
            self.request(port, other + '/handoffs', 'POST', original_submit, status=409)
            self.request(port, '/api/projects/missing/handoffs', 'POST', original_submit, status=404)
            self.request(port, path, 'POST', original_submit, status=403, headers={'Content-Type': 'application/json'})
            self.request(port, path, 'POST', original_submit, status=403, headers={
                'Content-Type': 'application/json', 'X-Studio-Request': '1', 'Origin': 'http://external.invalid',
            })
            self.request(port, path, 'POST', {**original_submit, 'expected_revision': True}, status=400)
            self.assertEqual(self.request(port, path), empty)

            board = self.task(port, route, board, 'requeue', task_id='review-yard')
            self.assertEqual(self.request(port, route + '/work-orders')['orders'], [])
            board = self.task(port, route, board, 'start', task_id='review-yard')
            order = self.order(port, route, board)
            self.assertEqual(order['attempt'], initial_order['attempt'] + 1)
            self.assertNotEqual(order['order_id'], initial_order['order_id'])
            self.request(port, path, 'POST', original_submit, status=409)

            submission = self.submit(empty, order)
            with _running_service(self.workspace) as second_port, ThreadPoolExecutor(max_workers=2) as pool:
                pending = [pool.submit(self.exchange, endpoint, path, 'POST', submission)
                           for endpoint in (port, second_port)]
                responses = dict(future.result() for future in pending)
            self.assertEqual(set(responses), {200, 409})
            saved = responses[200]
            item, = saved['items']
            self.assertEqual((saved['revision'], item['order_id'], item['review']), (1, order['order_id'], 'pending'))
            self.assertEqual(self.request(port, path), saved)
            self.assertEqual(self.request(port, other + '/handoffs')['items'], [])

            review = {'op': 'review', 'handoff_id': item['id'], 'decision': 'accepted',
                      'note': 'Reviewed the reported terrain evidence.'}
            reviewed = self.request(port, path, 'POST', self.update(saved, review))
            self.assertEqual((reviewed['revision'], reviewed['items'][0]['review']), (2, 'accepted'))
            self.assertEqual(self.request(port, route + '/tasks'), board)
            self.assertEqual(self.order(port, route, board), order)
            completed = self.task(port, route, board, 'complete', task_id='review-yard',
                                  evidence=['Verified the route approach in the terrain fixture.'])
            self.assertEqual(completed['tasks'][0]['status'], 'completed')
            self.assertEqual(self.request(port, route + '/work-orders')['orders'], [])
            self.assertEqual(self.request(port, '/api/jobs'), [])

            dossier = self.request(port, route + '/dossier')
            report = dossier['report']
            self.assertEqual((report['handoffs']['completed_attempts'], report['handoffs']['covered_attempts']),
                             (1, 1))
            self.assertEqual(report['board']['revision'], completed['revision'])
            self.assertEqual(self.request(port, other + '/dossier')['report']['handoffs']['current_count'], 0)
            recovery = self.request(port, route + '/recovery')
            self.assertTrue(verify_recovery(recovery))
            self.assertIsNotNone(recovery['records']['handoffs.json'])

        with _running_service(self.workspace) as port:
            self.assertEqual(self.request(port, path), reviewed)
            self.assertEqual(self.request(port, route + '/dossier'), dossier)
            self.assertEqual(self.request(port, route + '/recovery'), recovery)
            project['spec']['terrain']['amplitude'] += 0.25
            self.request(port, route + '/spec', 'PUT', {'spec': project['spec']})
            stale = self.request(port, route + '/work-orders')
            self.assertEqual((stale['state'], stale['orders']), ('stale', []))
            historical = self.request(port, path)
            self.assertEqual(historical['items'], reviewed['items'])
            self.assertNotEqual(historical['spec_sha256'], reviewed['spec_sha256'])
            self.request(port, path, 'POST', self.update(reviewed, review), status=409)
            self.request(port, path, 'POST', self.update(historical, review), status=409)
            latest = self.request(port, route + '/dossier')
            self.assertNotEqual(latest['report_sha256'], dossier['report_sha256'])
            counts = latest['report']['handoffs']
            self.assertEqual((counts['current_count'], counts['historical_count']), (0, 1))

    def test_corrupt_sources_fail_closed_without_losing_other_evidence(self):
        with _running_service(self.workspace) as port:
            project, route = self.project(port)
            self.claim(port, route)
            orders = self.request(port, route + '/work-orders')
            path = route + '/handoffs'
            submission = self.submit(self.request(port, path), orders['orders'][0])
            ledger = self.request(port, path, 'POST', submission)
            before = self.request(port, route + '/dossier')['report']
            directory = self.workspace / 'projects' / project['id']
            corrupt = b'{invalid JSON'
            handoff_file = directory / 'handoffs.json'
            valid_handoffs = handoff_file.read_bytes()

            handoff_file.write_bytes(corrupt)
            self.request(port, path, status=400)
            self.request(port, path, 'POST', self.update(ledger, submission['action']), status=400)
            self.assertEqual(self.request(port, route + '/work-orders'), orders)
            dossier = self.request(port, route + '/dossier')['report']
            self.assertIsNone(dossier['handoffs'])
            self.assertEqual(dossier['board'], before['board'])
            self.assertEqual(dossier['release'], before['release'])
            self.request(port, route + '/recovery', status=400)
            self.assertEqual(handoff_file.read_bytes(), corrupt)
            handoff_file.write_bytes(valid_handoffs)

            board_file = directory / 'task-board.json'
            board_file.write_bytes(corrupt)
            unknown = self.request(port, route + '/work-orders')
            self.assertEqual((unknown['state'], unknown['orders']), ('unavailable', []))
            dossier = self.request(port, route + '/dossier')['report']
            self.assertIsNone(dossier['board'])
            self.assertEqual(dossier['release'], before['release'])
            self.assertEqual(self.request(port, path), ledger)
            gates = {gate['id']: gate['status'] for gate in dossier['gates']}
            self.assertEqual(gates['task_board'], 'fail')
            self.request(port, route + '/recovery', status=400)
            self.assertEqual(board_file.read_bytes(), corrupt)
