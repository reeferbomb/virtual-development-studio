"""Exercise restart, recovery, shared capacity and actual build evidence over HTTP."""

import tempfile
import unittest
from pathlib import Path

from command_center.checkpoint_smoke import _request, _running_service
from command_center.orchestration_smoke import _wait_job
from command_center.scheduler_smoke import Board, _create_project


class CoordinationIntegrationTests(unittest.TestCase):
    def test_recover_reviewed_blocker_and_verify_build_after_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            with _running_service(workspace) as port:
                a = _create_project(port, 'Alpha Coordination')
                b = _create_project(port, 'Zulu Coordination')
                first, second = Board(port, a['id']), Board(port, b['id'])
                first.add('build', 'Build first project', 'build_operations', 4, gate='build')
                second.add('build', 'Build second project', 'build_operations', 4, gate='build')
                second.add('review', 'Review build', 'verification', 3, depends_on=['build'])
                route = second.project_route
                advice = _request(port, '/api/portfolio')
                self.assertEqual(advice['assignments'][0]['project_id'], b['id'])
                second.apply('start', task_id='build')
                allocation = _request(port, '/api/allocation')
                builder = next(r for r in allocation['roles'] if r['role'] == 'build_operations')
                self.assertEqual((builder['state'], builder['project_ids']), ('occupied', [b['id']]))
                order = _request(port, route + '/work-orders')['orders'][0]
                ledger = _request(port, route + '/handoffs')

                def handoff(action):
                    nonlocal ledger
                    ledger = _request(port, route + '/handoffs', 'POST', {
                        'expected_revision': ledger['revision'], 'spec_sha256': ledger['spec_sha256'], 'action': action})

                handoff(dict(op='submit', task_id='build', order_id=order['order_id'], outcome='blocked',
                             summary='Fixture inputs require review.', evidence=['Read the fixture specification.'],
                             changed_paths=[], next_action='Review fixture inputs.'))
                handoff_id = ledger['items'][0]['id']
                handoff(dict(op='review', handoff_id=handoff_id, decision='accepted', note='Reviewed observation.'))
                second.apply('block', task_id='build', reason='Review fixture inputs before building.')
                memory = _request(port, route + '/specialist-memory')
                recovery = _request(port, route + '/recovery-advice')
                self.assertEqual(recovery['items'][0]['handoff_id'], handoff_id)
                self.assertEqual(recovery['items'][0]['affected_count'], 1)
                self.assertEqual(_request(port, second.route), second.state)

            with _running_service(workspace) as port:
                second = Board(port, b['id'])
                self.assertEqual(_request(port, route + '/specialist-memory'), memory)
                self.assertEqual(_request(port, route + '/recovery-advice'), recovery)
                second.apply('requeue', task_id='build')
                self.assertEqual(_request(port, route + '/recovery-advice')['items'], [])
                self.assertEqual(_request(port, route + '/priorities')['recommendations'][0]['task_id'], 'build')
                second.apply('start', task_id='build')
                job = _request(port, route + '/build', 'POST', {'priority': 4}, expected_status=202)
                done = _wait_job(port, job['id'])
                self.assertEqual((done['status'], done['verified']), ('passed', True))
                second.apply('complete', task_id='build', evidence=['Verified build ' + done['id']], job_id=done['id'])
                self.assertEqual(_request(port, route + '/priorities')['recommendations'][0]['task_id'], 'review')
                self.assertEqual(second.task('build')['attempts'], 2)
                b['spec']['terrain']['amplitude'] += .25
                _request(port, route + '/spec', 'PUT', {'spec': b['spec']})
                self.assertEqual(_request(port, route + '/specialist-memory')['historical_count'], 1)
                self.assertEqual(_request(port, route + '/priorities')['status'], 'stale')
                self.assertEqual(_request(port, route + '/recovery-advice')['status'], 'stale')
