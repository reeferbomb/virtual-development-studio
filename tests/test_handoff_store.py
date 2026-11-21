import fcntl
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from command_center import handoff_store, task_store
from command_center.handoff_store import HandoffStore, validate_history
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest
from command_center.work_orders import work_orders


ROOT = Path(__file__).resolve().parents[1]


class HandoffStoreTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.workspace = Path(workspace.name)
        self.projects = ProjectStore(ROOT, self.workspace)
        self.project = self.projects.create('Relay', 'city')
        self.pid = self.project['id']
        self.digest = spec_digest(self.project['spec'])
        self.tasks = task_store.TaskStore(self.projects)
        self.store = HandoffStore(self.projects)
        self.path = self.projects.directory(self.pid) / 'handoffs.json'
        self.definition = dict(id='review-door', title='Check the west door', role='verification',
                               priority=4, gate='manual', depends_on=[])

    def request(self, action, revision=0, digest=None):
        return dict(action=action, expected_revision=revision, spec_sha256=digest or self.digest)

    def task(self, action, revision):
        return self.tasks.apply(self.pid, self.request(action, revision))

    def start(self):
        self.task(dict(op='add', task=self.definition), 0)
        board = self.task(dict(op='start', task_id=self.definition['id']), 1)
        return self.order(board)

    def order(self, board):
        return work_orders(self.projects.get(self.pid), board)['orders'][0]

    def report(self, order):
        return dict(op='submit', task_id=order['task_id'], order_id=order['order_id'],
                    outcome='progress', summary='Retested the west exit.',
                    evidence=['The replay crossed the threshold at frame 44.'],
                    changed_paths=['tests/exit replay.py'], next_action='Review the replay.')

    def apply(self, action, revision=0, digest=None):
        return self.store.apply(self.pid, self.request(action, revision, digest))

    def review(self, item, decision='accepted'):
        return dict(op='review', handoff_id=item['id'], decision=decision,
                    note='Lead inspected the linked replay.')

    def reopen(self):
        return HandoffStore(ProjectStore(ROOT, self.workspace))

    def test_lifecycle_reviews_and_restarts_leave_task_board_untouched(self):
        empty = self.store.get(self.pid)
        self.assertEqual(empty, dict(project_id=self.pid, spec_sha256=self.digest, revision=0, items=[]))
        validate_history(empty)
        self.assertFalse(self.path.exists())
        order = self.start()
        board_path = self.path.parent / task_store.BOARD
        original_board = board_path.read_bytes()
        report = self.report(order)
        first = self.apply(report)['items'][0]
        self.assertRegex(first['id'], r'^[0-9a-f]{32}$')
        self.assertEqual((first['role'], first['attempt'], first['board_revision']),
                         ('verification', 1, 2))
        self.assertEqual((first['review'], first['review_note'], first['reviewed_at']),
                         ('pending', None, None))
        second = self.apply(dict(report, outcome='completed', changed_paths=[]), 1)
        self.assertEqual(second['items'][1], first)
        self.assertEqual(second['items'][0]['order_id'], first['order_id'])
        self.assertNotEqual(second['items'][0]['id'], first['id'])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.reopen().get(self.pid), second)
        self.assertEqual(original_board, board_path.read_bytes())
        self.task(dict(op='complete', task_id=order['task_id'], evidence=['Lead replayed.']), 2)
        completed_board = board_path.read_bytes()
        reviewed = self.reopen().apply(self.pid, self.request(self.review(first, 'rejected'), 2))
        self.assertEqual(reviewed['items'][1]['review'], 'rejected')
        self.assertGreaterEqual(reviewed['items'][1]['reviewed_at'], first['created_at'])
        self.assertEqual(reviewed['items'][1]['review_note'], self.review(first)['note'])
        result = self.apply(self.review(second['items'][0]), 3)
        self.assertEqual([i['review'] for i in result['items']], ['accepted', 'rejected'])
        self.assertEqual(self.reopen().get(self.pid), result)
        self.assertEqual(completed_board, board_path.read_bytes())
        self.assertEqual(result['revision'], 4)
        validate_history(result)
        with self.assertRaisesRegex(ValueError, 'already been reviewed'):
            self.apply(self.review(first), 4)
        with self.assertRaises(FileExistsError):
            self.apply(report, 4)
        self.assertEqual(result, self.store.get(self.pid))

    def test_running_identity_changes_on_board_revision_attempt_and_spec(self):
        first = self.start()
        report = self.report(first)
        self.apply(report)
        task_id = first['task_id']
        other = dict(self.definition, id='check-roof', role='content')
        board = self.task(dict(op='add', task=other), 2)
        second = self.order(board)
        self.assertNotEqual(second['order_id'], first['order_id'])
        with self.assertRaises(FileExistsError):
            self.apply(report, 1)
        with self.assertRaises(FileExistsError):
            self.apply(dict(self.report(second), task_id='check-roof'), 1)
        self.task(dict(op='requeue', task_id=task_id), 3)
        with self.assertRaises(FileExistsError):
            self.apply(self.report(second), 1)
        board = self.task(dict(op='start', task_id=task_id), 4)
        third = self.order(board)
        with self.assertRaises(FileExistsError):
            self.apply(self.report(second), 1)
        with self.assertRaisesRegex(FileExistsError, 'revision changed'):
            self.apply(self.report(third), 0)
        saved = self.apply(dict(self.report(third), outcome='blocked'), 1)
        self.assertEqual([i['attempt'] for i in saved['items']], [2, 1])
        self.assertEqual([i['board_revision'] for i in saved['items']], [5, 2])
        changed = dict(self.project['spec'], seed=self.project['spec']['seed'] + 1)
        self.projects.save_spec(self.pid, changed)
        digest = spec_digest(changed)
        self.assertEqual(self.reopen().get(self.pid), {**saved, 'spec_sha256': digest})
        for action, requested_digest, error in (
                (self.report(third), self.digest, 'specification changed'),
                (self.report(third), digest, 'Work order'),
                (self.review(saved['items'][0]), digest, 'Historical')):
            with self.subTest(action=action), self.assertRaisesRegex(FileExistsError, error):
                self.apply(action, 2, requested_digest)
        self.assertEqual(self.store.get(self.pid)['items'], saved['items'])

    def test_paths_and_bounds_are_validated_without_opening_any_paths(self):
        order = self.start()
        report = self.report(order)
        paths = [None, {}, 'file.txt', ['new/a.py'] * 17]
        invalid_names = [None, True, '', '.', '..', '/tmp/file', 'one/two/../file',
                         r'C:\tmp\file', 'C:relative', r'\tmp\file', r'\\server\share\file',
                         r'one\..\file', '\x00a', 'a\nb', 'a' * 257]
        actions = [dict(report, changed_paths=bad) for bad in paths + [[name] for name in invalid_names]]
        for field in ('summary', 'next_action'):
            actions.extend(dict(report, **{field: bad}) for bad in (' ', 'a' * 513, '\ud800', None))
        actions.extend(dict(report, evidence=bad) for bad in ([], 'text', ['a'] * 9, [None], ['a' * 513]))
        actions.extend([dict(report, task_id='../task'), dict(report, order_id=[]),
                        dict(report, outcome=['blocked']), dict(report, review='accepted'),
                        {key: val for key, val in report.items() if key != 'next_action'}])
        for action in actions:
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.apply(action)
        self.assertFalse(self.path.exists())
        good_paths = ['nested/file.md', '.hidden/nested file.py', 'ä' * 256] + [f'a/{n}' for n in range(13)]
        saved = self.apply(dict(report, summary='a' * 512, next_action='b' * 512,
                                evidence=['c' * 512] * 8, changed_paths=good_paths))
        self.assertEqual(saved['items'][0]['changed_paths'], good_paths)
        decision = self.review(saved['items'][0])
        for change in (dict(decision=None), dict(note=' '), dict(note='a' * 513), dict(handoff_id='bad')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.apply(dict(decision, **change), 1)
        with patch.object(handoff_store, 'MAX_ITEMS', 1), self.assertRaisesRegex(ValueError, 'at most 1'):
            self.apply(report, 1)
        self.assertEqual(saved, self.reopen().get(self.pid))

    def test_concurrent_submissions_and_reviews_have_one_winner_per_revision(self):
        order = self.start()
        def race(actions, revision):
            barrier = threading.Barrier(2)
            def write(action):
                store = self.reopen()
                barrier.wait(timeout=3)
                try:
                    return store.apply(self.pid, self.request(action, revision))
                except FileExistsError:
                    return None
            with ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(write, actions))
            self.assertEqual(results.count(None), 1)
            result = self.reopen().get(self.pid)
            self.assertIn(result, results)
            return result
        saved = race([self.report(order), self.report(order)], 0)
        self.assertEqual(len(saved['items']), 1)
        item = saved['items'][0]
        result = race([self.review(item), self.review(item, 'rejected')], 1)
        self.assertEqual(result['revision'], 2)
        self.assertIn(result['items'][0]['review'], ('rejected', 'accepted'))

    def test_waiting_writer_checks_the_board_under_the_same_project_lock(self):
        report = self.report(self.start())
        started = threading.Event()
        def write():
            started.set()
            return self.apply(report)
        with ThreadPoolExecutor(max_workers=1) as workers:
            directory = os.open(self.path.parent, os.O_DIRECTORY)
            try:
                fcntl.flock(directory, fcntl.LOCK_EX)
                future = workers.submit(write)
                self.assertTrue(started.wait(2))
                with self.assertRaises(TimeoutError):
                    future.result(timeout=.1)
                _, board = task_store._read_state(directory, self.pid)
                board['revision'] += 1
                board['tasks'][0]['status'] = 'pending'
                task_store._write_board(directory, board)
            finally:
                os.close(directory)
            with self.assertRaises(FileExistsError):
                future.result(timeout=2)
        self.assertFalse(self.path.exists())

    def test_corrupt_records_and_unsafe_files_fail_closed(self):
        report = self.report(self.start())
        saved = self.apply(report)
        record = json.loads(self.path.read_bytes())
        first = record['items'][0]
        records = [dict(record, project_id='other'), dict(record, items=[]), dict(record, revision=2),
                   dict(record, revision=True), dict(record, items=[first, first], revision=2)]
        for change in [dict(role=[]), dict(attempt=0), dict(attempt=True), dict(board_revision=0),
                       dict(id='../x'), dict(order_id='a'), dict(spec_sha256=None), dict(task_id='Dot'),
                       dict(review=[]), dict(review_note='unearned'), dict(review='accepted'),
                       dict(created_at='invalid'), dict(changed_paths=['../x']), dict(evidence=[''])]:
            records.append(dict(record, items=[dict(first, **change)]))
        reviewed = dict(first, review='rejected', review_note='Reviewed.', reviewed_at='2000-01-01T00:00:00+00:00')
        records.append(dict(record, items=[reviewed], revision=2))
        inconsistent = dict(first, id='0' * 32, role='architecture')
        records.append(dict(record, items=[first, inconsistent], revision=2))
        for raw in [b'{', *(json.dumps(value).encode() for value in records)]:
            self.path.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.reopen().get(self.pid)
            with self.assertRaises(ValueError):
                self.apply(report, 1)
            self.assertEqual(self.path.read_bytes(), raw)
        self.path.write_text(json.dumps(record))
        outside = self.workspace / 'untouched.json'
        self.path.rename(outside)
        before = outside.read_bytes()
        self.path.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.apply(report, 1)
        self.path.unlink()
        os.mkfifo(self.path)
        with self.assertRaises(ValueError):
            self.reopen().get(self.pid)
        self.assertEqual(outside.read_bytes(), before)
        self.path.unlink()
        outside.rename(self.path)
        self.assertEqual(saved, self.store.get(self.pid))

    def test_failed_atomic_write_preserves_prior_history_and_pending_review(self):
        report = self.report(self.start())
        saved = self.apply(report)
        entries = set(self.path.parent.iterdir())
        for operation in ('fsync', 'replace'):
            with patch.object(handoff_store.os, operation, side_effect=OSError('disk failure')):
                with self.assertRaisesRegex(OSError, 'disk failure'):
                    self.apply(self.review(saved['items'][0]), 1)
            self.assertEqual(self.reopen().get(self.pid), saved)
            self.assertEqual(set(self.path.parent.iterdir()), entries)
        self.assertEqual(self.apply(self.review(saved['items'][0]), 1)['revision'], 2)


if __name__ == '__main__':
    unittest.main()
