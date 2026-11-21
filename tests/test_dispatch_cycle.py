import copy
import json
import tempfile
import unittest
from pathlib import Path

from command_center.dispatch_cycle import dispatch_cycle
from command_center.portfolio import portfolio_plan
from command_center.projects import ProjectStore
from command_center.task_store import BOARD, TaskStore


ROOT = Path(__file__).resolve().parents[1]


class DispatchCycleTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.projects = ProjectStore(ROOT, Path(workspace.name))
        self.tasks = TaskStore(self.projects)

    def project(self, name):
        return self.projects.create(name, 'city')['id']

    def apply(self, project_id, action):
        board = self.tasks.get(project_id)
        return self.tasks.apply(project_id, dict(expected_revision=board['revision'],
                                                 spec_sha256=board['spec_sha256'], action=action))

    def add(self, project_id, task_id, role, priority=3):
        self.apply(project_id, dict(op='add', task=dict(id=task_id, title=task_id.title(), role=role,
                                                        priority=priority, depends_on=[], gate='manual')))

    def snapshot(self):
        return portfolio_plan(self.projects, self.tasks)

    def test_ready_steps_follow_portfolio_rank_and_export_exact_observed_claims(self):
        alpha, beta = self.project('Alpha'), self.project('Beta')
        self.add(alpha, 'design', 'architecture', 1)
        self.add(alpha, 'draw', 'content', 5)
        self.add(beta, 'review', 'verification', 3)
        snapshot = self.snapshot()
        before = copy.deepcopy(snapshot)
        report = dispatch_cycle(snapshot)
        self.assertEqual(set(report), {'status', 'cycle_id', 'steps', 'conflicts', 'note'})
        self.assertEqual(report['status'], 'ready')
        self.assertRegex(report['cycle_id'], r'^[0-9a-f]{64}$')
        self.assertEqual(report['conflicts'], [])
        self.assertTrue(report['note'])
        expected = []
        for pid, tid, role, priority in [(alpha, 'draw', 'content', 5), (beta, 'review', 'verification', 3),
                                         (alpha, 'design', 'architecture', 1)]:
            board = self.tasks.get(pid)
            expected.append(dict(project_id=pid, task_id=tid, title=tid.title(), role=role,
                                 priority=priority, expected_revision=board['revision'],
                                 spec_sha256=board['spec_sha256'], action=dict(op='start', task_id=tid)))
        self.assertEqual(report['steps'], expected)
        self.assertEqual(dispatch_cycle(self.snapshot()), report)
        report['steps'][0]['action']['op'] = 'block'
        self.assertEqual(snapshot, before)
        self.assertEqual(self.snapshot(), before)

    def test_idle_snapshot_binds_empty_projects_spec_and_membership(self):
        empty = dispatch_cycle(self.snapshot())
        self.assertEqual(empty['status'], 'idle')
        self.assertEqual((empty['steps'], empty['conflicts']), ([], []))
        self.assertRegex(empty['cycle_id'], r'^[0-9a-f]{64}$')
        pid = self.project('Fresh')
        fresh = dispatch_cycle(self.snapshot())
        self.assertEqual(fresh['status'], 'idle')
        self.assertNotEqual(fresh['cycle_id'], empty['cycle_id'])
        spec = self.projects.get(pid)['spec']
        self.projects.save_spec(pid, dict(spec, seed=spec['seed'] + 1))
        changed = dispatch_cycle(self.snapshot())
        self.assertNotEqual(changed['cycle_id'], fresh['cycle_id'])
        self.assertFalse((self.projects.directory(pid) / BOARD).exists())

    def test_unchanged_steps_bind_other_project_revisions_and_occupied_roles(self):
        alpha, beta = self.project('Alpha'), self.project('Beta')
        self.add(alpha, 'design', 'architecture', 5)
        self.add(beta, 'draw', 'ui')
        self.apply(beta, dict(op='start', task_id='draw'))
        original = dispatch_cycle(self.snapshot())
        self.add(beta, 'later', 'ui', 1)
        snapshot = self.snapshot()
        updated = dispatch_cycle(snapshot)
        self.assertEqual(updated['steps'], original['steps'])
        self.assertNotEqual(updated['cycle_id'], original['cycle_id'])
        snapshot['occupied_roles'] = ['content']
        snapshot['role_occupancy'] = {'content': [beta]}
        other_owner = dispatch_cycle(snapshot)
        self.assertEqual(other_owner['steps'], original['steps'])
        self.assertNotEqual(other_owner['cycle_id'], updated['cycle_id'])

    def test_conflicts_including_stale_claims_block_every_step(self):
        alpha, beta = self.project('Alpha'), self.project('Beta')
        for pid in [alpha, beta]:
            self.add(pid, 'build', 'build_operations')
            self.apply(pid, dict(op='start', task_id='build'))
        spec = self.projects.get(beta)['spec']
        self.projects.save_spec(beta, dict(spec, seed=spec['seed'] + 1))
        self.add(alpha, 'review', 'verification')
        snapshot = self.snapshot()
        self.assertEqual(snapshot['assignments'], [])
        report = dispatch_cycle(snapshot)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(report['steps'], [])
        self.assertRegex(report['cycle_id'], r'^[0-9a-f]{64}$')
        self.assertEqual(report['conflicts'], [dict(role='build_operations', project_ids=[alpha, beta])])
        report['conflicts'][0]['project_ids'].clear()
        self.assertEqual(snapshot, self.snapshot())

    def test_unreadable_or_inconsistent_portfolios_withhold_cycle_and_steps(self):
        pid = self.project('Alpha')
        self.add(pid, 'design', 'architecture')
        snapshot = self.snapshot()
        (self.projects.directory(pid) / BOARD).write_bytes(b'{')
        for broken in [None, {}, [], self.snapshot(), dict(snapshot, projects=[]),
                       dict(snapshot, assignments=[dict(snapshot['assignments'][0], board_revision=True)]),
                       dict(snapshot, occupied_roles=['architecture']),
                       dict(snapshot, conflicts=[dict(role='ui', project_ids=[pid])])]:
            with self.subTest(broken=broken):
                report = dispatch_cycle(broken)
                self.assertEqual(report['status'], 'unavailable')
                self.assertIsNone(report['cycle_id'])
                self.assertEqual((report['steps'], report['conflicts']), ([], []))
                self.assertTrue(report['note'])

    def test_serialized_portfolio_must_agree_with_its_exact_dispatch_export(self):
        pid = self.project('Alpha')
        self.add(pid, 'design', 'architecture', 3)
        self.add(pid, 'test', 'verification', 1)
        serialized = json.dumps(self.snapshot())
        self.assertEqual(dispatch_cycle(json.loads(serialized))['status'], 'ready')
        for damage in ['top task', 'both tasks', 'missing export', 'nested priority', 'missing work order']:
            with self.subTest(damage=damage):
                snapshot = json.loads(serialized)
                export = snapshot['dispatch_plan']
                if damage in ('top task', 'both tasks'):
                    snapshot['assignments'][0]['task_id'] = 'absent'
                    if damage == 'both tasks':
                        export['assignments'][0]['task_id'] = 'absent'
                elif damage == 'missing export':
                    del snapshot['dispatch_plan']
                elif damage == 'nested priority':
                    export['assignments'][1]['priority'] = True
                else:
                    export['spawn_args'].pop()
                report = dispatch_cycle(snapshot)
                self.assertEqual(report['status'], 'unavailable')
                self.assertIsNone(report['cycle_id'])
                self.assertEqual((report['steps'], report['conflicts']), ([], []))


if __name__ == '__main__':
    unittest.main()
