"""Exercise the v27 read-only reports against the persisted Studio stores."""

import json
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path

from command_center.checkpoint_smoke import _running_service
from command_center.dispatch_cycle import dispatch_cycle
from command_center.quality_matrix import quality_matrix
from command_center.quality_trends import quality_trends
from command_center.specialist_analytics import specialist_analytics
from command_center.studio_curriculum import curriculum


class QualityHTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory(prefix='studio-quality-http-'))
        self.workspace = Path(temporary)
        self.port = self.enterContext(_running_service(self.workspace))

    def request(self, path, method='GET', data=None, *, status=200, headers=None):
        if headers is None:
            headers = {'Content-Type': 'application/json', 'X-Studio-Request': '1'} if data is not None else {}
        connection = HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            connection.request(method, path, json.dumps(data) if data is not None else None, headers)
            with connection.getresponse() as response:
                result = json.load(response)
                self.assertEqual(response.status, status, f'{method} {path}: {result}')
                self.assertEqual(response.getheader('Cache-Control'), 'no-store')
                return result
        finally:
            connection.close()

    def project(self, name='Quality Yard'):
        project = self.request('/api/projects', 'POST', {'name': name, 'kind': 'world'}, status=201)
        return project, f"/api/projects/{project['id']}"

    @staticmethod
    def update(record, **fields):
        return {'expected_revision': record['revision'], 'spec_sha256': record['spec_sha256'], **fields}

    def change(self, path, method, record, op, **fields):
        return self.request(path, method, self.update(record, action={'op': op, **fields}))

    def add_task(self, route, task_id, role, priority=3):
        path = route + '/tasks'
        return self.change(path, 'PUT', self.request(path), 'add', task={
            'id': task_id, 'title': task_id.replace('-', ' ').title(), 'role': role,
            'priority': priority, 'depends_on': [], 'gate': 'manual',
        })

    def capture(self, route):
        path = route + '/evidence-history'
        return self.request(path, 'POST', self.update(self.request(path), note='Review the saved terrain.'))

    def review_handoff(self, route):
        board = self.add_task(route, 'inspect-terrain', 'verification')
        board = self.change(route + '/tasks', 'PUT', board, 'start', task_id='inspect-terrain')
        order, = self.request(route + '/work-orders')['orders']
        path = route + '/handoffs'
        ledger = self.change(path, 'POST', self.request(path), 'submit',
                             task_id=order['task_id'], order_id=order['order_id'], outcome='completed',
                             summary='Reviewed the route.',
                             evidence=['Observed a clear approach in the terrain fixture.'],
                             changed_paths=[], next_action='Verify the approach independently.')
        ledger = self.change(path, 'POST', ledger, 'review', handoff_id=ledger['items'][0]['id'],
                             decision='accepted', note='Reviewed the observation.')
        return board, ledger

    def workspace_contents(self):
        contents = {}
        for path in self.workspace.rglob('*'):
            relative = path.relative_to(self.workspace)
            if path.is_file():
                info = path.stat()
                contents[relative] = (info.st_ino, info.st_mtime_ns, path.read_bytes())
            else:
                contents[relative] = None
        return contents

    def test_get_routes_enforce_local_scope_without_writing_files(self):
        project, route = self.project()
        digest = self.request(route + '/tasks')['spec_sha256']
        before = self.workspace_contents()
        resources = ('quality-matrix', 'quality-trends', 'specialist-analytics')
        for path in [f'{route}/{resource}' for resource in resources] + ['/api/dispatch-cycle', '/api/training']:
            with self.subTest(path=path):
                result = self.request(path, headers={'Origin': f'http://127.0.0.1:{self.port}'})
                if path.startswith(route + '/'):
                    self.assertEqual((result['project_id'], result['spec_sha256']), (project['id'], digest))
                    self.request(f"/api/projects/missing/{path.rsplit('/', 1)[-1]}", status=404)
                self.assertEqual(self.request(path), result)
                self.request(path, headers={'Host': 'external.invalid'}, status=403)
                self.request(path, headers={'Origin': 'http://external.invalid'}, status=403)
                self.request(path, 'POST', {}, status=404)
                self.request(path, 'PUT', {}, status=404)
        self.assertEqual(self.workspace_contents(), before)

    def test_training_serves_the_versioned_curriculum(self):
        result = self.request('/api/training')
        self.assertEqual(result, curriculum())
        self.assertEqual(result['version'], 3)
        self.assertRegex(result['curriculum_sha256'], r'^[0-9a-f]{64}$')
        self.assertTrue(result['tracks'])

    def test_matrix_and_trends_use_live_audit_and_the_latest_saved_capture(self):
        project, route = self.project()
        self.capture(route)
        history = self.capture(route)
        path = route + '/defects'
        self.change(path, 'PUT', self.request(path), 'add', title='Missing terrain collision',
                    severity='critical', description='The terrain approach has no collision boundary.',
                    evidence=['The terrain marker crosses the boundary.'])
        before = self.workspace_contents()

        matrix = self.request(route + '/quality-matrix')
        trends = self.request(route + '/quality-trends')
        acceptance = self.request(route + '/acceptance')
        self.assertEqual(matrix, quality_matrix(project, acceptance))
        self.assertEqual(matrix['status'], 'blocked')
        matrix_checks = {row['id']: row for row in matrix['checks']}
        self.assertEqual(matrix_checks['defects']['status'], 'fail')
        latest = history['items'][0]
        self.assertIn(latest['id'], matrix_checks['audit_history']['evidence'])

        audit = self.request(route + '/supervisor')
        self.assertEqual(trends, quality_trends(project, audit, history))
        self.assertEqual((trends['status'], trends['history_revision'], trends['baseline_id']),
                         ('current', history['revision'], latest['id']))
        self.assertEqual((trends['baseline_status'], trends['live_status']), ('pending', 'blocked'))
        self.assertEqual({row['id']: row['trend'] for row in trends['checks']}['defects'], 'regressed')
        self.assertEqual(self.workspace_contents(), before)

    def test_analytics_and_dispatch_use_current_persisted_records(self):
        project, route = self.project()
        other, other_route = self.project('Adjacent Yard')
        board, ledger = self.review_handoff(route)
        board = self.add_task(route, 'place-markers', 'content')
        other_board = self.add_task(other_route, 'write-signage', 'content', priority=5)
        before = self.workspace_contents()

        analytics = self.request(route + '/specialist-analytics')
        cycle = self.request('/api/dispatch-cycle')
        self.assertEqual(analytics, specialist_analytics(project, ledger))
        self.assertEqual((analytics['status'], analytics['handoff_revision']), ('current', ledger['revision']))
        verification = next(row for row in analytics['roles'] if row['role'] == 'verification')
        self.assertEqual((verification['submitted'], verification['accepted'], verification['completed']), (1, 1, 1))
        self.assertEqual(self.request(other_route + '/specialist-analytics')['status'], 'empty')

        self.assertEqual(cycle, dispatch_cycle(self.request('/api/portfolio')))
        self.assertEqual(cycle['status'], 'ready')
        step, = cycle['steps']
        self.assertEqual((step['project_id'], step['expected_revision'], step['spec_sha256']),
                         (other['id'], other_board['revision'], other_board['spec_sha256']))
        self.assertEqual(step['action'], {'op': 'start', 'task_id': 'write-signage'})
        self.assertEqual(self.request(route + '/tasks'), board)
        self.assertEqual(self.request(other_route + '/tasks'), other_board)
        self.assertEqual(self.request('/api/jobs'), [])
        self.assertEqual(self.workspace_contents(), before)

    def test_corrupt_and_historical_sources_are_handled_by_scope(self):
        project, route = self.project()
        _, other_route = self.project('Separate Evidence Yard')
        self.review_handoff(route)
        board = self.add_task(route, 'place-markers', 'content')
        history = self.capture(route)
        audit_file = self.workspace / 'projects' / project['id'] / 'evidence-history.json'
        handoff_file = audit_file.with_name('handoffs.json')
        board_file = audit_file.with_name('task-board.json')
        analytics_path = route + '/specialist-analytics'
        trends_path = route + '/quality-trends'
        matrix_path = route + '/quality-matrix'
        cycle_path = '/api/dispatch-cycle'
        for source, affected_path, unaffected_path in (
                (audit_file, trends_path, analytics_path),
                (handoff_file, analytics_path, trends_path),
                (board_file, cycle_path, analytics_path)):
            with self.subTest(source=source.name):
                valid = source.read_bytes()
                unchanged = self.request(unaffected_path)
                try:
                    source.write_bytes(b'{invalid JSON')
                    before = self.workspace_contents()
                    self.assertEqual(self.request(affected_path)['status'], 'unavailable')
                    self.assertEqual(self.request(unaffected_path), unchanged)
                    self.assertEqual(self.request(other_route + '/quality-trends')['status'], 'empty')
                    if source != handoff_file:
                        gate = 'audit_history' if source == audit_file else 'task_board'
                        checks = {row['id']: row['status'] for row in self.request(matrix_path)['checks']}
                        self.assertEqual(checks[gate], 'fail')
                    self.assertEqual(self.workspace_contents(), before)
                finally:
                    source.write_bytes(valid)

        step, = self.request(cycle_path)['steps']
        self.assertEqual(step['task_id'], 'place-markers')
        project['spec']['terrain']['amplitude'] += 0.25
        self.request(route + '/spec', 'PUT', {'spec': project['spec']})
        before = self.workspace_contents()
        trends = self.request(trends_path)
        analytics = self.request(analytics_path)
        self.assertNotEqual(trends['spec_sha256'], board['spec_sha256'])
        self.assertEqual((trends['status'], trends['historical_count'], trends['baseline_id']),
                         ('empty', len(history['items']), None))
        self.assertEqual((analytics['status'], analytics['historical_count']), ('empty', 1))
        checks = {row['id']: row['status'] for row in self.request(matrix_path)['checks']}
        self.assertEqual((checks['task_board'], checks['audit_history']), ('fail', 'pending'))
        self.assertEqual(self.request(cycle_path)['steps'], [])
        self.assertEqual(self.workspace_contents(), before)
