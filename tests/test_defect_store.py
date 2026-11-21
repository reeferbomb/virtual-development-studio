import fcntl
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from command_center import defect_store
from command_center.defect_store import DefectStore
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest


ROOT = Path(__file__).resolve().parents[1]


class DefectStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.projects = ProjectStore(ROOT, self.workspace)
        project = self.projects.create('Defect review', 'city')
        self.pid, self.spec = project['id'], project['spec']
        self.digest = spec_digest(self.spec)
        self.store = DefectStore(self.projects)
        self.path = self.projects.directory(self.pid) / 'defects.json'
        self.add = dict(op='add', title='Occluded door', severity='high',
                        description='A mesh covers the west exit.', evidence=['Screenshot 102, west exit.'])

    def request(self, action, revision=0, digest=None):
        return dict(expected_revision=revision, spec_sha256=self.digest if digest is None else digest,
                    action=action)

    def apply(self, action, revision=0, digest=None):
        return self.store.apply(self.pid, self.request(action, revision, digest))

    def reopen(self):
        return DefectStore(ProjectStore(ROOT, self.workspace))

    def test_read_only_empty_state_and_full_restart_lifecycle(self):
        summary = dict(current_open=0, current_resolved=0, historical_open=0, historical_resolved=0)
        self.assertEqual(self.store.get(self.pid),
                         dict(project_id=self.pid, revision=0, items=[], spec_sha256=self.digest,
                              summary=summary))
        self.assertFalse(self.path.exists())
        opened = self.apply(self.add)
        item = opened['items'][0]
        self.assertRegex(item['id'], r'^[0-9a-f]{32}$')
        self.assertEqual(item['spec_sha256'], self.digest)
        self.assertEqual(item['status'], 'open')
        self.assertEqual(item['evidence'], self.add['evidence'])
        self.assertEqual(item['created_at'], item['updated_at'])
        self.assertEqual(opened['summary'], dict(summary, current_open=1))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        close = dict(op='resolve', defect_id=item['id'], evidence=['Walkthrough replay crossed west exit.'])
        resolved = self.reopen().apply(self.pid, self.request(close, 1))
        self.assertEqual(resolved['revision'], 2)
        self.assertEqual(resolved['items'][0]['status'], 'resolved')
        self.assertEqual(resolved['items'][0]['evidence'], item['evidence'] + close['evidence'])
        self.assertEqual(resolved['summary'], dict(summary, current_resolved=1))
        reopen = dict(op='reopen', defect_id=item['id'], evidence=['Retest at frame 115 still fails.'])
        reopened = self.apply(reopen, 2)
        self.assertEqual(reopened['revision'], 3)
        self.assertEqual(reopened['summary'], opened['summary'])
        self.assertEqual(reopened['items'][0]['evidence'], resolved['items'][0]['evidence'] + reopen['evidence'])
        self.assertEqual(reopened['items'][0]['created_at'], item['created_at'])
        self.assertEqual(self.reopen().get(self.pid), reopened)

    def test_historical_open_and_resolved_items_are_read_only(self):
        first = self.apply(self.add)['items'][0]['id']
        second = self.apply(dict(self.add, title='Lower doorway'), 1)['items'][1]['id']
        closed = self.apply(dict(op='resolve', defect_id=second, evidence=['Reviewed capture B.']), 2)
        changed = dict(self.spec, seed=self.spec['seed'] + 1)
        self.projects.save_spec(self.pid, changed)
        digest = spec_digest(changed)
        historical = self.store.get(self.pid)
        self.assertEqual(historical['items'], closed['items'])
        self.assertEqual(historical['summary'], dict(current_open=0, current_resolved=0,
                                                    historical_open=1, historical_resolved=1))
        before = self.path.read_bytes()
        for action in [dict(op='resolve', defect_id=first, evidence=['Checked again.']),
                       dict(op='reopen', defect_id=second, evidence=['Saw another failure.'])]:
            with self.assertRaisesRegex(FileExistsError, 'Historical'):
                self.apply(action, 3, digest)
        for revision, request_digest in [(3, self.digest), (0, digest)]:
            with self.assertRaises(FileExistsError):
                self.apply(self.add, revision, request_digest)
        self.assertEqual(self.path.read_bytes(), before)
        new = self.apply(self.add, 3, digest)
        self.assertEqual(new['items'][:2], historical['items'])
        self.assertEqual(new['summary'], dict(historical['summary'], current_open=1))
        self.assertEqual(new['revision'], 4)

    def test_invalid_inputs_and_transitions_leave_record_intact(self):
        item = self.apply(self.add)['items'][0]
        before = self.path.read_bytes()
        close = dict(op='resolve', defect_id=item['id'], evidence=['Verified walk.'])
        bad_actions = [None, {}, {'op': []}, {'op': 'delete'}, dict(self.add, id=item['id']),
                       dict(self.add, title=' '), dict(self.add, title='a' * 161),
                       dict(self.add, description='a' * 2049), dict(self.add, description=None),
                       dict(self.add, severity=[]), dict(self.add, severity='urgent'),
                       {k: v for k, v in self.add.items() if k != 'description'},
                       dict(close, status='resolved'), dict(close, defect_id='../bad'),
                       dict(close, defect_id='a' * 32), dict(close, op='reopen')]
        for evidence in [None, [], 'verified', [{}], [''], [' \t\n'], [1], ['x' * 513], ['x'] * 9,
                         ['\x1b[42m'], ['\ud800'], ['\u200b']]:
            bad_actions.extend([dict(self.add, evidence=evidence), dict(close, evidence=evidence)])
        requests = [self.request(action, 1) for action in bad_actions]
        valid = self.request(close, 1)
        requests.extend([[], None, dict(valid, extra=True), dict(valid, expected_revision=True),
                         dict(valid, expected_revision=-1), dict(valid, spec_sha256='F' * 64),
                         {k: v for k, v in valid.items() if k != 'expected_revision'}])
        for data in requests:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.store.apply(self.pid, data)
        self.assertEqual(self.path.read_bytes(), before)
        self.apply(close, 1)
        with self.assertRaisesRegex(ValueError, 'already resolved'):
            self.apply(close, 2)

    def test_limits_preserve_a_resolution_slot_and_never_discard_old_evidence(self):
        action_notes = ['note'] * 8
        item = self.apply(dict(self.add, evidence=action_notes))['items'][0]
        close = dict(op='resolve', defect_id=item['id'], evidence=action_notes)
        reopen = dict(close, op='reopen')
        self.apply(close, 1)
        self.apply(reopen, 2)
        self.apply(dict(close, evidence=['resolution']), 3)  # 25 cumulative
        with self.assertRaisesRegex(ValueError, '31'):
            self.apply(dict(reopen, evidence=['note'] * 7), 4)
        self.apply(dict(reopen, evidence=['note'] * 6), 4)
        with self.assertRaisesRegex(ValueError, '32'):
            self.apply(dict(close, evidence=['note', 'more']), 5)
        closed = self.apply(dict(close, evidence=['last retest']), 5)
        self.assertEqual(len(closed['items'][0]['evidence']), 32)
        self.assertEqual(closed['items'][0]['evidence'][:8], action_notes)
        with patch.object(defect_store, 'MAX_ITEMS', 1), self.assertRaisesRegex(ValueError, 'at most 1'):
            self.apply(self.add, 6)
        self.assertEqual(self.store.get(self.pid), closed)

    def test_atomic_failure_preserves_last_commit_and_next_write_recovers(self):
        self.apply(self.add)
        before = self.path.read_bytes()
        entries = set(self.path.parent.iterdir())
        for name in ('fsync', 'replace'):
            with patch.object(defect_store.os, name, side_effect=OSError('storage failure')):
                with self.assertRaisesRegex(OSError, 'storage failure'):
                    self.apply(self.add, 1)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(set(self.path.parent.iterdir()), entries)
        # A process killed before rename can leave its private staging file.
        (self.path.parent / '.defects-abandoned.tmp').write_text('{')
        self.assertEqual(self.reopen().get(self.pid)['revision'], 1)
        committed = self.apply(self.add, 1)
        self.assertEqual(self.reopen().get(self.pid), committed)

    def test_two_independent_writers_cannot_both_commit_one_revision(self):
        barrier = threading.Barrier(2)
        def write(title):
            store = self.reopen()
            barrier.wait(timeout=5)
            try:
                return store.apply(self.pid, self.request(dict(self.add, title=title)))
            except FileExistsError:
                return None

        with ThreadPoolExecutor(max_workers=2) as threads:
            outcomes = list(threads.map(write, ('Doorway', 'Hallway')))
        self.assertEqual(outcomes.count(None), 1)
        stored = self.reopen().get(self.pid)
        self.assertIn(stored, outcomes)
        self.assertEqual(len(stored['items']), 1)
        self.assertEqual(stored['revision'], 1)

    def test_waiting_writer_rechecks_spec_inside_project_lock(self):
        started = threading.Event()
        def write():
            started.set()
            return self.apply(self.add)

        with ThreadPoolExecutor(max_workers=1) as threads:
            directory = os.open(self.path.parent, os.O_DIRECTORY)
            try:
                fcntl.flock(directory, fcntl.LOCK_EX)
                future = threads.submit(write)
                self.assertTrue(started.wait(2))
                with self.assertRaises(TimeoutError):
                    future.result(timeout=.1)
                new_spec = dict(self.spec, seed=self.spec['seed'] + 1)
                (self.path.parent / 'spec.json').write_text(json.dumps(new_spec))
            finally:
                os.close(directory)
            with self.assertRaisesRegex(FileExistsError, 'specification changed'):
                future.result(timeout=2)
        self.assertFalse(self.path.exists())

    def test_corrupt_oversize_or_untrusted_storage_fails_closed(self):
        saved = self.apply(self.add)
        record = json.loads(self.path.read_bytes())
        item = record['items'][0]
        bad_records = [dict(record, revision=True), dict(record, revision=0),
                       dict(record, project_id='elsewhere'), dict(record, items=[item] * 2),
                       dict(record, revision=2), dict(record, items=[])]
        bad_records.extend(dict(record, items=[dict(item, **changes)]) for changes in
                           [dict(status='done'), dict(status='resolved'), dict(spec_sha256='../escape'),
                            dict(id='X' * 32), dict(created_at='bad'), dict(updated_at='9999-01-01'),
                            dict(updated_at='2000-01-01T00:00:00+00:00'), dict(evidence=[' '])])
        for raw in (b'{bad', b' ' * (defect_store.MAX_FILE_BYTES + 1),
                    *(json.dumps(r).encode() for r in bad_records)):
            self.path.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.store.get(self.pid)
            with self.assertRaises(ValueError):
                self.apply(self.add, 1)
            self.assertEqual(self.path.read_bytes(), raw)
        self.path.write_text(json.dumps(record))
        self.assertEqual(self.store.get(self.pid), saved)
        for path in (self.path, self.path.parent / 'spec.json', self.path.parent / 'project.json'):
            outside = self.workspace / f'outside-{path.name}'
            path.rename(outside)
            old_bytes = outside.read_bytes()
            try:
                path.symlink_to(outside)
                with self.assertRaises(ValueError):
                    self.store.get(self.pid)
                with self.assertRaises(ValueError):
                    self.apply(self.add, 1)
                path.unlink()
                os.mkfifo(path)
                with self.assertRaises(ValueError):
                    self.store.get(self.pid)
                self.assertEqual(outside.read_bytes(), old_bytes)
            finally:
                path.unlink()
                outside.rename(path)
        with self.assertRaises(ValueError):
            self.store.get('../../outside')
        with self.assertRaises(FileNotFoundError):
            self.store.get('missing-project')
        self.assertEqual(self.store.get(self.pid), saved)


if __name__ == '__main__':
    unittest.main()
