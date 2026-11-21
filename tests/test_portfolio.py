import fcntl
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from command_center import portfolio
from command_center.dispatch import default_profile
from command_center.portfolio import portfolio_plan
from command_center.projects import ProjectStore
from command_center.task_store import BOARD, TaskStore


ROOT = Path(__file__).resolve().parents[1]


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.projects = ProjectStore(ROOT, Path(temporary.name))
        self.tasks = TaskStore(self.projects)

    def plan(self):
        return portfolio_plan(self.projects, self.tasks)

    def create(self, name):
        return self.projects.create(name, 'city')['id']

    def apply(self, project_id, action):
        board = self.tasks.get(project_id)
        return self.tasks.apply(project_id, {'expected_revision': board['revision'],
                                             'spec_sha256': board['spec_sha256'], 'action': action})

    def add(self, project, task_id, role, priority=3, depends_on=()):
        return self.apply(project, {'op': 'add', 'task': {'id': task_id, 'title': task_id.title(),
                                                          'role': role, 'priority': priority,
                                                          'depends_on': list(depends_on), 'gate': 'manual'}})

    def test_empty_workspace_and_unsaved_board(self):
        plan = self.plan()
        self.assertEqual(plan, {'projects': [], 'occupied_roles': [], 'role_occupancy': {}, 'conflicts': [], 'assignments': [],
                                'dispatch_plan': {'execution_mode': 'export_only',
                                                  'host_tool': 'collaboration.spawn_agent',
                                                  'profile': default_profile(), 'assignments': [], 'spawn_args': []},
                                'summary': dict(projects=0, current=0, stale=0, empty=0, unavailable=0,
                                                ready=0, running=0)})
        project_id = self.create('New Project')
        board = self.tasks.get(project_id)
        plan = self.plan()
        self.assertEqual(plan['projects'], [{'project_id': project_id, 'name': 'New Project',
                                             'state': 'empty', 'revision': 0, 'spec_sha256': board['spec_sha256'],
                                             'summary': board['summary']}])
        self.assertEqual(plan['summary']['empty'], 1)
        self.assertEqual(plan['assignments'], [])
        self.assertEqual(plan['dispatch_plan']['spawn_args'], [])
        self.assertFalse((self.projects.directory(project_id) / BOARD).exists())

    def test_role_transfer_cannot_mix_two_board_generations(self):
        alpha, beta = [self.create(name) for name in ('Alpha', 'Beta')]
        for pid in (alpha, beta):
            self.add(pid, 'draw', 'ui')
        self.apply(alpha, dict(op='start', task_id='draw'))

        def transfer():
            self.apply(alpha, dict(op='requeue', task_id='draw'))
            self.apply(beta, dict(op='start', task_id='draw'))

        def writer_can_enter(path):
            directory = os.open(path, os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except BlockingIOError:
                return False
            finally:
                os.close(directory)

        original = portfolio._locked_directory
        checked = []

        @contextmanager
        def interleave(path, mode):
            if path == self.projects.directory(beta):
                checked.append((writer_can_enter(self.projects.projects),
                                writer_can_enter(self.projects.directory(alpha))))
                if checked[-1][1]:
                    transfer()
            with original(path, mode) as directory:
                yield directory

        with patch.object(portfolio, '_locked_directory', interleave):
            snapshot = self.plan()
        self.assertEqual(snapshot['role_occupancy'], {'ui': [alpha]})
        self.assertEqual(snapshot['conflicts'], [])
        self.assertEqual(checked, [(False, False)])
        transfer()
        self.assertEqual(self.plan()['role_occupancy'], {'ui': [beta]})

    def test_global_priority_tiebreaks_dependencies_and_snapshot_identity(self):
        zulu = self.create('Zulu')
        alpha = self.create('Alpha')
        self.add(zulu, 'aaa', 'ui', 4)
        self.add(zulu, 'race', 'gameplay', 5)
        self.add(zulu, 'locked', 'content', 5, depends_on=['race'])
        self.add(zulu, 'package', 'build_operations', 2)
        self.add(alpha, 'zeta', 'ui', 4)
        self.add(alpha, 'beta', 'ui', 4)
        self.add(alpha, 'walk', 'gameplay', 1)
        before = {pid: (self.projects.directory(pid) / BOARD).read_bytes() for pid in (zulu, alpha)}
        plan = self.plan()
        self.assertEqual(plan, self.plan())
        self.assertEqual([row['project_id'] for row in plan['projects']], [alpha, zulu])
        self.assertEqual(plan['summary'], dict(projects=2, current=2, stale=0, empty=0, unavailable=0,
                                               running=0, ready=6))
        expected = [(zulu, 'race', 'gameplay', 5), (alpha, 'beta', 'ui', 4),
                    (zulu, 'package', 'build_operations', 2)]
        self.assertEqual([(a['project_id'], a['task_id'], a['role'], a['priority'])
                          for a in plan['assignments']], expected)
        for assignment in plan['assignments']:
            board = self.tasks.get(assignment['project_id'])
            self.assertEqual(assignment['board_revision'], board['revision'])
            self.assertEqual(assignment['spec_sha256'], board['spec_sha256'])
            self.assertEqual(assignment['title'], assignment['task_id'].title())
        self.assertEqual([(a['model_id'], a['reasoning_effort']) for a in plan['assignments']],
                         [('gpt-6.2-astra', 'ultra'), ('gpt-6.2-astra', 'ultra'), ('gpt-6.2-sol', 'max')])
        for pid, original in before.items():
            self.assertEqual((self.projects.directory(pid) / BOARD).read_bytes(), original)

    def test_equal_priority_critical_work_wins_across_projects_and_within_role(self):
        alpha, zulu = [self.create(name) for name in ('Alpha', 'Zulu')]
        self.add(alpha, 'aaa', 'architecture', 4)
        self.add(zulu, 'aaa', 'architecture', 4)
        self.add(zulu, 'critical', 'architecture', 4)
        self.add(zulu, 'followup', 'gameplay', 3, depends_on=['critical'])
        self.add(zulu, 'check', 'verification', 3, depends_on=['followup'])
        plan = self.plan()
        self.assertEqual([(a['project_id'], a['task_id']) for a in plan['assignments']], [(zulu, 'critical')])
        self.apply(zulu, {'op': 'start', 'task_id': 'critical'})
        plan = self.plan()
        self.assertEqual(plan['role_occupancy'], {'architecture': [zulu]})
        self.assertEqual(plan['assignments'], [])

    def test_dispatch_arguments_match_eligible_tasks_and_contain_the_host_handoff(self):
        project_id = self.create('Joint Build')
        self.add(project_id, 'build-release', 'build_operations')
        self.add(project_id, 'verify-release', 'verification')
        plan = self.plan()
        export = plan['dispatch_plan']
        self.assertEqual(set(export), {'execution_mode', 'host_tool', 'profile', 'assignments', 'spawn_args'})
        self.assertEqual(export['execution_mode'], 'export_only')
        self.assertEqual(export['host_tool'], 'collaboration.spawn_agent')
        self.assertEqual(export['profile'], default_profile())
        self.assertEqual(export['assignments'], plan['assignments'])
        self.assertEqual(len(export['spawn_args']), 2)
        roles = {r['id']: r for r in export['profile']['roles']}
        for task, args in zip(export['assignments'], export['spawn_args'], strict=True):
            self.assertEqual(set(args), {'task_name', 'fork_turns', 'model', 'reasoning_effort', 'message'})
            self.assertEqual((args['task_name'], args['fork_turns'], args['model'], args['reasoning_effort']),
                             (roles[task['role']]['agent_task_name'], 'none', task['model_id'], task['reasoning_effort']))
            self.assertIn(roles[task['role']]['codename'], args['message'])
            self.assertIn('curriculum', args['message'].lower())
            for field in (project_id, task['task_id'], task['title'], task['spec_sha256'],
                          f"board revision {task['board_revision']}", '/api/portfolio',
                          f'/api/projects/{project_id}/tasks', 'claim the exact task',
                          export['profile']['continuity']['host_instruction']):
                self.assertIn(field, args['message'])
        self.assertEqual(self.tasks.get(project_id)['summary']['running'], 0)

    def test_running_roles_conflicts_stale_records_and_release(self):
        alpha, beta, charlie = [self.create(name) for name in ('Alpha', 'Beta', 'Charlie')]
        for pid in (alpha, beta):
            self.add(pid, 'design', 'architecture')
            self.apply(pid, {'op': 'start', 'task_id': 'design'})
        self.add(alpha, 'move', 'gameplay')
        self.apply(alpha, {'op': 'start', 'task_id': 'move'})
        self.add(alpha, 'draw', 'ui', 5)
        spec = self.projects.get(alpha)['spec']
        self.projects.save_spec(alpha, dict(spec, seed=spec['seed'] + 1))
        self.add(charlie, 'plan', 'architecture', 5)
        self.add(charlie, 'run', 'gameplay', 5)
        self.add(charlie, 'compose', 'content')
        plan = self.plan()
        self.assertEqual(plan['projects'][0]['state'], 'stale')
        self.assertEqual(plan['summary'], dict(projects=3, current=2, stale=1, empty=0, unavailable=0,
                                               running=3, ready=3))
        self.assertEqual(plan['occupied_roles'], ['architecture', 'gameplay'])
        self.assertEqual(plan['role_occupancy'], {'architecture': [alpha, beta], 'gameplay': [alpha]})
        self.assertEqual(plan['conflicts'], [{'role': 'architecture', 'project_ids': [alpha, beta]}])
        self.assertEqual(plan['assignments'], [])
        self.assertEqual(plan['dispatch_plan']['assignments'], plan['assignments'])
        self.assertEqual(plan['dispatch_plan']['spawn_args'], [])
        self.apply(beta, {'op': 'block', 'task_id': 'design', 'reason': 'Waiting for a decision'})
        self.assertEqual(self.plan()['conflicts'], [])
        self.assertEqual(self.plan()['occupied_roles'], ['architecture', 'gameplay'])
        self.apply(alpha, {'op': 'reset'})
        plan = self.plan()
        self.assertEqual(plan['occupied_roles'], [])
        self.assertEqual([a['task_id'] for a in plan['assignments']], ['plan', 'run', 'compose'])

    def test_unreadable_boards_and_metadata_suppress_all_assignments_until_repaired(self):
        alpha, beta, charlie = [self.create(name) for name in ('Alpha', 'Beta', 'Charlie')]
        self.add(alpha, 'review', 'verification')
        self.add(beta, 'move', 'gameplay')
        broken_board = self.projects.directory(beta) / BOARD
        broken_metadata = self.projects.directory(charlie) / 'project.json'
        originals = {path: path.read_bytes() for path in (broken_board, broken_metadata)}
        for path in originals:
            path.write_bytes(b'{invalid')
        plan = self.plan()
        self.assertEqual(plan['summary'], dict(projects=3, current=1, stale=0, empty=0, unavailable=2,
                                               running=0, ready=1))
        self.assertEqual(plan['assignments'], [])
        self.assertEqual(plan['dispatch_plan']['assignments'], [])
        self.assertEqual(plan['dispatch_plan']['spawn_args'], [])
        for row in plan['projects'][1:]:
            self.assertEqual(row['state'], 'unavailable')
            self.assertIsNone(row['revision'])
            self.assertIsNone(row['spec_sha256'])
            self.assertIsNone(row['summary'])
            self.assertTrue(row['error'])
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), b'{invalid')
            path.write_bytes(original)
        self.assertEqual([a['task_id'] for a in self.plan()['assignments']], ['review', 'move'])


if __name__ == '__main__':
    unittest.main()
