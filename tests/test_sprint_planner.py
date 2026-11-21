import copy
import unittest

from command_center import scheduler
from command_center.provenance import spec_digest
from command_center.sprint_planner import plan_sprint
from command_center.supervisor import audit_project


class SprintPlannerTests(unittest.TestCase):
    def setUp(self):
        self.project = {'id': 'test-yard', 'spec': {'seed': 311}}
        self.identity = dict(project_id=self.project['id'], spec_sha256=spec_digest(self.project['spec']))
        self.board = dict(self.identity, board_spec_sha256=None, revision=0, state='empty', tasks=[])
        self.jobs = []
        self.releases = dict(self.identity, active_state='empty', active_release_id=None, releases=[])
        self.defects = dict(self.identity, items=[dict(id='abc', spec_sha256=self.identity['spec_sha256'],
                                                     severity='critical', status='open')])
        self.profile = dict(self.identity, regression=None, summary={})

    def audit(self):
        return audit_project(self.project, self.jobs, self.board, self.releases, self.defects, self.profile)

    def plan(self):
        return plan_sprint(self.project, self.audit(), self.board)

    def current_board(self, records):
        self.board.update(state='current', board_spec_sha256=self.identity['spec_sha256'],
                          revision=self.board['revision'] + 1, tasks=records)

    def test_advisory_plan_is_pure_and_deterministic(self):
        audit = self.audit()
        inputs = self.project, audit, self.board
        original = copy.deepcopy(inputs)
        plan = plan_sprint(*inputs)
        self.assertEqual(inputs, original)
        self.assertEqual(plan, plan_sprint(*copy.deepcopy(inputs)))
        audit['recommendations'].reverse()
        audit['checks'].reverse()
        self.assertEqual(plan, plan_sprint(*inputs))
        self.assertEqual(plan['status'], 'ready')
        content = {key: plan[key] for key in ('project_id', 'spec_sha256', 'board_revision', 'tasks', 'rationale')}
        self.assertEqual(plan['plan_id'], spec_digest(content))
        by_id = {entry['id']: entry for entry in plan['tasks']}
        records = []
        self.assertEqual(list(by_id), [row['task_id'] for row in plan['rationale']])
        for task, row in zip(plan['tasks'], plan['rationale']):
            records = scheduler.apply_action(records, {'op': 'add', 'task': task})
            source = next(r for r in audit['recommendations'] if
                          'supervisor-' + r['id'].replace('_', '-') == task['id'])
            self.assertEqual(row['detail'], source['detail'])
            self.assertEqual(row['evidence'], source['evidence'])
        self.assertEqual(by_id['supervisor-defects']['priority'], 5)
        self.assertEqual(by_id['supervisor-build']['gate'], 'build')
        self.assertEqual(by_id['supervisor-release']['gate'], 'manual')
        self.assertEqual(by_id['supervisor-build']['depends_on'], ['supervisor-defects'])
        self.assertEqual(by_id['supervisor-release']['depends_on'], ['supervisor-build'])
        self.assertTrue(all(task['status'] == 'pending' and not task['evidence'] for task in records))
        self.assertNotIn('supervisor-build', scheduler.schedule(records)['ready_task_ids'])

    def test_plan_id_tracks_evidence_and_board_revision(self):
        initial = self.plan()
        self.defects['items'][0]['id'] = 'different-defect'
        changed = self.plan()
        self.assertEqual(changed['tasks'], initial['tasks'])
        self.assertNotEqual(changed['plan_id'], initial['plan_id'])
        self.current_board([])
        self.assertNotEqual(changed['plan_id'], self.plan()['plan_id'])

    def test_all_passing_checks_propose_no_tasks(self):
        task = dict(id='review', title='Review the current build', role='verification', priority=3,
                    depends_on=[], gate='manual')
        records = scheduler.apply_action([], dict(op='add', task=task))
        records = scheduler.apply_action(records, dict(op='start', task_id='review'))
        records = scheduler.apply_action(records, dict(op='complete', task_id='review', evidence=['Inspected output.']))
        self.current_board(records)
        self.defects['items'] = []
        self.jobs = [dict(self.identity, id='a' * 32, status='passed', verified=True)]
        self.releases.update(active_state='current', active_release_id='candidate',
                             releases=[dict(self.identity, id='candidate')])
        self.profile.update(regression=False, summary=dict(latest_total_seconds=2, baseline_total_seconds=2))
        self.assertEqual(self.audit()['status'], 'pass')
        plan = self.plan()
        self.assertEqual((plan['status'], plan['tasks'], plan['rationale']), ('empty', [], []))

    def test_unavailable_foreign_stale_and_corrupt_boards_block(self):
        audit = self.audit()
        invalid = [None, {}, dict(self.board, project_id='other'), dict(self.board, state='stale'),
                   dict(self.board, revision=True), dict(self.board, revision=9),
                   dict(self.board, state='current'), dict(self.board, tasks=[{}]),
                   dict(self.board, spec_sha256='f' * 64)]
        for board in invalid:
            with self.subTest(board=board):
                plan = plan_sprint(self.project, audit, board)
                self.assertEqual(plan['status'], 'blocked')
                self.assertEqual((plan['tasks'], plan['rationale']), ([], []))
                self.assertRegex(plan['plan_id'], r'^[a-f0-9]{64}$')

    def test_unavailable_mismatched_and_malformed_audits_block(self):
        audit = self.audit()
        rec = audit['recommendations'][0]
        bad = [None, dict(audit, project_id='another'), dict(audit, spec_sha256='a' * 64),
               dict(audit, checks=[]), dict(audit, status='pending'), dict(audit, recommendations=None),
               dict(audit, recommendations=[])]
        for key, value in [('severity', []), ('role', 'guest'), ('id', []), ('detail', ' '),
                           ('title', 1), ('title', 'z' * 121), ('title', chr(0xd800)),
                           ('evidence', 'wrong type'), ('evidence', [])]:
            bad.append(dict(audit, recommendations=[dict(rec, **{key: value})]))
        for source in bad:
            with self.subTest(source=source):
                plan = plan_sprint(self.project, source, self.board)
                self.assertEqual(plan['status'], 'blocked')
                self.assertEqual(plan['tasks'], [])

    def test_duplicate_recommendations_and_existing_completed_task(self):
        audit = self.audit()
        rec = audit['recommendations'][0]
        duplicate = dict(audit, recommendations=[rec, *audit['recommendations']])
        self.assertEqual(plan_sprint(self.project, duplicate, self.board), self.plan())
        conflict = dict(audit, recommendations=[dict(rec, title='Different task'), *audit['recommendations']])
        self.assertEqual(plan_sprint(self.project, conflict, self.board)['status'], 'blocked')
        records = []
        for task in self.plan()['tasks']:
            records = scheduler.apply_action(records, dict(op='add', task=task))
        records = scheduler.apply_action(records, dict(op='start', task_id='supervisor-defects'))
        records = scheduler.apply_action(records, dict(op='complete', task_id='supervisor-defects',
                                                       evidence=['Reproduced the issue and filed a fix request.']))
        self.current_board(records)
        covered = self.plan()
        self.assertEqual(covered['status'], 'empty')
        self.assertEqual(covered['tasks'], [])
        self.assertIn('1 completed', covered['reason'])
        self.assertIn('follow-up', covered['reason'])

    def test_an_existing_build_can_gate_a_new_release_review(self):
        build = next(task for task in self.plan()['tasks'] if task['id'] == 'supervisor-build')
        records = scheduler.apply_action([], dict(op='add', task=dict(build, depends_on=[])))
        self.current_board(records)
        proposed = {task['id']: task for task in self.plan()['tasks']}
        self.assertNotIn('supervisor-build', proposed)
        self.assertEqual(proposed['supervisor-release']['depends_on'], ['supervisor-build', 'supervisor-defects'])
        for task in proposed.values():
            records = scheduler.apply_action(records, dict(op='add', task=task))

    def test_recovery_work_and_minor_defects_do_not_gate_builds(self):
        self.defects['items'][0]['severity'] = 'low'
        tasks = {task['id']: task for task in self.plan()['tasks']}
        self.assertEqual(tasks['supervisor-build']['depends_on'], [])
        self.defects = None
        self.jobs = None
        tasks = {task['id']: task for task in self.plan()['tasks']}
        self.assertEqual(tasks['supervisor-build']['gate'], 'manual')
        self.assertEqual(tasks['supervisor-release']['depends_on'], [])

    def test_near_full_boards_offer_only_valid_additions(self):
        base = dict(title='Existing task', role='ui', priority=2, depends_on=[], gate='manual')
        record = scheduler.apply_action([], dict(op='add', task=dict(base, id='sample')))[0]
        records = [dict(record, id=f'existing-{i}') for i in range(99)]
        self.current_board(records)
        partial = self.plan()
        self.assertEqual(partial['status'], 'ready')
        self.assertEqual([task['id'] for task in partial['tasks']], ['supervisor-defects'])
        self.assertIn('limit', partial['reason'])
        self.current_board(scheduler.apply_action(records, dict(op='add', task=partial['tasks'][0])))
        full = self.plan()
        self.assertEqual(full['status'], 'blocked')
        self.assertEqual(full['tasks'], [])
        self.assertIn('100', full['reason'])


if __name__ == '__main__':
    unittest.main()
