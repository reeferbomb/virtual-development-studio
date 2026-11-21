import copy
import hashlib
import json
import unittest

from command_center.acceptance import assess_acceptance
from command_center.dossier import build_dossier
from command_center.performance import profile_jobs
from command_center.provenance import spec_digest
from command_center.scheduler import apply_action
from command_center.supervisor import audit_project
from command_center.task_store import _projection
from command_center.work_orders import order_id


class DossierTests(unittest.TestCase):
    def setUp(self):
        self.project = dict(id='demo', name='Demo', kind='multiplayer', spec={})
        self.digest = spec_digest({})
        self.scope = dict(project_id='demo', spec_sha256=self.digest)
        self.jobs = [self.job(index) for index in range(1, 4)]
        self.release = dict(id='a' * 32, spec_sha256=self.digest, job_id=self.jobs[-1]['id'],
                            manifest_sha256='c' * 64, created_at=self.jobs[-1]['created_at'],
                            output='jobs/' + self.jobs[-1]['id'] + '/output')
        self.registry = dict(self.scope, revision=1, active_state='current',
                             active_release_id=self.release['id'], releases=[self.release])
        definition = dict(id='review', title='Review input', role='ui', priority=2, depends_on=[], gate='manual')
        tasks = apply_action([], dict(op='add', task=definition))
        self.running = apply_action(tasks, dict(op='start', task_id='review'))
        self.done = apply_action(self.running, dict(op='complete', task_id='review', evidence=['Reviewed input.']))
        self.board = self.board_at(3, self.done)
        self.defects = dict(self.scope, revision=0, items=[])
        self.history = dict(self.scope, revision=0, items=[])
        self.handoffs = dict(self.scope, revision=0, items=[])
        self.audit, _ = self.live()
        self.history.update(revision=1, items=[dict(id='4' * 32, spec_sha256=self.digest, status='pass',
                                                    checks=copy.deepcopy(self.audit['checks']), note='Reviewed',
                                                    created_at='2026-01-01T00:00:00+00:00')])
        self.audit, self.acceptance = self.live()

    def board_at(self, revision, tasks):
        record = dict(self.scope, revision=revision, tasks=tasks) if revision else None
        return _projection('demo', self.digest, record)

    def job(self, i):
        stamp = f'2026-01-01T00:{i // 60:02}:{i % 60:02}+00:00'
        return dict(self.scope, id=f'{i:032x}', kind='multiplayer', status='passed', verified=True, queue_sequence=i,
                    created_at=stamp, started_at=stamp, manifest_sha256='c' * 64,
                    commands=[dict(stage=stage, exit_code=0, duration_seconds=2, argv=['/private/build/tool'])
                              for stage in ('build', 'verify')], output='/private/build/artifact')

    def handoff(self, i=1, **changes):
        when = '2026-01-01T00:00:00+00:00'
        item = dict(id=f'{i:032x}', order_id=order_id('demo', self.digest, 2, self.running[0]),
                    task_id='review', spec_sha256=self.digest, role='ui', attempt=1, board_revision=2,
                    created_at=when, outcome='completed', summary='Input checked', evidence=['Observed movement'],
                    changed_paths=['private/report.txt'], next_action='Review', review='accepted',
                    review_note='Checked', reviewed_at=when)
        return item | changes

    def live(self):
        audit = audit_project(self.project, self.jobs, self.board, self.registry, self.defects,
                              profile_jobs(self.project, self.jobs))
        return audit, assess_acceptance(self.project, audit, self.board, self.defects, self.history)

    def sources(self):
        return [self.project, self.audit, self.acceptance, self.board, self.registry, self.jobs, self.handoffs]

    def report(self):
        return build_dossier(*self.sources())

    def test_ready_without_handoffs_and_independently_recomputable_checksum(self):
        before = copy.deepcopy(self.sources())
        result = self.report()
        body = result['report']
        self.assertEqual(result['status'], 'ready', body)
        self.assertEqual(body['status'], result['status'])
        self.assertEqual(body['project_id'], result['project_id'])
        self.assertEqual(body['spec_sha256'], result['spec_sha256'])
        self.assertEqual((body['name'], body['kind']), ('Demo', 'multiplayer'))
        self.assertEqual(body['gates'], self.acceptance['gates'])
        self.assertEqual(body['release']['manifest_sha256'], self.release['manifest_sha256'])
        self.assertEqual(body['board']['tasks'][0]['evidence'], ['Reviewed input.'])
        self.assertEqual(body['handoffs']['covered_attempts'], 0)
        self.assertEqual(body['jobs'][0]['total_seconds'], 4)
        self.assertEqual(self.sources(), before)
        encoded = json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), result['report_sha256'])
        self.assertNotIn(b'/private/build', encoded)
        self.assertNotIn(b'generated_at', encoded)
        self.assertEqual(self.report(), result)
        body['name'] = 'Changed'
        self.assertNotEqual(spec_digest(body), result['report_sha256'])

    def test_order_and_out_of_scope_jobs_do_not_change_digest(self):
        self.jobs = [self.job(i) for i in range(1, 55)]
        self.audit, self.acceptance = self.live()
        original = self.report()
        self.assertEqual(original['status'], 'ready', original)
        self.assertEqual(len(original['report']['jobs']), 54)
        self.jobs.reverse()
        self.jobs.extend([dict(self.job(99), project_id='other'), dict(self.job(100), spec_sha256='f' * 64)])
        self.acceptance['gates'].reverse()
        self.audit['checks'].reverse()
        self.assertEqual(self.report(), original)
        self.jobs[0]['commands'][0]['duration_seconds'] = 2.1
        self.audit, self.acceptance = self.live()
        self.assertNotEqual(self.report()['report_sha256'], original['report_sha256'])

    def test_only_accepted_matching_completed_reports_cover_current_completed_attempt(self):
        accepted = self.handoff()
        rejected = self.handoff(2, review='rejected')
        progress = self.handoff(3, outcome='progress')
        past_spec = self.handoff(4, spec_sha256='e' * 64, order_id='e' * 64)
        other_attempt = self.handoff(5, attempt=2, order_id='a' * 64)
        pending = self.handoff(6, review='pending', review_note=None, reviewed_at=None)
        mismatched_order = self.handoff(7, order_id='d' * 64)
        self.handoffs.update(revision=13, items=[accepted, rejected, progress, past_spec, other_attempt,
                                                pending, mismatched_order])
        result = self.report()
        summary = result['report']['handoffs']
        self.assertEqual(result['status'], 'ready', result)
        self.assertEqual((summary['current_count'], summary['historical_count']), (6, 1))
        self.assertEqual((summary['completed_attempts'], summary['covered_attempts']), (1, 1))
        self.assertEqual(summary['coverage'][0]['handoff_ids'], [accepted['id']])
        self.assertNotIn('private/report.txt', json.dumps(result))
        self.handoffs['items'].reverse()  # All timestamps tie.
        self.assertEqual(self.report(), result)
        self.handoffs['items'].remove(accepted)
        self.handoffs['revision'] -= 2
        self.assertEqual(self.report()['report']['handoffs']['covered_attempts'], 0)

    def test_accepted_report_does_not_complete_board_release_or_build(self):
        self.handoffs.update(revision=2, items=[self.handoff()])
        self.board = self.board_at(2, self.running)
        self.jobs = []
        self.registry.update(revision=0, releases=[], active_release_id=None, active_state='empty')
        self.audit, self.acceptance = self.live()
        result = self.report()
        self.assertEqual(result['status'], 'pending', result)
        self.assertEqual(result['report']['handoffs']['completed_attempts'], 0)
        self.assertEqual(result['report']['release']['active_state'], 'empty')
        self.assertEqual(result['report']['jobs'], [])
        self.assertEqual(result['report']['board']['tasks'][0]['status'], 'running')

    def test_corrupt_scoped_sources_and_fabricated_gates_fail_closed(self):
        for index in (1, 2, 3, 4, 6):
            for key, value in (('project_id', 'other'), ('spec_sha256', 'b' * 64)):
                with self.subTest(index=index, field=key):
                    args = copy.deepcopy(self.sources())
                    args[index][key] = value
                    result = build_dossier(*args)
                    self.assertEqual(result['status'], 'blocked')
                    self.assertTrue(result['report']['source_errors'])
        for index in range(7):
            args = self.sources()
            args[index] = None
            self.assertEqual(build_dossier(*args)['status'], 'blocked')
        self.acceptance['gates'].append(self.acceptance['gates'][0])
        self.assertEqual(self.report()['status'], 'blocked')
        self.acceptance['gates'].pop()
        self.acceptance['gates'][0]['evidence'] = 'Different job.'
        self.assertIn('acceptance', self.report()['report']['source_errors'])

    def test_detects_disagreement_with_actual_build_board_and_release_evidence(self):
        self.jobs[-1]['status'] = 'failed'
        self.jobs[-1]['verified'] = False
        self.assertEqual(self.report()['status'], 'blocked')
        self.assertIn('audit', self.report()['report']['source_errors'])
        self.audit, self.acceptance = self.live()
        self.assertIn('release', self.report()['report']['source_errors'])
        self.jobs[-1] = self.job(3)
        self.audit, self.acceptance = self.live()
        self.release['manifest_sha256'] = 'e' * 64
        self.assertIn('release', self.report()['report']['source_errors'])
        self.release['manifest_sha256'] = 'c' * 64
        self.board['tasks'][0].update(gate='build', job_id='f' * 32)
        self.assertIn('board', self.report()['report']['source_errors'])

    def test_malformed_records_block_instead_of_looking_empty_or_verified(self):
        changes = [
            (3, lambda obj: obj['summary'].update(completed=False)),
            (4, lambda obj: obj['releases'][0].update(output='/tmp/leak')),
            (5, lambda obj: obj.append(copy.deepcopy(obj[0]))),
            (5, lambda obj: obj[0].update(project_id=None)),
            (5, lambda obj: obj[0].update(kind='assets')),
            (5, lambda obj: obj[0]['commands'][0].update(duration_seconds=float('nan'))),
            (5, lambda obj: obj[0]['commands'][1].update(exit_code=1)),
            (6, lambda obj: obj.update(revision=5)),
        ]
        for index, alter in changes:
            with self.subTest(index=index, change=alter):
                sources = copy.deepcopy(self.sources())
                alter(sources[index])
                result = build_dossier(*sources)
                self.assertEqual(result['status'], 'blocked')
                self.assertTrue(result['report']['source_errors'])


if __name__ == '__main__':
    unittest.main()
