import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from command_center.blueprints import blueprint
from command_center.projects import ProjectStore, TEMPLATES
from command_center.provenance import spec_digest
from command_center.task_store import TaskStore


ROOT = Path(__file__).resolve().parents[1]


class BlueprintTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.projects = ProjectStore(ROOT, Path(workspace.name))
        self.project = self.projects.create('Starter', 'city')
        self.store = TaskStore(self.projects)
        self.board = self.store.get(self.project['id'])

    def apply(self, op, **fields):
        self.board = self.store.apply(self.project['id'], dict(
            expected_revision=self.board['revision'], spec_sha256=self.board['spec_sha256'],
            action=dict(op=op, **fields)))

    def preview(self):
        return blueprint(self.project, self.board)

    def test_every_kind_has_a_distinct_verified_milestone_and_six_schedulable_roles(self):
        identifiers, milestones, briefs = set(), set(), set()
        for kind in TEMPLATES:
            with self.subTest(kind=kind):
                project = self.projects.create(kind, kind)
                board = self.store.get(kind)
                plan = blueprint(project, board)
                self.assertEqual(set(plan), {'project_id', 'spec_sha256', 'board_revision', 'template_id',
                                             'title', 'tasks', 'status', 'reason', 'plan_id'})
                self.assertEqual((plan['status'], plan['project_id'], plan['spec_sha256'], plan['board_revision']),
                                 ('ready', kind, spec_digest(project['spec']), 0))
                self.assertRegex(plan['plan_id'], r'^[0-9a-f]{64}$')
                self.assertTrue(plan['reason'].strip())
                self.assertTrue(plan['title'].strip())
                self.assertTrue(plan['template_id'].strip())
                self.assertEqual(len(plan['tasks']), 6)
                roles = {task['role']: task for task in plan['tasks']}
                self.assertEqual(set(roles), {'architecture', 'gameplay', 'content', 'ui',
                                              'build_operations', 'verification'})
                for role in ('gameplay', 'content', 'ui'):
                    self.assertEqual(roles[role]['depends_on'], [roles['architecture']['id']])
                build = roles['build_operations']
                self.assertEqual(set(build['depends_on']), {roles[role]['id'] for role in ('gameplay', 'content', 'ui')})
                self.assertEqual(build['gate'], 'build')
                self.assertEqual(roles['verification']['depends_on'], [build['id']])
                current = self.store.apply(kind, dict(expected_revision=0, spec_sha256=plan['spec_sha256'],
                                           action=dict(op='add_batch', tasks=plan['tasks'])))
                self.assertEqual(current['ready_task_ids'], [roles['architecture']['id']])
                self.assertEqual(current['summary']['running'], 0)
                identifiers.add(plan['template_id'])
                milestones.add(plan['title'])
                briefs.add(tuple(task['title'] for task in plan['tasks']))
        self.assertEqual((len(identifiers), len(milestones), len(briefs)), (len(TEMPLATES),) * 3)

    def test_preview_is_pure_and_its_identity_binds_the_reviewed_content(self):
        plan = self.preview()
        before = deepcopy((self.project, self.board))
        self.assertEqual(plan, blueprint(*deepcopy(before)))
        self.assertEqual(spec_digest({k: plan[k] for k in ('project_id', 'spec_sha256', 'board_revision',
                                                            'template_id', 'title', 'tasks')}), plan['plan_id'])
        self.assertFalse((self.projects.directory(self.project['id']) / 'task-board.json').exists())
        plan['tasks'][-1]['depends_on'].clear()
        self.assertEqual((self.project, self.board), before)
        self.assertTrue(self.preview()['tasks'][-1]['depends_on'])

        original_id = self.preview()['plan_id']
        other = self.projects.create('Other', 'city')
        self.assertNotEqual(blueprint(other, self.store.get(other['id']))['plan_id'], original_id)
        self.project = self.projects.save_spec('starter', dict(self.project['spec'], seed=123))
        self.board = self.store.get('starter')
        self.assertNotEqual(self.preview()['plan_id'], original_id)
        self.assertEqual(self.preview()['tasks'], blueprint(*before)['tasks'])

    def test_existing_work_blocks_partial_conflicting_or_unrelated_blueprints(self):
        plan = self.preview()
        self.apply('add', task=plan['tasks'][0])
        for task in plan['tasks'][1:]:
            with self.subTest(about_to_add=task['id']):
                self.assert_blocked(self.preview())
                self.apply('add', task=task)
        role = plan['tasks'][0]['role']
        self.apply('reassign', task_id=plan['tasks'][0]['id'], role='ui' if role != 'ui' else 'content')
        self.assert_blocked(self.preview())
        other = self.projects.create('Custom', 'city')
        board = self.store.apply(other['id'], dict(expected_revision=0, spec_sha256=plan['spec_sha256'],
                                 action=dict(op='add', task=dict(plan['tasks'][0], id='unrelated'))))
        self.assert_blocked(blueprint(other, board))

    def test_full_matching_definitions_survive_lifecycle_and_subsequent_additions(self):
        plan = self.preview()
        self.apply('add_batch', tasks=list(reversed(plan['tasks'])))
        root = next(task for task in plan['tasks'] if not task['depends_on'])
        self.apply('start', task_id=root['id'])
        self.apply('complete', task_id=root['id'], evidence=['Recorded component boundaries'])
        self.apply('add', task=dict(root, id='custom-followup', title='Inspect newly reported issue'))
        self.assertEqual(self.preview()['status'], 'applied')
        self.assertEqual(self.preview()['tasks'], plan['tasks'])
        self.assertIsNone(self.preview()['plan_id'])

    def test_only_an_explicitly_reset_current_board_can_start_again(self):
        original = self.preview()
        self.apply('add_batch', tasks=original['tasks'])
        self.project = self.projects.save_spec('starter', dict(self.project['spec'], seed=123))
        self.board = self.store.get('starter')
        self.assert_blocked(self.preview())
        self.apply('reset')
        reset = self.preview()
        self.assertEqual((reset['status'], reset['board_revision']), ('ready', 2))
        fresh_board = self.store.get(self.projects.create('Fresh', 'city')['id'])
        fresh_board.update(project_id='starter', spec_sha256=reset['spec_sha256'])
        self.assertNotEqual(reset['plan_id'], blueprint(self.project, fresh_board)['plan_id'])

    def assert_blocked(self, plan):
        self.assertEqual((plan['status'], plan['tasks'], plan['plan_id']), ('blocked', [], None))
        self.assertTrue(plan['reason'].strip())

    def test_foreign_missing_stale_and_corrupt_snapshots_fail_closed(self):
        for board in [None, {}, dict(self.board, project_id='foreign'), dict(self.board, spec_sha256='e' * 64),
                      dict(self.board, revision=True), dict(self.board, ready_task_ids=['phantom']),
                      dict(self.board, state='current'), dict(self.board, tasks=[{}]),
                      dict(self.board, summary=dict(self.board['summary'], running=False))]:
            with self.subTest(board=board):
                self.assert_blocked(blueprint(self.project, board))
        for project in [None, '', {}, dict(self.project, id='bad/id'), dict(self.project, kind='unrecognized'),
                        dict(self.project, kind=[]), dict(self.project, spec=None),
                        dict(self.project, spec={'invalid': float('nan')})]:
            with self.subTest(project=project):
                self.assert_blocked(blueprint(project, self.board))
