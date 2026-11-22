"""Verify the academy lab through the real loopback API."""

import json
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path

from command_center.checkpoint_smoke import _running_service

CATALOG = '/api/training-lab'
ASSESS = CATALOG + '/assess'
JSON_HEADERS = {'Content-Type': 'application/json', 'X-Studio-Request': '1'}


class LabHTTPTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory(prefix='studio-lab-http-'))
        self.workspace = Path(directory)
        self.port = self.enterContext(_running_service(self.workspace))
        self.origin = f'http://127.0.0.1:{self.port}'

    def request(self, path, method='GET', data=None, *, status=200, body=None, headers=None):
        if data is not None:
            body = json.dumps(data).encode()
        if headers is None:
            headers = JSON_HEADERS if body is not None else {}
        connection = HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            with connection.getresponse() as response:
                result = json.load(response)
                self.assertEqual(response.status, status, f'{method} {path}: {result}')
                self.assertEqual(response.getheader('Cache-Control'), 'no-store')
                return result
        finally:
            connection.close()

    def assert_error(self, status, path, method='GET', data=None, **kwargs):
        result = self.request(path, method, data, status=status, **kwargs)
        self.assertTrue(result['error'])

    def workspace_snapshot(self):
        contents = {}
        for path in (self.workspace, *self.workspace.rglob('*')):
            info = path.stat()
            body = path.read_bytes() if path.is_file() else None
            contents[path.relative_to(self.workspace)] = (info.st_ino, info.st_mtime_ns, body)
        return contents

    @staticmethod
    def interface_exercise(catalog):
        return next(item for item in catalog['exercises'] if item['id'] == 'interface')

    def test_catalog_example_passes_and_regression_fails_without_workspace_changes(self):
        self.request('/api/projects', 'POST', {'name': 'Lab isolation fixture', 'kind': 'cinematic'}, status=201)
        before = self.workspace_snapshot()

        catalog = self.request(CATALOG, headers={'Origin': self.origin})
        self.assertEqual(self.request(CATALOG), catalog)
        self.assertEqual(catalog['version'], 4)
        self.assertRegex(catalog['lab_sha256'], r'^[0-9a-f]{64}\Z')
        self.assertEqual(len(catalog['exercises']), 28)
        self.assertTrue(catalog['note'])
        exercise = self.interface_exercise(catalog)
        for field in ('title', 'brief', 'roles', 'criteria', 'example'):
            self.assertTrue(exercise[field])

        submission = {'exercise_id': exercise['id'], 'submission': exercise['example']}
        assessment = self.request(ASSESS, 'POST', submission, headers={**JSON_HEADERS, 'Origin': self.origin})
        self.assertEqual(assessment['version'], 4)
        self.assertEqual(assessment['exercise_id'], 'interface')
        self.assertEqual(assessment['lab_sha256'], catalog['lab_sha256'])
        self.assertRegex(assessment['submission_sha256'], r'^[0-9a-f]{64}\Z')
        self.assertRegex(assessment['assessment_sha256'], r'^[0-9a-f]{64}\Z')
        self.assertEqual(assessment['status'], 'pass')
        self.assertEqual(assessment['summary'], {'pass': len(exercise['criteria']), 'fail': 0})
        self.assertEqual([{key: check[key] for key in ('id', 'label')} for check in assessment['checks']],
                         exercise['criteria'])
        self.assertTrue(all(check['status'] == 'pass' and check['detail'] for check in assessment['checks']))
        self.assertTrue(assessment['note'])
        self.assertEqual(self.request(ASSESS, 'POST', submission), assessment)

        widget = submission['submission']['screens'][0]['widgets'][0]
        widget['foreground'] = widget['background']
        failed = self.request(ASSESS, 'POST', submission)
        self.assertEqual(failed['status'], 'fail')
        self.assertGreater(failed['summary']['fail'], 0)
        self.assertIn('contrast', {check['id'] for check in failed['checks'] if check['status'] == 'fail'})
        self.assertNotEqual(failed['submission_sha256'], assessment['submission_sha256'])
        self.assertNotEqual(failed['assessment_sha256'], assessment['assessment_sha256'])
        self.assertEqual(self.workspace_snapshot(), before)

    def test_new_workflows_are_available_as_read_only_practice(self):
        before = self.workspace_snapshot()
        titles = {'cutscenes', 'game-audio', 'multiplayer', 'persistence', 'ai-encounters', 'production-pipeline',
                  'player-enjoyment', 'replayability', 'player-research', 'visual-direction',
                  'visual-readability', 'experience-iteration', 'motion-design', 'character-performance',
                  'environmental-storytelling', 'diegetic-narrative', 'voice-direction', 'voice-integration'}
        tracks = self.request('/api/training')['tracks']
        exercises = self.request(CATALOG)['exercises']
        for exercise in exercises:
            if exercise['id'] not in titles:
                continue
            with self.subTest(exercise=exercise['id']):
                track = next(t for t in tracks if t['id'] == exercise['id'])
                self.assertEqual(track['roles'], exercise['roles'])
                result = self.request(ASSESS, 'POST', {'exercise_id': exercise['id'], 'submission': exercise['example']})
                self.assertEqual(result['status'], 'pass')
                self.assertEqual(result['version'], 4)
                self.assertGreaterEqual(len(result['checks']), 3)
                self.assert_error(400, ASSESS, 'POST', {'exercise_id': exercise['id'], 'submission': {}})
                titles.remove(exercise['id'])
        self.assertFalse(titles)
        self.assertEqual(self.workspace_snapshot(), before)

    def test_assessment_rejects_invalid_payloads(self):
        exercise = self.interface_exercise(self.request(CATALOG))
        valid = {'exercise_id': exercise['id'], 'submission': exercise['example']}
        for data in ([], {}, {'exercise_id': 'interface'}, {'submission': {}},
                     {**valid, 'exercise_id': 'missing-exercise'},
                     {**valid, 'exercise_id': ['interface']},
                     {**valid, 'submission': []},
                     {**valid, 'submission': {}},
                     {**valid, 'command': ['echo', 'exercise data']},
                     {**valid, 'project_id': 'example'}):
            with self.subTest(data=data):
                self.assert_error(400, ASSESS, 'POST', data)
        self.assert_error(400, ASSESS, 'POST', body=b'{')
        self.assert_error(400, ASSESS, 'POST', valid,
                          headers={**JSON_HEADERS, 'Content-Type': 'text/plain'})
        self.assert_error(400, ASSESS, 'POST', valid,
                          headers={**JSON_HEADERS, 'Content-Length': str(1024 * 1024 + 1)})

    def test_assessment_rejects_duplicate_json_keys(self):
        exercise = self.interface_exercise(self.request(CATALOG))
        example = exercise['example']
        body = json.dumps({'exercise_id': exercise['id'], 'submission': example}).encode()
        foreground = json.dumps(example['screens'][0]['widgets'][0]['foreground']).encode()
        field = b'"foreground": ' + foreground
        self.assertIn(field, body)
        top_level = b'{"exercise_id": "interface", ' + body[1:]
        nested = body.replace(field, field + b', ' + field, 1)
        for location, payload in (('top level', top_level), ('nested widget', nested)):
            with self.subTest(location=location):
                self.assert_error(400, ASSESS, 'POST', body=payload)

    def test_routes_enforce_loopback_and_method_scope(self):
        cross_origin = {'Origin': 'http://external.invalid'}
        external_host = {'Host': 'external.invalid'}
        for headers in (cross_origin, external_host):
            with self.subTest(headers=headers):
                self.assert_error(403, CATALOG, headers=headers)
                self.assert_error(403, ASSESS, 'POST', {}, headers={**JSON_HEADERS, **headers})
        self.assert_error(403, ASSESS, 'POST', {}, headers={'Content-Type': 'application/json'})
        self.assert_error(404, CATALOG, 'POST', {})
        self.assert_error(404, ASSESS, 'PUT', {})
        self.assert_error(404, ASSESS)
        self.assert_error(404, '/api/projects/example/training-lab/assess', 'POST', {})
