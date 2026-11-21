import copy
import unittest

from command_center.provenance import spec_digest
from command_center.scheduler import apply_action
from command_center.supervisor import audit_project


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.project = {'id': 'demo', 'spec': {'seed': 23}}
        self.digest = spec_digest(self.project['spec'])
        self.identity = dict(project_id='demo', spec_sha256=self.digest)
        self.job = dict(self.identity, id='1' * 32, status='passed', verified=True,
                        created_at='2026-01-01T00:00:00+00:00', queue_sequence=1)
        self.jobs = [self.job]
        task = dict(id='review', title='Review menu', role='ui', priority=3, depends_on=[], gate='manual')
        self.planned = apply_action([], dict(op='add', task=task))
        self.running = apply_action(self.planned, dict(op='start', task_id='review'))
        done = apply_action(self.running, dict(op='complete', task_id='review', evidence=['Reviewed menu capture']))
        self.board = dict(self.identity, board_spec_sha256=self.digest, revision=3, state='current', tasks=done)
        self.release_id = 'a' * 32
        release = dict(id=self.release_id, job_id=self.job['id'], spec_sha256=self.digest,
                       manifest_sha256='f' * 64, output=f'jobs/{self.job["id"]}/output',
                       created_at='2026-01-02T00:00:00+00:00')
        self.registry = dict(self.identity, active_state='current', active_release_id=self.release_id, releases=[release])
        self.ledger = dict(self.identity, items=[])
        self.profile = dict(self.identity, regression=False,
                            summary=dict(latest_total_seconds=31.5, baseline_total_seconds=32.0))

    def audit(self):
        result = audit_project(self.project, self.jobs, self.board, self.registry, self.ledger, self.profile)
        self.assertEqual(result['spec_sha256'], self.digest)
        self.assertEqual(result['project_id'], self.project['id'])
        self.recs = result['recommendations']
        checks = {check['id']: check for check in result['checks']}
        self.assertEqual(list(checks), ['build', 'release', 'task_board', 'manual_review', 'defects', 'performance'])
        self.assertEqual(len(result['checks']), len(checks))
        for rec in self.recs:
            self.assertIn(checks[rec['id']]['evidence'], rec['evidence'])
            self.assertTrue(rec['detail'] and rec['title'] and rec['role'])
        return result['status'], checks

    def test_fully_evidenced_pass_is_pure_and_deterministic(self):
        inputs = (self.project, self.jobs, self.board, self.registry, self.ledger, self.profile)
        original = copy.deepcopy(inputs)
        status, checks = self.audit()
        self.assertEqual(status, 'pass')
        self.assertEqual({row['status'] for row in checks.values()}, {'pass'})
        self.assertEqual(self.recs, [])
        self.assertEqual(inputs, original)
        self.assertEqual(audit_project(*inputs), audit_project(*copy.deepcopy(inputs)))

    def test_empty_sources_are_pending_and_zero_recorded_defects_pass(self):
        self.jobs = []
        self.registry.update(active_state='empty', active_release_id=None, releases=[])
        self.board.update(state='empty', board_spec_sha256=None, tasks=[])
        self.profile.update(regression=None, summary={})
        status, checks = self.audit()
        self.assertEqual(status, 'pending')
        self.assertEqual(checks['defects']['status'], 'pass')
        self.assertTrue(all(check['status'] == 'pending' for key, check in checks.items() if key != 'defects'))

    def test_unavailable_sources_and_concurrent_spec_change_fail_closed(self):
        self.jobs = self.registry = self.board = self.profile = self.ledger = None
        status, checks = self.audit()
        self.assertEqual(status, 'blocked')
        self.assertTrue(all(row['status'] == 'fail' and 'unavailable' in row['evidence'] for row in checks.values()))
        self.ledger = dict(self.identity, spec_sha256='b' * 64, items=[])
        self.assertIn('current specification', self.audit()[1]['defects']['evidence'])

    def test_newest_current_job_wins_and_unverified_results_fail(self):
        failed = dict(self.job, id='2' * 32, status='failed', verified=False, queue_sequence=2)
        stale = dict(self.job, id='3' * 32, queue_sequence=3, spec_sha256='d' * 64)
        foreign = dict(self.job, id='4' * 32, queue_sequence=4, project_id='other')
        self.jobs = [foreign, self.job, stale, failed]
        status, checks = self.audit()
        self.assertEqual(status, 'blocked')
        self.assertIn(failed['id'], checks['build']['evidence'])
        self.assertEqual(checks['release']['status'], 'pass')
        failed.update(status='passed', verified='true')
        self.assertEqual(self.audit()[1]['build']['status'], 'fail')
        failed.update(verified=True)
        self.assertEqual(self.audit()[1]['build']['status'], 'pass')
        for state in ('queued', 'running', 'canceled'):
            failed.update(status=state)
            self.assertEqual(self.audit()[1]['build']['status'], 'pending')
        self.jobs = [stale, foreign]
        self.assertEqual(self.audit()[1]['build']['status'], 'pending')

    def test_legacy_job_chronology_uses_absolute_times_and_rejects_ambiguity(self):
        self.jobs[0].pop('queue_sequence')
        later = dict(self.job, id='9' * 32, status='failed', created_at='2025-12-31T22:00:01-02:00')
        self.jobs.append(later)
        self.assertIn(later['id'], self.audit()[1]['build']['evidence'])
        later['created_at'] = 'bad date'
        self.assertIn('order', self.audit()[1]['build']['evidence'])
        self.jobs = [{'id': 'c' * 32, 'project_id': None, 'status': 'failed'}]
        self.assertEqual(self.audit()[1]['build']['status'], 'fail')

    def test_stale_release_and_stale_board_cannot_certify_current_work(self):
        old = 'e' * 64
        self.registry['releases'][0]['spec_sha256'] = old
        self.registry['active_state'] = 'stale'
        self.board.update(board_spec_sha256=old, state='stale')
        status, checks = self.audit()
        self.assertEqual(status, 'attention')
        self.assertEqual(checks['release']['status'], 'warn')
        self.assertEqual(checks['task_board']['status'], 'warn')
        self.assertEqual(checks['manual_review']['status'], 'pending')
        self.registry['active_state'] = 'current'
        self.assertEqual(self.audit()[1]['release']['status'], 'fail')
        self.board['state'] = 'current'
        self.assertEqual(self.audit()[1]['task_board']['status'], 'fail')

    def test_invalid_active_release_blocks_and_controlled_integrity_errors_are_reported(self):
        self.registry['active_state'] = 'invalid'
        status, checks = self.audit()
        self.assertEqual(status, 'blocked')
        self.assertEqual(checks['release']['status'], 'fail')
        self.assertEqual(self.recs[0]['severity'], 'critical')
        for key, value in [('active_release_id', 'unknown'), ('releases', [])]:
            with self.subTest(key=key):
                self.registry[key] = value
                self.assertEqual(self.audit()[1]['release']['status'], 'fail')

    def test_manual_gate_requires_current_completion_with_evidence(self):
        self.board['tasks'] = self.running
        status, checks = self.audit()
        self.assertEqual(status, 'pending')
        self.assertIn('1 running', checks['task_board']['evidence'])
        self.assertEqual(checks['manual_review']['status'], 'pending')
        self.board['tasks'] = apply_action(self.running, dict(op='block', task_id='review', reason='Need device'))
        status, checks = self.audit()
        self.assertEqual(status, 'blocked')
        self.assertIn('review', checks['task_board']['evidence'])
        self.board['tasks'] = [dict(self.running[0], status='completed', evidence=[])]
        self.assertEqual(self.audit()[1]['manual_review']['status'], 'fail')

    def test_open_defects_use_only_current_status_severity_and_stable_priority(self):
        issue = dict(id='c' * 32, spec_sha256=self.digest, severity='medium', status='open')
        old = dict(issue, id='d' * 32, spec_sha256='e' * 64, severity='critical')
        closed = dict(issue, id='f' * 32, severity='critical', status='resolved')
        self.ledger['items'] = [old, issue, closed]
        status, checks = self.audit()
        self.assertEqual(status, 'attention')
        self.assertIn(issue['id'], checks['defects']['evidence'])
        self.assertNotIn(old['id'], checks['defects']['evidence'])
        self.assertEqual(self.recs[0]['severity'], 'medium')
        self.registry['active_state'] = 'invalid'
        issue.update(severity='high')
        self.assertEqual(self.audit()[1]['defects']['status'], 'fail')
        self.assertEqual([rec['severity'] for rec in self.recs], ['critical', 'high'])
        issue.update(severity='critical')
        self.assertEqual(self.audit()[0], 'blocked')
        self.assertEqual([rec['id'] for rec in self.recs], ['defects', 'release'])
        issue.update(status='resolved')
        self.assertEqual(self.audit()[1]['defects']['status'], 'pass')

    def test_measured_timing_regression_and_invalid_comparison(self):
        self.profile.update(regression=True, summary=dict(latest_total_seconds=60.5, baseline_total_seconds=32))
        status, checks = self.audit()
        self.assertEqual(status, 'attention')
        self.assertIn('60.5 seconds', checks['performance']['evidence'])
        self.assertNotIn('FPS', checks['performance']['evidence'])
        self.profile['summary']['baseline_total_seconds'] = 0
        self.assertEqual(self.audit()[1]['performance']['status'], 'fail')
        self.profile['regression'] = None
        self.assertEqual(self.audit()[1]['performance']['status'], 'pending')
        self.profile = dict(self.profile, project_id='elsewhere', regression=False)
        self.assertEqual(self.audit()[1]['performance']['status'], 'fail')


if __name__ == '__main__':
    unittest.main()
