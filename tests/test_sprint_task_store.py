import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from command_center.projects import ProjectStore
from command_center.provenance import spec_digest
from command_center.task_store import TaskStore


ROOT = Path(__file__).resolve().parents[1]


def definition(task_id, *dependencies):
    return {'id': task_id, 'title': task_id, 'role': 'gameplay', 'priority': 3,
            'depends_on': list(dependencies), 'gate': 'manual'}


class SprintTaskStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.projects = ProjectStore(ROOT, Path(temporary.name))
        self.project = self.projects.create('Sprint Test', 'city')
        self.pid = self.project['id']
        self.digest = spec_digest(self.project['spec'])
        self.path = self.projects.directory(self.pid) / 'task-board.json'
        self.store = TaskStore(self.projects)

    def apply(self, action, revision, digest=None):
        return self.store.apply(self.pid, {'expected_revision': revision,
                                           'spec_sha256': self.digest if digest is None else digest,
                                           'action': action})

    def batch(self, tasks, revision, digest=None):
        return self.apply({'op': 'add_batch', 'tasks': tasks}, revision, digest)

    def test_forward_references_and_existing_history_survive_single_revision(self):
        self.apply({'op': 'add', 'task': definition('foundation')}, 0)
        self.apply({'op': 'start', 'task_id': 'foundation'}, 1)
        prior = self.apply({'op': 'complete', 'task_id': 'foundation', 'evidence': ['Reviewed']}, 2)
        tasks = [definition('verify', 'feature', 'foundation'), definition('feature', 'foundation')]
        board = self.batch(tasks, 3)
        self.assertEqual(board['revision'], 4)
        self.assertEqual(board['tasks'][:1], prior['tasks'])
        self.assertEqual([task['id'] for task in board['tasks'][1:]], ['verify', 'feature'])
        self.assertEqual(board['ready_task_ids'], ['feature'])
        self.assertEqual(board['assignments'][0]['task_id'], 'feature')
        for task in board['tasks'][1:]:
            self.assertEqual((task['status'], task['attempts'], task['reason'], task['job_id'], task['evidence']),
                             ('pending', 0, None, None, []))
        self.assertEqual(TaskStore(self.projects).get(self.pid), board)

    def test_invalid_batch_preserves_every_byte(self):
        self.batch([definition('existing')], 0)
        before = self.path.read_bytes()
        first = definition('first')
        invalid = [
            {}, {'tasks': []}, {'tasks': 'list'}, {'tasks': [first], 'reset': True},
            {'tasks': [first, None]}, {'tasks': [first, {}]},
            {'tasks': [first, dict(definition('second'), status='completed')]},
            {'tasks': [first, dict(definition('second'), priority=True)]},
            {'tasks': [first, definition('existing')]}, {'tasks': [first, first]},
            {'tasks': [first, definition('second', 'missing')]},
            {'tasks': [definition('first', 'second'), definition('second', 'first')]},
            {'tasks': [first, definition('second', 'second')]},
            {'tasks': [first, definition('second', 'first', 'first')]},
        ]
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.apply({'op': 'add_batch', **fields}, 1)
            self.assertEqual(self.path.read_bytes(), before)

    def test_combined_board_limit_and_unwritten_new_board(self):
        with self.assertRaises(ValueError):
            self.batch([definition('bad', 'missing')], 0)
        self.assertFalse(self.path.exists())
        self.batch([definition('initial')], 0)
        additions = [definition(f'task-{i}') for i in range(100)]
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.batch(additions, 1)
        self.assertEqual(self.path.read_bytes(), before)
        board = self.batch(additions[:99], 1)
        self.assertEqual((board['revision'], board['summary']['total']), (2, 100))

    def test_changed_revision_spec_or_stale_board_preserves_batch(self):
        self.batch([definition('initial')], 0)
        before = self.path.read_bytes()
        changed = dict(self.project['spec'], seed=self.project['spec']['seed'] + 1)
        with self.assertRaises(FileExistsError):
            self.batch([definition('next')], 0)
        self.projects.save_spec(self.pid, changed)
        for digest in (self.digest, spec_digest(changed)):
            with self.subTest(digest=digest), self.assertRaises(FileExistsError):
                self.batch([definition('next')], 1, digest)
        self.assertEqual(self.path.read_bytes(), before)

    def test_concurrent_batches_publish_one_whole_plan(self):
        barrier = threading.Barrier(2)

        def writer(prefix):
            store = TaskStore(self.projects)
            base, child = f'{prefix}-base', f'{prefix}-child'
            action = {'op': 'add_batch', 'tasks': [definition(child, base), definition(base)]}
            barrier.wait(timeout=5)
            try:
                return store.apply(self.pid, {'expected_revision': 0, 'spec_sha256': self.digest,
                                              'action': action})
            except FileExistsError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            boards = list(pool.map(writer, ('east', 'west')))
        self.assertEqual(boards.count(None), 1)
        persisted = self.store.get(self.pid)
        self.assertIn(persisted, boards)
        self.assertEqual(persisted['revision'], 1)
        self.assertIn([task['id'] for task in persisted['tasks']],
                      (['east-child', 'east-base'], ['west-child', 'west-base']))


if __name__ == '__main__':
    unittest.main()
