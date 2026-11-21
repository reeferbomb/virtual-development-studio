import copy
import unittest

from command_center.acceptance import assess_acceptance
from command_center.provenance import spec_digest
from command_center.scheduler import apply_action
from command_center.supervisor import audit_project


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.project = {'id': 'demo', 'spec': {'seed': 23}}
        self.digest = spec_digest(self.project['spec'])
        self.scope = dict(project_id='demo', spec_sha256=self.digest)
        self.jobs = [dict(self.scope, id='1' * 32, status='passed', verified=True)]
        release = dict(id='2' * 32, spec_sha256=self.digest)
        self.registry = dict(self.scope, releases=[release], active_release_id=release['id'], active_state='current')
        definition = dict(id='review', title='Review settings', role='ui', priority=3, depends_on=[], gate='manual')
        tasks = apply_action([], {'op': 'add', 'task': definition})
        self.running = apply_action(tasks, dict(op='start', task_id='review'))
        done = apply_action(self.running, dict(op='complete', task_id='review', evidence=['Reviewed settings on device']))
        self.board = dict(self.scope, board_spec_sha256=self.digest, revision=3, state='current', tasks=done)
        self.defects = dict(self.scope, revision=0, items=[], summary=self.counts())
        self.profile = dict(self.scope, regression=False, summary=dict(latest_total_seconds=12, baseline_total_seconds=12))
        self.audit = self.live_audit()
        self.history = dict(self.scope, revision=0, items=[])
        self.capture()

    @staticmethod
    def counts(**changes):
        return dict(current_open=0, current_resolved=0, historical_open=0, historical_resolved=0) | changes

    def live_audit(self):
        return audit_project(self.project, self.jobs, self.board, self.registry, self.defects, self.profile)

    def capture(self):
        revision = self.history['revision'] + 1
        snapshot = dict(id=f'{revision:032x}', spec_sha256=self.digest, checks=copy.deepcopy(self.audit['checks']),
                        status=self.audit['status'], note='Observed local verification', created_at='2026-01-02T00:00:00+00:00')
        self.history['items'].insert(0, snapshot)
        self.history['revision'] = revision
        return snapshot

    def report(self):
        return assess_acceptance(self.project, self.audit, self.board, self.defects, self.history)

    def check(self, gate_id, expected_status, expected_gate):
        report = self.report()
        self.assertEqual(report['status'], expected_status, report)
        gate = next(row for row in report['gates'] if row['id'] == gate_id)
        self.assertEqual(gate['status'], expected_gate, gate)
        self.assertTrue(gate['evidence'].strip())
        return gate['evidence']

    def test_ready_report_is_deterministic_and_does_not_mutate_inputs(self):
        sources = [self.project, self.audit, self.board, self.defects, self.history]
        before = copy.deepcopy(sources)
        result = self.report()
        self.assertEqual(result, assess_acceptance(*before))
        self.assertEqual(sources, before)
        self.assertEqual(result['project_id'], 'demo')
        self.assertEqual(result['spec_sha256'], self.digest)
        self.assertEqual(result['status'], 'ready')
        self.assertIn('operator review', result['summary'])
        self.assertEqual([gate['id'] for gate in result['gates']],
                         ['build', 'release', 'task_board', 'manual_review', 'defects', 'performance', 'audit_history'])
        self.assertTrue(all(gate['status'] == 'pass' and gate['label'] and gate['evidence'] for gate in result['gates']))

    def test_pass_requires_an_explicit_current_capture(self):
        self.history['items'][0]['spec_sha256'] = 'a' * 64
        self.check('audit_history', 'pending', 'pending')
        self.history.update(revision=0, items=[])
        self.check('audit_history', 'pending', 'pending')

    def test_a_newer_failed_capture_supersedes_an_older_pass_even_in_a_time_tie(self):
        self.jobs[0]['status'] = 'failed'
        self.audit = self.live_audit()
        latest = self.capture()
        self.jobs[0]['status'] = 'passed'
        self.audit = self.live_audit()
        self.assertIn(latest['id'], self.check('audit_history', 'blocked', 'fail'))
        self.capture()
        self.check('audit_history', 'ready', 'pass')

    def test_passing_capture_cannot_mask_a_live_warning_or_pending_build(self):
        self.profile['regression'] = True
        self.audit = self.live_audit()
        self.assertIn('regression', self.check('performance', 'blocked', 'fail'))
        self.profile['regression'] = False
        self.jobs[0]['status'] = 'queued'
        self.audit = self.live_audit()
        self.check('build', 'pending', 'pending')
        self.registry['active_state'] = 'invalid'
        self.audit = self.live_audit()
        self.check('release', 'blocked', 'fail')

    def test_board_read_after_live_audit_checks_manual_evidence_and_scope(self):
        self.board['tasks'] = self.running
        self.check('task_board', 'pending', 'pending')
        self.check('manual_review', 'pending', 'pending')
        self.board['tasks'] = [dict(self.running[0], status='completed', evidence=[])]
        self.check('manual_review', 'blocked', 'fail')
        self.board.update(tasks=self.running, state='stale', board_spec_sha256='f' * 64)
        self.check('task_board', 'blocked', 'fail')

    def test_every_open_severity_blocks_even_after_passing_live_audit(self):
        when = '2026-01-02T00:00:00+00:00'
        item = dict(id='3' * 32, spec_sha256=self.digest, status='open', title='Missing icon',
                    description='Settings icon is blank', evidence=['Observed in settings'], created_at=when, updated_at=when)
        self.defects.update(items=[item], revision=1, summary=self.counts(current_open=1))
        for severity in ('low', 'medium', 'high', 'critical'):
            with self.subTest(severity=severity):
                item['severity'] = severity
                self.assertIn(item['id'], self.check('defects', 'blocked', 'fail'))
        item['spec_sha256'] = 'e' * 64
        self.defects['summary'] = self.counts(historical_open=1)
        self.check('defects', 'ready', 'pass')
        item['spec_sha256'] = self.digest
        item.update(status='resolved', evidence=['Observed in settings', 'Confirmed fix on device'])
        self.defects.update(revision=2, summary=self.counts(current_resolved=1))
        self.check('defects', 'ready', 'pass')

    def test_corrupt_or_wrong_scope_sources_fail_closed(self):
        sources = [('audit', 'build'), ('board', 'task_board'), ('defects', 'defects'), ('history', 'audit_history')]
        for name, gate in sources:
            original = getattr(self, name)
            for bad in (None, {}, dict(original, project_id='elsewhere'), dict(original, spec_sha256='b' * 64)):
                with self.subTest(name=name, bad=bad):
                    setattr(self, name, bad)
                    self.check(gate, 'blocked', 'fail')
            setattr(self, name, original)
        self.audit['checks'].pop()
        self.check('build', 'blocked', 'fail')
        self.audit = self.live_audit()
        self.history['items'][0]['checks'][0]['status'] = 'fail'
        self.check('audit_history', 'blocked', 'fail')
        self.board['revision'] = False
        self.check('task_board', 'blocked', 'fail')
        self.defects['summary']['current_open'] = 1
        self.check('defects', 'blocked', 'fail')

    def test_invalid_project_identity_cannot_produce_ready(self):
        for bad in (None, {}, {'id': [], 'spec': {}}, {'id': 'demo'}, {'id': 'demo', 'spec': {'seed': float('nan')}}):
            with self.subTest(project=bad):
                self.project = bad
                report = self.report()
                self.assertEqual(report['status'], 'blocked')
                self.assertIsNone(report['spec_sha256'])
                self.assertTrue(all(row['status'] == 'fail' for row in report['gates']))


if __name__ == '__main__':
    unittest.main()
