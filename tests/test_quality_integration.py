"""Exercise curriculum-bearing work orders and quality evidence with an actual build."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from command_center.checkpoint_smoke import _request, _running_service
from command_center.orchestration_smoke import _wait_job
from command_center.quality_cli import main
from command_center.scheduler_smoke import Board, _create_project
from command_center.studio_curriculum import curriculum


class QualityIntegrationTests(unittest.TestCase):
    def test_curriculum_claim_review_build_and_quality_trend(self):
        with tempfile.TemporaryDirectory() as temporary:
            with _running_service(Path(temporary)) as port:
                project = _create_project(port, 'Academy Quality Fixture')
                board = Board(port, project['id'])
                route = board.project_route
                board.add('build', 'Build the playable fixture', 'build_operations', 4, gate='build')
                board.add('review', 'Review the build', 'verification', 3, depends_on=['build'])
                self.assertEqual(_request(port, '/api/training'), curriculum())
                baseline = _request(port, route + '/evidence-history')
                _request(port, route + '/evidence-history', 'POST', {
                    'expected_revision': baseline['revision'], 'spec_sha256': baseline['spec_sha256'],
                    'note': 'Capture the initial local quality audit.'})
                before = _request(port, route + '/quality-matrix')
                self.assertEqual(next(c['status'] for c in before['checks'] if c['id'] == 'build'), 'pending')
                cycle = _request(port, '/api/dispatch-cycle')
                self.assertEqual(cycle['status'], 'ready')
                step, = cycle['steps']
                payload = {key: step[key] for key in ('expected_revision', 'spec_sha256', 'action')}
                board.state = _request(port, board.route, 'PUT', payload)
                _request(port, board.route, 'PUT', payload, expected_status=409)
                order, = _request(port, route + '/work-orders')['orders']
                self.assertIn('Game development and gameplay engineering', order['spawn_args']['message'])
                self.assertIn('Build operations, performance, and asset provenance', order['spawn_args']['message'])
                job = _request(port, route + '/build', 'POST', {'priority': 4}, expected_status=202)
                done = _wait_job(port, job['id'])
                self.assertEqual((done['status'], done['verified']), ('passed', True))
                ledger = _request(port, route + '/handoffs')
                ledger = _request(port, route + '/handoffs', 'POST', {
                    'expected_revision': ledger['revision'], 'spec_sha256': ledger['spec_sha256'],
                    'action': dict(op='submit', task_id='build', order_id=order['order_id'],
                                   outcome='completed', summary='Fixture built.',
                                   evidence=['Verified build ' + done['id']], changed_paths=[],
                                   next_action='Lead review.')})
                _request(port, route + '/handoffs', 'POST', {
                    'expected_revision': ledger['revision'], 'spec_sha256': ledger['spec_sha256'],
                    'action': dict(op='review', handoff_id=ledger['items'][0]['id'],
                                   decision='accepted', note='Reviewed verified build.')})
                board.apply('complete', task_id='build', evidence=['Verified build ' + done['id']], job_id=done['id'])
                after = _request(port, route + '/quality-matrix')
                self.assertEqual(next(c['status'] for c in after['checks'] if c['id'] == 'build'), 'pass')
                trends = _request(port, route + '/quality-trends')
                self.assertEqual(next(c['trend'] for c in trends['checks'] if c['id'] == 'build'), 'improved')
                analytics = _request(port, route + '/specialist-analytics')
                builder = next(r for r in analytics['roles'] if r['role'] == 'build_operations')
                self.assertEqual((builder['submitted'], builder['accepted'], builder['completed']), (1, 1, 1))
                self.assertEqual(_request(port, '/api/dispatch-cycle')['steps'][0]['task_id'], 'review')
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main([project['id'], '--port', str(port)]), 1)
                self.assertEqual(json.loads(output.getvalue()), after)
