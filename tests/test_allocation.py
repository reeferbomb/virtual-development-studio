import copy
import tempfile
import unittest
from pathlib import Path

from command_center.allocation import allocation
from command_center.dispatch import default_profile
from command_center.portfolio import portfolio_plan
from command_center.projects import ProjectStore
from command_center.task_store import BOARD, TaskStore


ROOT = Path(__file__).resolve().parents[1]
ROLES = [role['id'] for role in default_profile()['roles']]


class AllocationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.projects = ProjectStore(ROOT, Path(temporary.name))
        self.tasks = TaskStore(self.projects)

    def create(self, name):
        return self.projects.create(name, 'city')['id']

    def operate(self, project_id, action):
        board = self.tasks.get(project_id)
        return self.tasks.apply(project_id, dict(expected_revision=board['revision'],
                                                 spec_sha256=board['spec_sha256'], action=action))

    def add(self, project_id, task_id, role, priority=3):
        self.operate(project_id, dict(op='add', task=dict(id=task_id, title=task_id.title(),
                     role=role, priority=priority, depends_on=[], gate='manual')))

    def snapshot(self):
        return portfolio_plan(self.projects, self.tasks)

    def assert_unavailable(self, snapshot):
        report = allocation(snapshot)
        self.assertEqual(report['status'], 'unavailable')
        self.assertEqual(report['roles'], [])
        self.assertEqual(report['summary'], dict(capacity=len(ROLES), assigned=0, occupied=0,
                                                  conflicts=0, idle=0))
        self.assertTrue(report['note'])

    def test_empty_workspace_and_unsaved_board_have_six_idle_roles(self):
        empty_workspace = self.snapshot()
        project_id = self.create('New project')
        for snapshot in (empty_workspace, self.snapshot()):
            report = allocation(snapshot)
            self.assertEqual(report['status'], 'empty')
            self.assertEqual(report['summary'], dict(capacity=6, assigned=0, occupied=0, conflicts=0, idle=6))
            self.assertEqual(report['roles'], [dict(role=role, state='idle', project_ids=[], assignment=None)
                                               for role in ROLES])
        self.assertFalse((self.projects.directory(project_id) / BOARD).exists())

    def test_exact_owners_conflicts_and_recommendations_preserve_boards_and_snapshot(self):
        alpha, beta = self.create('Alpha'), self.create('Beta')
        for project_id in (beta, alpha):
            self.add(project_id, 'design', 'architecture')
            self.operate(project_id, dict(op='start', task_id='design'))
        self.add(alpha, 'editor', 'ui')
        self.operate(alpha, dict(op='start', task_id='editor'))
        spec = self.projects.get(alpha)['spec']
        self.projects.save_spec(alpha, dict(spec, seed=spec['seed'] + 1))
        self.add(beta, 'verify', 'verification')
        self.add(beta, 'screen', 'ui')
        boards = [self.projects.directory(pid) / BOARD for pid in (alpha, beta)]
        originals = [path.read_bytes() for path in boards]
        snapshot = self.snapshot()
        before = copy.deepcopy(snapshot)
        report = allocation(snapshot)
        self.assertEqual(report['status'], 'current')
        self.assertEqual(report['summary'], dict(capacity=6, assigned=1, occupied=1, conflicts=1, idle=3))
        self.assertEqual([r['role'] for r in report['roles']], ROLES)
        rows = {r['role']: r for r in report['roles']}
        self.assertEqual(rows['architecture'], dict(role='architecture', state='conflict',
                                                    project_ids=[alpha, beta], assignment=None))
        self.assertEqual(rows['ui'], dict(role='ui', state='occupied', project_ids=[alpha], assignment=None))
        self.assertEqual(rows['verification'], dict(role='verification', state='assigned', project_ids=[beta],
                                                    assignment=snapshot['assignments'][0]))
        self.assertEqual(rows['content']['state'], 'idle')
        self.assertEqual(allocation(snapshot), report)
        rows['verification']['assignment']['title'] = 'Edited locally'
        self.assertEqual(snapshot, before)
        self.assertEqual([path.read_bytes() for path in boards], originals)

    def test_ranked_choice_is_the_portfolio_recommendation(self):
        alpha, beta = self.create('Alpha'), self.create('Beta')
        self.add(alpha, 'low', 'content', 1)
        self.add(beta, 'high', 'content', 5)
        snapshot = self.snapshot()
        chosen = next(r for r in allocation(snapshot)['roles'] if r['role'] == 'content')
        self.assertEqual(chosen['project_ids'], [beta])
        self.assertEqual(chosen['assignment'], snapshot['assignments'][0])

    def test_unreadable_project_suppresses_the_workspace_forecast(self):
        healthy, broken = self.create('Healthy'), self.create('Broken')
        self.add(healthy, 'test', 'verification')
        (self.projects.directory(broken) / BOARD).write_bytes(b'{')
        self.assert_unavailable(self.snapshot())

    def test_invalid_scope_revision_role_identity_or_counts_suppress_every_assignment(self):
        project_id = self.create('Project')
        self.add(project_id, 'draw', 'ui')
        snapshot = self.snapshot()
        for field, value in (('project_id', 'other'), ('board_revision', 2), ('board_revision', True),
                             ('spec_sha256', '1' * 64), ('priority', False), ('role', []),
                             ('task_id', ''), ('title', ' '), ('model_id', 'another-model')):
            with self.subTest(field=field, value=value):
                damaged = copy.deepcopy(snapshot)
                damaged['assignments'][0][field] = value
                self.assert_unavailable(damaged)
        for key in ('assignments', 'projects'):
            damaged = copy.deepcopy(snapshot)
            damaged[key] *= 2
            self.assert_unavailable(damaged)
        for key in ('summary', 'occupied_roles', 'conflicts', 'role_occupancy'):
            damaged = copy.deepcopy(snapshot)
            del damaged[key]
            self.assert_unavailable(damaged)
        for key, value in (('running', True), ('ready', 0), ('projects', 2)):
            damaged = copy.deepcopy(snapshot)
            damaged['summary'][key] = value
            self.assert_unavailable(damaged)
        for damaged in (None, [], {}, dict(snapshot, assignments=None), dict(snapshot, assignments=[])):
            self.assert_unavailable(damaged)

    def test_owner_counts_must_match_each_project_even_when_totals_match(self):
        alpha, beta = self.create('Alpha'), self.create('Beta')
        self.add(alpha, 'draw', 'ui')
        self.operate(alpha, dict(op='start', task_id='draw'))
        snapshot = self.snapshot()
        snapshot['role_occupancy']['ui'] = [beta]
        self.assert_unavailable(snapshot)

    def test_inconsistent_owners_conflicts_or_double_booking_suppress_forecast(self):
        alpha, beta = self.create('Alpha'), self.create('Beta')
        for pid in (alpha, beta):
            self.add(pid, 'draw', 'ui')
            self.operate(pid, dict(op='start', task_id='draw'))
        self.add(alpha, 'play', 'gameplay')
        snapshot = self.snapshot()
        for field, value in (
                ('role_occupancy', {'ui': [alpha]}), ('role_occupancy', {'ui': [alpha, alpha]}),
                ('role_occupancy', {'ui': [alpha, 'outsider']}), ('role_occupancy', []),
                ('occupied_roles', []), ('conflicts', []),
                ('conflicts', [dict(role='ui', project_ids=[alpha])])):
            with self.subTest(field=field, value=value):
                self.assert_unavailable(dict(snapshot, **{field: value}))
        damaged = copy.deepcopy(snapshot)
        damaged['assignments'][0]['role'] = 'ui'
        self.assert_unavailable(damaged)


if __name__ == '__main__':
    unittest.main()
