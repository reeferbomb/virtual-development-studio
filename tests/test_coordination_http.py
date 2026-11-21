"""Exercise read-only coordination views through the Studio HTTP API."""

import json
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path

from command_center.checkpoint_smoke import _running_service


class CoordinationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='studio-coordination-http-')))
        self.port = self.enterContext(_running_service(self.workspace))

    def request(self, path, method='GET', data=None, *, status=200, headers=None):
        if headers is None:
            headers = {'Content-Type': 'application/json', 'X-Studio-Request': '1'} if data is not None else {}
        body = json.dumps(data) if data is not None else None
        connection = HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            connection.request(method, path, body, headers)
            with connection.getresponse() as response:
                result = json.load(response)
                self.assertEqual(response.status, status, f'{method} {path}: {result}')
                self.assertEqual(response.getheader('Cache-Control'), 'no-store')
                return result
        finally:
            connection.close()

    def project(self, name='Coordination Yard'):
        project = self.request('/api/projects', 'POST', {'name': name, 'kind': 'world'}, status=201)
        return project, f"/api/projects/{project['id']}"

    def change(self, path, method, record, op, **fields):
        return self.request(path, method, {'expected_revision': record['revision'],
                                           'spec_sha256': record['spec_sha256'],
                                           'action': {'op': op, **fields}})

    def task(self, route, board, task_id, role, *, priority=3, depends_on=()):
        return self.change(route + '/tasks', 'PUT', board, 'add', task={
            'id': task_id, 'title': task_id.replace('-', ' ').title(), 'role': role,
            'priority': priority, 'depends_on': list(depends_on), 'gate': 'manual',
        })

    def seed_blocked_task(self, route):
        task_path = route + '/tasks'
        board = self.task(route, self.request(task_path), 'inspect-terrain', 'verification', priority=4)
        board = self.task(route, board, 'mark-route', 'content', depends_on=['inspect-terrain'])
        board = self.task(route, board, 'draft-text', 'content')
        board = self.change(task_path, 'PUT', board, 'start', task_id='inspect-terrain')
        order, = self.request(route + '/work-orders')['orders']
        handoff_path = route + '/handoffs'
        ledger = self.request(handoff_path)
        report = {'task_id': order['task_id'], 'order_id': order['order_id'], 'outcome': 'blocked',
                  'summary': 'A terrain seam interrupts the approach.',
                  'evidence': ['The approach crosses a gap at the north ridge.'],
                  'changed_paths': [], 'next_action': 'Inspect the north ridge seam in the fixture.'}
        ledger = self.change(handoff_path, 'POST', ledger, 'submit', **report)
        accepted_id = ledger['items'][0]['id']
        ledger = self.change(handoff_path, 'POST', ledger, 'review', handoff_id=accepted_id,
                             decision='accepted', note='The lead reproduced the gap.')
        ledger = self.change(handoff_path, 'POST', ledger, 'submit',
                             **{**report, 'summary': 'Unreviewed follow-up observation.'})
        blocked = self.change(task_path, 'PUT', board, 'block', task_id='inspect-terrain',
                              reason='The route needs a continuous terrain surface.')
        return blocked, ledger, accepted_id

    def workspace_contents(self):
        contents = {}
        for path in self.workspace.rglob('*'):
            if path.is_file():
                info = path.stat()
                contents[path.relative_to(self.workspace)] = (info.st_ino, info.st_mtime_ns, path.read_bytes())
            else:
                contents[path.relative_to(self.workspace)] = None
        return contents

    def test_coordination_routes_are_local_read_only_projections(self):
        project, route = self.project()
        digest = self.request(route + '/tasks')['spec_sha256']
        before = self.workspace_contents()
        resources = ('specialist-memory', 'priorities', 'recovery-advice')
        paths = [f'{route}/{resource}' for resource in resources] + ['/api/allocation']
        for path in paths:
            with self.subTest(path=path):
                result = self.request(path, headers={'Origin': f'http://127.0.0.1:{self.port}'})
                self.assertEqual(result['status'], 'empty')
                if path != '/api/allocation':
                    self.assertEqual((result['project_id'], result['spec_sha256']), (project['id'], digest))
                self.assertEqual(self.request(path), result)
                self.request(path, headers={'Host': 'external.invalid'}, status=403)
                self.request(path, headers={'Origin': 'http://external.invalid'}, status=403)
                self.request(path, 'POST', {}, status=404)
                self.request(path, 'PUT', {}, status=404)
        for resource in resources:
            self.request(f'/api/projects/missing/{resource}', status=404)
        self.assertEqual(self.workspace_contents(), before)

    def test_coordination_uses_persisted_board_and_reviewed_handoffs(self):
        project, route = self.project()
        other, other_route = self.project('Adjacent Yard')
        board, ledger, accepted_id = self.seed_blocked_task(route)
        other_board = self.task(other_route, self.request(other_route + '/tasks'),
                                'inspect-terrain', 'verification', priority=5)
        self.assertEqual(other_board['spec_sha256'], board['spec_sha256'])
        before = self.workspace_contents()

        memory = self.request(route + '/specialist-memory')
        self.assertEqual((memory['status'], memory['handoff_revision']), ('current', ledger['revision']))
        verification = next(row for row in memory['roles'] if row['role'] == 'verification')
        self.assertEqual(verification['accepted_count'], 1)
        self.assertEqual([item['handoff_id'] for item in verification['memories']], [accepted_id])
        self.assertNotIn('Unreviewed follow-up observation.', json.dumps(memory))
        self.assertEqual(self.request(other_route + '/specialist-memory')['status'], 'empty')

        priorities = self.request(route + '/priorities')
        candidate = {'task_id': 'draft-text', 'title': 'Draft Text', 'role': 'content', 'priority': 3,
                     'downstream_count': 0, 'chain_length': 1}
        self.assertEqual((priorities['status'], priorities['board_revision']), ('current', board['revision']))
        self.assertEqual(priorities['candidates'], [candidate])
        self.assertEqual(priorities['recommendations'], [candidate])

        recovery = self.request(route + '/recovery-advice')
        self.assertEqual((recovery['status'], recovery['board_revision'], recovery['handoff_revision']),
                         ('current', board['revision'], ledger['revision']))
        item, = recovery['items']
        self.assertEqual((item['task_id'], item['attempt'], item['affected_count'], item['handoff_id']),
                         ('inspect-terrain', 1, 1, accepted_id))
        self.assertNotIn('Inspect the north ridge seam in the fixture.', json.dumps(recovery))
        self.assertEqual(self.request(other_route + '/recovery-advice')['items'], [])

        allocation = self.request('/api/allocation')
        self.assertEqual((allocation['status'], allocation['summary']['assigned']), ('current', 2))
        assignments = [row['assignment'] for row in allocation['roles'] if row['state'] == 'assigned']
        self.assertEqual({(row['project_id'], row['task_id']) for row in assignments},
                         {(project['id'], 'draft-text'), (other['id'], 'inspect-terrain')})
        self.assertCountEqual(assignments, self.request('/api/portfolio')['assignments'])
        self.assertEqual(self.request(route + '/tasks'), board)
        self.assertEqual(self.request(route + '/handoffs'), ledger)
        self.assertEqual(self.request('/api/jobs'), [])
        self.assertEqual(self.workspace_contents(), before)

    def test_coordination_withholds_stale_or_unreadable_evidence_by_scope(self):
        project, route = self.project()
        other, other_route = self.project('Adjacent Yard')
        board, ledger, _ = self.seed_blocked_task(route)
        directory = self.workspace / 'projects' / project['id']
        handoff_file = directory / 'handoffs.json'
        valid_handoffs = handoff_file.read_bytes()
        foreign_ledger = {**json.loads(valid_handoffs), 'project_id': other['id']}
        handoff_file.write_text(json.dumps(foreign_ledger), encoding='utf-8')
        before = self.workspace_contents()
        memory = self.request(route + '/specialist-memory')
        self.assertEqual((memory['status'], memory['roles']), ('unavailable', []))
        recovery = self.request(route + '/recovery-advice')
        self.assertEqual((recovery['status'], recovery['items']), ('unavailable', []))
        self.assertEqual(self.request(route + '/priorities')['status'], 'current')
        self.assertEqual(self.request('/api/allocation')['status'], 'current')
        self.assertEqual(self.workspace_contents(), before)
        handoff_file.write_bytes(valid_handoffs)

        board_file = directory / 'task-board.json'
        valid_board = board_file.read_bytes()
        board_file.write_bytes(b'{unreadable')
        before = self.workspace_contents()
        priorities = self.request(route + '/priorities')
        self.assertEqual((priorities['status'], priorities['candidates']), ('unavailable', []))
        recovery = self.request(route + '/recovery-advice')
        self.assertEqual((recovery['status'], recovery['items']), ('unavailable', []))
        self.assertEqual(self.request(route + '/specialist-memory')['status'], 'current')
        self.assertEqual(self.request(other_route + '/priorities')['status'], 'empty')
        self.assertEqual(self.request(other_route + '/recovery-advice')['status'], 'empty')
        allocation = self.request('/api/allocation')
        self.assertEqual((allocation['status'], allocation['roles']), ('unavailable', []))
        self.assertEqual(self.workspace_contents(), before)
        board_file.write_bytes(valid_board)

        project['spec']['terrain']['amplitude'] += 0.25
        self.request(route + '/spec', 'PUT', {'spec': project['spec']})
        before = self.workspace_contents()
        current_digest = self.request(route + '/tasks')['spec_sha256']
        self.assertNotEqual(current_digest, board['spec_sha256'])
        memory = self.request(route + '/specialist-memory')
        self.assertEqual((memory['status'], memory['spec_sha256'], memory['historical_count']),
                         ('empty', current_digest, len(ledger['items'])))
        self.assertTrue(all(not row['memories'] for row in memory['roles']))
        for resource, key in [('priorities', 'candidates'), ('recovery-advice', 'items')]:
            snapshot = self.request(f'{route}/{resource}')
            self.assertEqual((snapshot['status'], snapshot['spec_sha256'], snapshot['board_revision'], snapshot[key]),
                             ('stale', current_digest, board['revision'], []))
        self.assertEqual(self.request('/api/allocation')['summary']['assigned'], 0)
        self.assertEqual(self.workspace_contents(), before)
