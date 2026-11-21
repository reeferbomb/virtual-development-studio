"""Exercise the academy practice records through the real local API."""

import json
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from command_center import training_lab
from command_center.checkpoint_smoke import _running_service


RECORDS = '/api/training-records'
PROGRESS = '/api/training-progress'
JSON_HEADERS = {'Content-Type': 'application/json', 'X-Studio-Request': '1'}


def inventory_submission():
    return {
        'screens': [
            {'width': 1600, 'height': 900, 'widgets': [
                {'id': 'stock', 'rect': [64, 72, 512, 450], 'foreground': '#FFFFFF',
                 'background': '#23252B', 'text_px': 22},
                {'id': 'back', 'rect': [64, 550, 160, 44], 'foreground': '#FFFFFF',
                 'background': '#003B5C', 'text_px': 19},
            ]},
            {'width': 768, 'height': 480, 'widgets': [
                {'id': 'stock', 'rect': [24, 40, 420, 320], 'foreground': '#FFFFFF',
                 'background': '#23252B', 'text_px': 18},
                {'id': 'back', 'rect': [24, 380, 120, 40], 'foreground': '#FFFFFF',
                 'background': '#003B5C', 'text_px': 16},
            ]},
        ],
        'navigation': {'start': 'stock', 'edges': [['stock', 'back'], ['back', 'stock']]},
        'actions': {'keyboard': {'move': 'tab', 'select': 'enter', 'back': 'esc', 'inventory': 'b'},
                    'controller': {'move': 'dpad', 'select': 'south', 'back': 'east', 'inventory': 'menu'}},
        'states': {'empty': 'Nothing in the backpack', 'full': 'All slots occupied',
                   'error': 'This item is locked'},
    }


def record_request(submission, revision=0):
    return {'expected_revision': revision, 'action': {
        'op': 'record', 'exercise_id': 'interface', 'role': 'ui', 'submission': submission,
    }}


def review_request(record_id, revision, reviewer='verification', decision='accepted'):
    return {'expected_revision': revision, 'action': {
        'op': 'review', 'record_id': record_id, 'reviewer_role': reviewer,
        'decision': decision, 'note': 'Compared the declared HUD with the rubric.',
    }}


class TrainingRecordsHTTPTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory(prefix='studio-records-http-'))
        self.workspace = Path(directory)

    def request(self, port, path=RECORDS, *, method='GET', data=None, body=None, headers=None, status=200):
        if data is not None:
            body = json.dumps(data).encode()
        if headers is None:
            headers = JSON_HEADERS if body is not None else {}
        connection = HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            with connection.getresponse() as response:
                result = json.load(response)
                self.assertEqual(response.status, status, f'{method} {path}: {result}')
                self.assertEqual(response.getheader('Cache-Control'), 'no-store')
                if status >= 400:
                    self.assertEqual(set(result), {'error'})
                    self.assertTrue(result['error'])
                return result
        finally:
            connection.close()

    def workspace_snapshot(self):
        return {path.relative_to(self.workspace): (path.stat().st_mtime_ns,
                                                    path.read_bytes() if path.is_file() else None)
                for path in (self.workspace, *self.workspace.rglob('*'))}

    def test_absent_records_read_is_empty_and_does_not_write(self):
        with _running_service(self.workspace) as port:
            before = self.workspace_snapshot()
            catalog = self.request(port, '/api/training-lab')
            empty = self.request(port)
            self.assertEqual(set(empty), {'revision', 'lab_sha256', 'records', 'note'})
            self.assertEqual(empty['revision'], 0)
            self.assertEqual(empty['records'], [])
            self.assertEqual(empty['lab_sha256'], catalog['lab_sha256'])
            self.assertTrue(empty['note'])
            self.assertEqual(self.workspace_snapshot(), before)

    def test_records_persist_across_server_restart_without_credentials(self):
        submission = inventory_submission()
        with _running_service(self.workspace) as port:
            saved = self.request(port, method='POST', data=record_request(submission))
            self.assertEqual(saved['revision'], 1)
            record, = saved['records']
            self.assertEqual(set(record), {'id', 'exercise_id', 'role', 'created_at', 'reference',
                                           'submission', 'report', 'review', 'current'})
            self.assertEqual(record['exercise_id'], 'interface')
            self.assertEqual(record['role'], 'ui')
            self.assertEqual(record['submission'], submission)
            self.assertEqual(record['report']['status'], 'pass')
            self.assertEqual(record['report']['lab_sha256'], saved['lab_sha256'])
            self.assertIs(record['current'], True)
            self.assertIs(record['reference'], False)
            self.assertIsNone(record['review'])
            self.assertTrue(record['id'])
            self.assertTrue(record['created_at'])

        with _running_service(self.workspace) as restarted_port:
            self.assertEqual(self.request(restarted_port), saved)

    def test_record_with_stale_assessment_digest_conflicts_without_writing(self):
        submission = inventory_submission()
        assessment = {'exercise_id': 'interface', 'submission': submission}
        with _running_service(self.workspace) as port:
            path = '/api/training-lab/assess'
            previous = self.request(port, path, method='POST', data=assessment)
            empty = self.request(port)
            before = self.workspace_snapshot()

            submission['states']['empty'] = 'Nothing in stock'
            data = record_request(submission)
            data['action']['expected_assessment_sha256'] = previous['assessment_sha256']
            self.request(port, method='POST', data=data, status=409)
            self.assertEqual(self.request(port), empty)
            self.assertEqual(self.workspace_snapshot(), before)

            current = self.request(port, path, method='POST', data=assessment)
            data['action']['expected_assessment_sha256'] = current['assessment_sha256']
            saved = self.request(port, method='POST', data=data)
            self.assertEqual(saved['revision'], 1)
            record, = saved['records']
            self.assertEqual(record['submission'], submission)
            self.assertEqual(record['report'], current)

    def test_review_checks_revision_and_distinct_reviewer(self):
        with _running_service(self.workspace) as port:
            saved = self.request(port, method='POST', data=record_request(inventory_submission()))
            record, = saved['records']
            before = self.workspace_snapshot()
            self.request(port, method='POST', data=review_request(record['id'], 0), status=409)
            self.request(port, method='POST', data=review_request(record['id'], 1, reviewer='ui'), status=400)
            self.assertEqual(self.request(port), saved)
            self.assertEqual(self.workspace_snapshot(), before)

            reviewed = self.request(port, method='POST', data=review_request(record['id'], 1))
            self.assertEqual(reviewed['revision'], 2)
            review = reviewed['records'][0]['review']
            self.assertEqual(set(review), {'reviewer_role', 'decision', 'note', 'reviewed_at'})
            self.assertEqual(review['reviewer_role'], 'verification')
            self.assertEqual(review['decision'], 'accepted')
            self.assertEqual(review['note'], 'Compared the declared HUD with the rubric.')
            self.assertTrue(review['reviewed_at'])
            self.assertEqual({**reviewed['records'][0], 'review': None}, record)
            self.assertEqual(self.request(port), reviewed)

    def test_review_cannot_accept_a_reference_or_a_failing_record(self):
        with _running_service(self.workspace) as port:
            catalog = self.request(port, '/api/training-lab')
            example = next(item['example'] for item in catalog['exercises'] if item['id'] == 'interface')
            saved = self.request(port, method='POST', data=record_request(example))
            reference, = saved['records']
            self.assertIs(reference['reference'], True)
            self.assertEqual(reference['report']['status'], 'pass')
            self.request(port, method='POST', data=review_request(reference['id'], 1), status=400)
            self.assertEqual(self.request(port), saved)

            submission = inventory_submission()
            del submission['states']['empty']
            saved = self.request(port, method='POST', data=record_request(submission, revision=1))
            failed = next(item for item in saved['records'] if item['id'] != reference['id'])
            self.assertIs(failed['reference'], False)
            self.assertEqual(failed['report']['status'], 'fail')
            self.request(port, method='POST', data=review_request(failed['id'], 2), status=400)
            self.assertEqual(self.request(port), saved)

            rejected = self.request(port, method='POST', data=review_request(failed['id'], 2, decision='rejected'))
            self.assertEqual(rejected['revision'], 3)
            decision = next(item['review'] for item in rejected['records'] if item['id'] == failed['id'])
            self.assertEqual(decision['decision'], 'rejected')

    def test_catalog_change_keeps_old_records_read_only(self):
        with _running_service(self.workspace) as port:
            saved = self.request(port, method='POST', data=record_request(inventory_submission()))
            record, = saved['records']
        before = self.workspace_snapshot()

        with (patch.object(training_lab, 'VERSION', training_lab.VERSION + 1),
              _running_service(self.workspace) as port):
            historical = self.request(port)
            self.assertEqual(historical['revision'], saved['revision'])
            self.assertNotEqual(historical['lab_sha256'], saved['lab_sha256'])
            self.assertEqual(historical['records'], [{**record, 'current': False}])
            self.request(port, method='POST', data=review_request(record['id'], 1), status=409)
            self.assertEqual(self.request(port), historical)
            self.assertEqual(self.workspace_snapshot(), before)

    def test_post_rejects_malformed_and_oversized_requests_without_writes(self):
        valid = record_request(inventory_submission())
        invalid = {
            'array': [],
            'empty': {},
            'boolean revision': {**valid, 'expected_revision': True},
            'negative revision': {**valid, 'expected_revision': -1},
            'extra field': {**valid, 'api_key': 'unexpected field'},
            'unassigned role': {**valid, 'action': {**valid['action'], 'role': 'build_operations'}},
            'oversized submission': {**valid, 'action': {**valid['action'], 'submission': {'text': 'a' * 4097}}},
        }
        with _running_service(self.workspace) as port:
            before = self.workspace_snapshot()
            for label, data in invalid.items():
                with self.subTest(label=label):
                    self.request(port, method='POST', data=data, status=400)
            self.request(port, method='POST', body=b'{', status=400)
            self.request(port, method='POST', data=valid, status=400,
                         headers={**JSON_HEADERS, 'Content-Type': 'text/plain'})
            self.request(port, method='POST', data=valid, status=400,
                         headers={**JSON_HEADERS, 'Content-Length': str(1024 * 1024 + 1)})
            self.assertEqual(self.workspace_snapshot(), before)

    def test_post_rejects_duplicate_json_keys_without_writes(self):
        body = json.dumps(record_request(inventory_submission())).encode()
        background = b'"background": "#23252B"'
        self.assertIn(background, body)
        duplicates = {'top level': b'{"expected_revision":0,' + body[1:],
                      'nested widget': body.replace(background, background + b', ' + background, 1)}
        with _running_service(self.workspace) as port:
            before = self.workspace_snapshot()
            for label, malformed in duplicates.items():
                with self.subTest(label=label):
                    self.request(port, method='POST', body=malformed, status=400)
            self.assertEqual(self.workspace_snapshot(), before)

    def test_routes_enforce_loopback_request_header_and_method_scope(self):
        with _running_service(self.workspace) as port:
            valid = record_request(inventory_submission())
            for external in ({'Origin': 'http://external.invalid'}, {'Host': 'external.invalid'}):
                with self.subTest(headers=external):
                    self.request(port, headers=external, status=403)
                    self.request(port, PROGRESS, headers=external, status=403)
                    self.request(port, method='POST', data=valid, headers={**JSON_HEADERS, **external}, status=403)
            self.request(port, method='POST', data=valid, headers={'Content-Type': 'application/json'}, status=403)
            self.request(port, method='PUT', data=valid, status=404)
            self.request(port, PROGRESS, method='POST', data=valid, status=404)
            self.assertEqual(self.request(port)['revision'], 0)

    def test_progress_reflects_saved_records_without_writes(self):
        with _running_service(self.workspace) as port:
            before = self.workspace_snapshot()
            empty = self.request(port, PROGRESS)
            self.assertEqual(empty['revision'], 0)
            self.assertEqual(empty['summary']['records'], 0)
            self.assertEqual(self.workspace_snapshot(), before)

            saved = self.request(port, method='POST', data=record_request(inventory_submission()))
            before = self.workspace_snapshot()
            progress = self.request(port, PROGRESS)
            self.assertEqual(progress['revision'], 1)
            self.assertEqual(progress['lab_sha256'], saved['lab_sha256'])
            self.assertEqual(progress['summary']['records'], 1)
            self.assertEqual(progress['summary']['current'], 1)
            self.assertEqual(progress['summary']['pending'], 1)
            self.assertNotIn('Nothing in the backpack', json.dumps(progress))
            self.assertEqual(self.workspace_snapshot(), before)
