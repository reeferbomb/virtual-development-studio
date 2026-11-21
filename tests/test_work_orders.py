import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from command_center.projects import ProjectStore
from command_center.provenance import spec_digest
from command_center.task_store import TaskStore
from command_center.work_orders import order_id, work_orders


ROOT = Path(__file__).resolve().parents[1]
ROSTER = (
    ('architecture', 'Count Blueprint', 'count_blueprint', 'gpt-6.2-astra', 'ultra'),
    ('gameplay', 'Major Mayhem', 'major_mayhem', 'gpt-6.2-astra', 'ultra'),
    ('verification', 'Doctor Doomcheck', 'doctor_doomcheck', 'gpt-6.2-astra', 'ultra'),
    ('ui', 'Madame Glitch', 'madame_glitch', 'gpt-6.2-astra', 'ultra'),
    ('content', 'Grimbrush', 'grimbrush', 'gpt-6.2-astra', 'ultra'),
    ('build_operations', 'Baron Buildgrave', 'baron_buildgrave', 'gpt-6.2-sol', 'max'),
)


def definition(task_id='audit', role='verification', gate='manual', depends_on=()):
    return dict(id=task_id, title='Review ' + task_id, role=role, gate=gate, priority=4,
                depends_on=list(depends_on))


class WorkOrdersTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.projects = ProjectStore(ROOT, Path(workspace.name))
        self.project = self.projects.create('Work order desk', 'city')
        self.pid = self.project['id']
        self.digest = spec_digest(self.project['spec'])
        self.store = TaskStore(self.projects)
        self.board = self.store.get(self.pid)

    def apply(self, op, **fields):
        self.board = self.store.apply(self.pid, dict(expected_revision=self.board['revision'],
                                      spec_sha256=self.board['spec_sha256'], action=dict(op=op, **fields)))

    def export(self):
        return work_orders(self.project, self.board)

    def test_only_claimed_tasks_export_and_export_writes_nothing(self):
        empty = self.export()
        self.assertEqual(empty, dict(project_id=self.pid, spec_sha256=self.digest, board_revision=0,
                                     state='empty', orders=[]))
        path = self.projects.directory(self.pid) / 'task-board.json'
        self.assertFalse(path.exists())
        self.apply('add_batch', tasks=[definition('prepare', 'architecture'), definition('audit'),
                                       definition('build', 'build_operations', 'build', ['prepare']),
                                       definition('blocked', 'ui'), definition('pending', 'content')])
        self.assertEqual(self.export()['orders'], [])
        self.apply('start', task_id='prepare')
        self.apply('complete', task_id='prepare', evidence=['Reviewed project layout'])
        self.apply('start', task_id='blocked')
        self.apply('block', task_id='blocked', reason='Waiting for artwork')
        self.apply('start', task_id='build')
        copies = deepcopy((self.project, self.board))
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        result = self.export()
        self.assertEqual(json.loads(json.dumps(result)), self.export())
        self.assertEqual(result['state'], 'current')
        self.assertEqual([o['task_id'] for o in result['orders']], ['build'])
        order = result['orders'][0]
        self.assertEqual(set(order), {'order_id', 'task_id', 'attempt', 'role', 'codename', 'title',
                                      'gate', 'depends_on', 'board_revision', 'spawn_args'})
        self.assertEqual(order['depends_on'], ['prepare'])
        self.assertEqual(order['gate'], 'build')
        self.assertEqual(order['board_revision'], self.board['revision'])
        self.assertEqual(order['attempt'], 1)
        self.assertIn('passed, verified build job', order['spawn_args']['message'])
        order['depends_on'].clear()
        self.assertEqual((self.project, self.board), copies)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_six_role_roster_and_report_contract(self):
        tasks = [definition(role.replace('_', '-'), role) for role, *_ in reversed(ROSTER)]
        self.apply('add_batch', tasks=tasks)
        for task in tasks:
            self.apply('start', task_id=task['id'])
        orders = self.export()['orders']
        self.assertEqual(len({order['order_id'] for order in orders}), 6)
        for (role, codename, task_name, model, effort), order in zip(ROSTER, orders, strict=True):
            self.assertEqual((order['role'], order['codename']), (role, codename))
            self.assertRegex(order['order_id'], r'^[0-9a-f]{64}$')
            args = order['spawn_args']
            self.assertEqual(set(args), {'task_name', 'model', 'reasoning_effort', 'fork_turns', 'message'})
            self.assertEqual((args['task_name'], args['model'], args['reasoning_effort'], args['fork_turns']),
                             (task_name, model, effort, 'none'))
            for text in (self.pid, self.digest, codename, order['title'], order['task_id'], order['order_id'],
                         f"board revision {self.board['revision']}", 'attempt 1', 'manual review', 'lead',
                         'completed', 'blocked', 'progress', 'summary', 'evidence', 'changed_paths',
                         'next_action', 'Do not write'):
                self.assertIn(text, args['message'])

    def test_revision_attempt_reassignment_and_completion(self):
        self.apply('add', task=definition())
        self.apply('start', task_id='audit')
        original = self.export()['orders'][0]
        self.apply('add', task=definition('lighting', 'content'))
        refreshed = self.export()['orders'][0]
        self.assertNotEqual(original['order_id'], refreshed['order_id'])
        self.assertEqual(original['attempt'], refreshed['attempt'])
        self.apply('requeue', task_id='audit')
        self.assertEqual(self.export()['orders'], [])
        self.apply('reassign', task_id='audit', role='build_operations')
        self.apply('start', task_id='audit')
        retry = self.export()['orders'][0]
        self.assertEqual((retry['role'], retry['attempt'], retry['spawn_args']['model']),
                         ('build_operations', 2, 'gpt-6.2-sol'))
        self.assertEqual(len({r['order_id'] for r in (original, refreshed, retry)}), 3)
        self.apply('complete', task_id='audit', evidence=['Reviewed saved artifacts'])
        self.assertEqual(self.export()['orders'], [])
        completed = self.board['tasks'][0]
        self.assertEqual(order_id(self.pid, self.digest, retry['board_revision'], completed), retry['order_id'])
        for field, value in (('gate', 'build'), ('role', 'ui'), ('depends_on', ['lighting']),
                             ('priority', 1), ('title', 'Other work'), ('id', 'other'), ('attempts', 1)):
            with self.subTest(field=field):
                self.assertNotEqual(order_id(self.pid, self.digest, retry['board_revision'],
                                             dict(completed, **{field: value})), retry['order_id'])
        for project_id, digest in (('other-project', self.digest), (self.pid, 'f' * 64)):
            self.assertNotEqual(order_id(project_id, digest, retry['board_revision'], completed), retry['order_id'])

    def test_stale_spec_projection_and_explicit_reset(self):
        self.apply('add', task=definition())
        self.apply('start', task_id='audit')
        old_order = self.export()['orders'][0]
        self.project = self.projects.save_spec(self.pid, dict(self.project['spec'], seed=self.project['spec']['seed'] + 1))
        self.assertEqual(self.export()['state'], 'unavailable')  # Mixed project and board snapshots.
        self.board = self.store.get(self.pid)
        stale = self.export()
        self.assertEqual((stale['state'], stale['board_revision'], stale['orders']), ('stale', 2, []))
        self.assertNotEqual(stale['spec_sha256'], self.digest)
        self.apply('reset')
        self.assertEqual((self.export()['state'], self.export()['orders']), ('current', []))
        self.apply('add', task=definition())
        self.apply('start', task_id='audit')
        self.assertNotEqual(self.export()['orders'][0]['order_id'], old_order['order_id'])

    def test_malformed_foreign_and_tampered_snapshots_fail_closed(self):
        self.apply('add', task=definition())
        self.apply('start', task_id='audit')
        foreign = self.projects.create('Foreign', 'city')  # Same default spec; different project.
        self.assertEqual(work_orders(foreign, self.board)['orders'], [])
        invalid_boards = [None, {}, [], dict(self.board, spec_sha256='A' * 64),
                          dict(self.board, board_spec_sha256='a' * 64), dict(self.board, revision=True),
                          dict(self.board, revision=0), dict(self.board, state='empty'),
                          dict(self.board, ready_task_ids=['audit']), dict(self.board, tasks=[]),
                          dict(self.board, summary=dict(self.board['summary'], running=True)),
                          dict(self.board, tasks=[dict(self.board['tasks'][0], attempts=0)]),
                          dict(self.board, tasks=self.board['tasks'] * 2)]
        for invalid in invalid_boards:
            with self.subTest(invalid=invalid):
                self.assertEqual(work_orders(self.project, invalid), dict(project_id=self.pid,
                                 spec_sha256=self.digest, board_revision=None, state='unavailable', orders=[]))
        for invalid in (None, {}, [], dict(self.project, id='../outside'), dict(self.project, spec=[]),
                        dict(self.project, spec={'seed': float('nan')})):
            with self.subTest(project=invalid):
                out = work_orders(invalid, self.board)
                self.assertEqual((out['state'], out['board_revision'], out['orders']), ('unavailable', None, []))
