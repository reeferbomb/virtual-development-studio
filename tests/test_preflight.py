import copy
import unittest

from command_center.acceptance import assess_acceptance
from command_center.dossier import build_dossier
from command_center.forecast import forecast
from command_center.performance import profile_jobs
from command_center.preflight import preflight
from command_center.provenance import spec_digest
from command_center.scheduler import apply_action
from command_center.supervisor import audit_project
from command_center.task_store import _projection


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.project = dict(id='studio', name='Studio', kind='multiplayer', spec={})
        self.scope = dict(project_id='studio', spec_sha256=spec_digest({}))
        stamp = '2026-01-01T00:00:00+00:00'
        self.jobs = [dict(self.scope, id=f'{i:032x}', status='passed', verified=True, created_at=stamp, queue_sequence=i,
                          manifest_sha256='a' * 64, commands=[dict(stage=stage, duration_seconds=1)
                                                              for stage in ('build', 'verify')]) for i in range(1, 4)]
        job_id = self.jobs[-1]['id']
        release = dict(id='b' * 32, job_id=job_id, spec_sha256=self.scope['spec_sha256'], created_at=stamp,
                       manifest_sha256='a' * 64, output=f'jobs/{job_id}/output')
        self.registry = dict(self.scope, revision=1, releases=[release], active_release_id=release['id'],
                             active_state='current')
        self.empty = dict(self.scope, revision=0, items=[])
        definition = dict(id='review', title='Review controls', role='ui', priority=2, depends_on=[], gate='manual')
        self.pending = apply_action([], dict(op='add', task=definition))
        self.running = apply_action(self.pending, dict(op='start', task_id='review'))
        self.done = apply_action(self.running, dict(op='complete', task_id='review', evidence=['Controls reviewed.']))

    def sources(self, tasks, revision=3, *, captured=True):
        record = dict(self.scope, revision=revision, tasks=tasks) if revision else None
        board = _projection(self.scope['project_id'], self.scope['spec_sha256'], record)
        audit = audit_project(self.project, self.jobs, board, self.registry, self.empty,
                              profile_jobs(self.project, self.jobs))
        history = self.empty
        if captured:
            capture = dict(id='1' * 32, spec_sha256=self.scope['spec_sha256'], status=audit['status'],
                           checks=audit['checks'], note='Review', created_at='2026-01-01T00:00:00+00:00')
            history = dict(self.scope, revision=1, items=[capture])
        acceptance = assess_acceptance(self.project, audit, board, self.empty, history)
        dossier = build_dossier(self.project, audit, acceptance, board, self.registry, self.jobs, self.empty)
        return dossier, forecast(self.project, board)

    def test_real_ready_dossier_is_advisory_deterministic_and_read_only(self):
        dossier, schedule = self.sources(self.done)
        self.assertEqual(dossier['status'], 'ready')
        sources = [self.project, dossier, schedule]
        originals = copy.deepcopy(sources)
        result = preflight(*sources)
        self.assertEqual(result['status'], 'ready', result)
        self.assertTrue(all(row['status'] == 'pass' for row in result['checks']))
        self.assertEqual(result['report_sha256'], spec_digest(result['report']))
        for key in ('project_id', 'spec_sha256', 'status', 'checks'):
            self.assertEqual(result[key], result['report'][key])
        self.assertEqual(result['report']['dossier_sha256'], dossier['report_sha256'])
        self.assertEqual(result['report']['board_revision'], 3)
        self.assertIn('publication', result['report']['advisory'])
        self.assertEqual(preflight(*sources), result)
        self.assertEqual(originals, sources)

    def test_valid_pending_and_failed_evidence_have_distinct_results(self):
        blocked = apply_action(self.running, dict(op='block', task_id='review', reason='Needs repair'))
        for tasks, revision, captured, status in [(self.done, 3, False, 'pending'), ([], 0, False, 'pending'),
                                                (self.pending, 1, False, 'pending'),
                                                (self.running, 2, False, 'pending'), (blocked, 3, False, 'blocked')]:
            with self.subTest(status=status, revision=revision, tasks=tasks):
                result = preflight(self.project, *self.sources(tasks, revision, captured=captured))
                self.assertEqual(result['status'], status, result)

    def test_damaged_seal_wrong_identity_and_inconsistent_evidence_fail_closed(self):
        dossier, schedule = self.sources(self.done)
        for mutation, reseal in [
            (lambda d: d['report'].update(name='tampered'), False),
            (lambda d: d.update(report_sha256='f' * 64), False),
            (lambda d: d.update(project_id='elsewhere'), False),
            (lambda d: d['report'].update(spec_sha256='f' * 64), True),
            (lambda d: d['report'].update(kind='world'), True),
            (lambda d: d['report'].update(status='pending'), True),
            (lambda d: d['report'].update(source_errors={'board': 'Unreadable.'}), True),
            (lambda d: d['report'].update(acceptance_status='pending'), True),
            (lambda d: d['report'].update(audit_status='pending'), True),
            (lambda d: d['report'].update(gates=[]), True),
            (lambda d: d['report']['gates'][0].update(status='pending'), True),
            (lambda d: d['report']['release'].update(active_state='invalid'), True),
            (lambda d: d['report']['jobs'][-1].update(verified=False), True),
            (lambda d: d['report']['jobs'][0].update(job_id=None), True),
            (lambda d: d['report']['release'].update(revision=0), True),
            (lambda d: d['report']['board']['tasks'][0].update(gate='build', job_id='f' * 32), True),
            (lambda d: d['report']['board']['tasks'][0].update(attempt=0), True),
            (lambda d: d['report'].update(board=None), True),
            (lambda d: d['report']['board']['tasks'][0].update(status='unknown'), True),
            (lambda d: d['report']['board']['summary'].update(completed=True), True),
        ]:
            changed = copy.deepcopy(dossier)
            mutation(changed)
            if reseal:
                changed['report_sha256'] = spec_digest(changed['report'])
            with self.subTest(changed=changed):
                self.assertEqual(preflight(self.project, changed, schedule)['status'], 'blocked')

    def test_pending_gate_cannot_mask_a_contradictory_release_record(self):
        dossier, schedule = self.sources(self.done, captured=False)
        self.assertEqual(dossier['status'], 'pending')
        dossier['report']['release']['job_id'] = 'f' * 32
        dossier['report_sha256'] = spec_digest(dossier['report'])
        self.assertEqual(preflight(self.project, dossier, schedule)['status'], 'blocked')

    def test_forecast_must_match_actual_board_revision_and_remaining_task_identity(self):
        for tasks in (self.done, self.pending):
            dossier, schedule = self.sources(tasks)
            for patch in [dict(board_revision=9), dict(project_id='elsewhere'), dict(spec_sha256='f' * 64),
                          dict(status='unavailable'), dict(status='stale'), dict(remaining_tasks=True),
                          dict(unscheduled=['elsewhere']), dict(waves=[dict(wave=1, task_ids=['elsewhere'])])]:
                with self.subTest(tasks=tasks, patch=patch):
                    self.assertEqual(preflight(self.project, dossier, schedule | patch)['status'], 'blocked')
        dossier, _ = self.sources(self.pending)
        _, schedule = self.sources(self.done)
        self.assertEqual(preflight(self.project, dossier, schedule)['status'], 'blocked')

    def test_unknown_sources_are_blocked_and_report_remains_digestible(self):
        dossier, schedule = self.sources(self.done)
        for project, evidence, work in [(None, dossier, schedule), (self.project, None, schedule),
                                        (self.project, dossier, []), (self.project, {'status': 'ready'}, schedule),
                                        (self.project, dossier, self.scope | {'remaining_tasks': 0}),
                                        (self.project, dossier | {'report': {'value': float('nan')}}, schedule)]:
            result = preflight(project, evidence, work)
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(result['report_sha256'], spec_digest(result['report']))


if __name__ == '__main__':
    unittest.main()
