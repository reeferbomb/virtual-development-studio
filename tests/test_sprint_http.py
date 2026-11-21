"""Verify sprint approval, evidence capture and readiness through the Studio API."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path

from command_center.checkpoint_smoke import _running_service


class SprintHTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='studio-sprint-http-')
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

    def project(self, port, name='Sprint Yard'):
        project = self.request(port, '/api/projects', 'POST', {'name': name, 'kind': 'world'}, status=201)
        return project, f"/api/projects/{project['id']}"

    @staticmethod
    def approval(preview):
        return {'expected_revision': preview['board_revision'], 'spec_sha256': preview['spec_sha256'],
                'plan_id': preview['plan_id']}

    @staticmethod
    def update(snapshot, **fields):
        return {'expected_revision': snapshot['revision'], 'spec_sha256': snapshot['spec_sha256'], **fields}

    @staticmethod
    def gates(readiness):
        return {gate['id']: gate['status'] for gate in readiness['gates']}

    def add_defect(self, port, route):
        path = route + '/defects'
        data = self.update(self.request(port, path), action={
            'op': 'add', 'title': 'Fixture collision issue', 'severity': 'critical',
            'description': 'Fixture marker crosses the expected collision boundary.',
            'evidence': ['Recorded a boundary crossing in the desktop fixture.'],
        })
        return self.request(port, path, 'PUT', data)

    def test_sprint_approval_is_project_scoped_and_applies_once(self):
        with _running_service(self.workspace) as port:
            _, route = self.project(port)
            _, other = self.project(port, 'Another Sprint Yard')
            sprint, tasks = route + '/sprint', route + '/tasks'
            empty_board, preview = self.request(port, tasks), self.request(port, sprint)
            approval = self.approval(preview)
            self.assertEqual(preview['status'], 'ready')
            self.assertEqual(self.request(port, sprint), preview)
            self.assertEqual(self.request(port, tasks), empty_board)
            other_preview = self.request(port, other + '/sprint')
            self.assertEqual(other_preview['spec_sha256'], preview['spec_sha256'])
            self.assertNotEqual(other_preview['plan_id'], preview['plan_id'])
            self.request(port, other + '/sprint', 'POST', approval, status=409)

            for invalid in ({}, {**approval, 'expected_revision': True}, {**approval, 'expected_revision': -1},
                            {**approval, 'plan_id': 'invalid'}, {**approval, 'spec_sha256': 'a'},
                            {**approval, 'tasks': preview['tasks']}):
                with self.subTest(invalid=invalid.keys()):
                    self.request(port, sprint, 'POST', invalid, status=400)
            self.assertEqual(self.request(port, tasks), empty_board)

            task = {'id': 'review-terrain', 'title': 'Review the terrain', 'role': 'architecture',
                    'priority': 1, 'depends_on': [], 'gate': 'manual'}
            manual = self.request(port, tasks, 'PUT', self.update(empty_board, action={'op': 'add', 'task': task}))
            self.request(port, sprint, 'POST', approval, status=409)
            self.assertEqual(self.request(port, tasks), manual)

            current = self.request(port, sprint)
            with ThreadPoolExecutor(max_workers=2) as pool:
                waiters = [pool.submit(self.exchange, port, sprint, 'POST', self.approval(current)) for _ in range(2)]
                responses = dict(waiter.result() for waiter in waiters)
            self.assertEqual(set(responses), {200, 409})
            applied = responses[200]
            self.assertEqual(applied['revision'], manual['revision'] + 1)
            self.assertEqual(applied['tasks'][0], manual['tasks'][0])
            self.assertEqual(applied['tasks'][1:], [dict(task, status='pending', attempts=0, reason=None,
                                                        job_id=None, evidence=[]) for task in current['tasks']])
            self.assertEqual(self.request(port, tasks), applied)
            self.assertEqual(self.request(port, other + '/tasks')['tasks'], [])
            empty_plan = self.request(port, sprint)
            self.assertEqual(empty_plan['status'], 'empty')
            self.request(port, sprint, 'POST', self.approval(empty_plan), status=409)
            self.assertEqual(self.request(port, tasks), applied)
            self.assertEqual(self.request(port, '/api/jobs'), [])

        with _running_service(self.workspace) as port:
            self.assertEqual(self.request(port, tasks), applied)
            self.assertEqual(self.request(port, sprint), empty_plan)

    def test_sprint_recomputes_after_other_evidence_changes(self):
        with _running_service(self.workspace) as port:
            _, route = self.project(port)
            sprint, tasks = route + '/sprint', route + '/tasks'
            before, initial = self.request(port, tasks), self.request(port, sprint)
            self.add_defect(port, route)
            changed = self.request(port, sprint)
            self.assertEqual(changed['board_revision'], initial['board_revision'])
            self.assertEqual(changed['spec_sha256'], initial['spec_sha256'])
            self.assertNotEqual(changed['plan_id'], initial['plan_id'])
            self.request(port, sprint, 'POST', self.approval(initial), status=409)
            self.assertEqual(self.request(port, tasks), before)
            updated = self.request(port, sprint, 'POST', self.approval(changed))
            self.assertEqual({task['id'] for task in updated['tasks']}, {task['id'] for task in changed['tasks']})
            self.assertEqual(self.gates(self.request(port, route + '/acceptance'))['defects'], 'fail')

    def test_capture_uses_current_audit_and_retains_history_across_spec_edits(self):
        with _running_service(self.workspace) as port:
            project, route = self.project(port)
            _, other = self.project(port, 'Separate Evidence Yard')
            path = route + '/evidence-history'
            empty = self.request(port, path)
            self.assertEqual((empty['revision'], empty['items']), (0, []))
            self.assertEqual(self.gates(self.request(port, route + '/acceptance'))['audit_history'], 'pending')
            approval = self.update(empty, note='Initial audit before the fixture changed.')
            audit = self.request(port, route + '/supervisor')
            for invalid in ({**approval, 'audit': audit}, {**approval, 'note': ' '},
                            {**approval, 'expected_revision': True}):
                self.request(port, path, 'POST', invalid, status=400)
            self.assertEqual(self.request(port, path), empty)
            first = self.request(port, path, 'POST', approval)
            original = first['items'][0]
            self.assertEqual((original['status'], original['checks']), (audit['status'], audit['checks']))
            self.assertEqual(original['note'], approval['note'])

            self.add_defect(port, route)
            live = self.request(port, route + '/supervisor')
            self.request(port, path, 'POST', approval, status=409)
            saved = self.request(port, path, 'POST', self.update(first, note='Captured the blocking defect.'))
            self.assertEqual(saved['revision'], 2)
            self.assertEqual(saved['items'][1], original)
            self.assertEqual(saved['items'][0]['checks'], live['checks'])
            self.assertEqual(saved['items'][0]['status'], 'blocked')
            self.assertEqual(self.gates(self.request(port, route + '/acceptance'))['audit_history'], 'fail')
            self.assertEqual(self.request(port, other + '/evidence-history')['items'], [])

        with _running_service(self.workspace) as port:
            self.assertEqual(self.request(port, path), saved)
            plan = self.request(port, route + '/sprint')
            self.request(port, route + '/sprint', 'POST', self.approval(plan))
            project['spec']['terrain']['amplitude'] += 0.25
            self.request(port, route + '/spec', 'PUT', {'spec': project['spec']})
            historical = self.request(port, path)
            self.assertNotEqual(historical['spec_sha256'], saved['spec_sha256'])
            self.assertEqual(historical['items'], saved['items'])
            self.request(port, path, 'POST', self.update(saved, note='Old spec capture'), status=409)
            stale_board = self.request(port, route + '/tasks')
            blocked = self.request(port, route + '/sprint')
            self.assertEqual(blocked['status'], 'blocked')
            self.request(port, route + '/sprint', 'POST', self.approval(blocked), status=409)
            self.assertEqual(self.request(port, route + '/tasks'), stale_board)
            self.assertEqual(self.request(port, path), historical)
            self.assertEqual(self.gates(self.request(port, route + '/acceptance'))['audit_history'], 'pending')

    def test_routes_enforce_local_scope_and_fail_closed_on_corrupt_sources(self):
        with _running_service(self.workspace) as port:
            project, route = self.project(port)
            directory = self.workspace / 'projects' / project['id']
            before = {file.name: file.read_bytes() for file in directory.iterdir()}
            for resource in ('sprint', 'evidence-history', 'acceptance'):
                path = route + '/' + resource
                self.assertEqual(self.request(port, path)['project_id'], project['id'])
                self.request(port, path, headers={'Host': 'external.invalid'}, status=403)
                self.request(port, path, headers={'Origin': 'http://external.invalid'}, status=403)
                self.request(port, '/api/projects/missing/' + resource, status=404)
                self.request(port, path, 'PUT', {}, status=404)
            self.request(port, route + '/acceptance', 'POST', {}, status=404)
            preview = self.request(port, route + '/sprint')
            capture = self.update(self.request(port, route + '/evidence-history'), note='Capture the current audit.')
            for resource, data in (('sprint', self.approval(preview)), ('evidence-history', capture)):
                path = route + '/' + resource
                self.request(port, '/api/projects/missing/' + resource, 'POST', data, status=404)
                self.request(port, path, 'POST', data, status=403, headers={'Content-Type': 'application/json'})
                self.request(port, path, 'POST', data, status=403, headers={
                    'Content-Type': 'application/json', 'X-Studio-Request': '1', 'Origin': 'http://external.invalid',
                })
            self.assertEqual({file.name: file.read_bytes() for file in directory.iterdir()}, before)

            files = ('task-board.json', 'evidence-history.json')
            corrupt = b'{invalid JSON'
            for name in files:
                (directory / name).write_bytes(corrupt)
            self.assertEqual(self.request(port, route + '/sprint')['status'], 'blocked')
            self.request(port, route + '/sprint', 'POST', self.approval(preview), status=409)
            self.request(port, route + '/evidence-history', status=400)
            self.request(port, route + '/evidence-history', 'POST', capture, status=400)
            acceptance = self.request(port, route + '/acceptance')
            self.assertEqual(acceptance['status'], 'blocked')
            gates = self.gates(acceptance)
            self.assertEqual((gates['task_board'], gates['audit_history'], gates['defects']), ('fail', 'fail', 'pass'))
            self.assertEqual({file.name: file.read_bytes() for file in directory.iterdir()},
                             {**before, **dict.fromkeys(files, corrupt)})
