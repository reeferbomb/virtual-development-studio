import copy
import fcntl
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from command_center import evidence_history as history
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest
from command_center.supervisor import audit_project


ROOT = Path(__file__).resolve().parents[1]


class EvidenceHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.projects = ProjectStore(ROOT, self.workspace)
        self.project = self.projects.create('Review', 'city')
        self.pid = self.project['id']
        self.store = history.EvidenceHistory(self.projects)
        self.path = self.projects.directory(self.pid) / history.REGISTRY
        self.audit = audit_project(self.project, None, None, None, None, None)
        self.request = dict(expected_revision=0, spec_sha256=self.audit['spec_sha256'], note='Review 1')

    def capture(self, revision=0):
        return self.store.capture(self.pid, dict(self.request, expected_revision=revision), self.audit)

    def reopen(self):
        return history.EvidenceHistory(ProjectStore(ROOT, self.workspace))

    def test_only_explicit_capture_writes_and_snapshots_survive_spec_changes(self):
        original = self.path.parent.stat().st_mtime_ns
        expected = dict(project_id=self.pid, revision=0, items=[], spec_sha256=self.audit['spec_sha256'])
        self.assertEqual(self.store.get(self.pid), expected)
        self.assertEqual(self.path.parent.stat().st_mtime_ns, original)
        self.assertFalse(self.path.exists())
        first = self.capture()
        observation = copy.deepcopy(first['items'][0])
        self.assertEqual(observation['checks'], self.audit['checks'])
        self.assertEqual(observation['status'], 'blocked')
        self.assertEqual(observation['note'], 'Review 1')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.audit['checks'][0]['evidence'] = 'Independent input object.'
        self.assertEqual(first['items'][0], observation)
        original = self.path.read_bytes()
        spec = dict(self.project['spec'], seed=self.project['spec']['seed'] + 1)
        project = self.projects.save_spec(self.pid, spec)
        digest = spec_digest(spec)
        self.assertEqual(self.reopen().get(self.pid), dict(first, spec_sha256=digest))
        self.assertEqual(self.path.read_bytes(), original)

        audit = audit_project(project, [], None, None, None, None)
        request = dict(self.request, expected_revision=1, spec_sha256=digest, note='Reviewed new seed.')
        second = self.reopen().capture(self.pid, request, audit)
        self.assertEqual(second['revision'], 2)
        self.assertEqual(second['items'][0]['spec_sha256'], digest)
        self.assertEqual(second['items'][0]['checks'], audit['checks'])
        self.assertNotEqual(observation['id'], second['items'][0]['id'])
        self.assertEqual(second['items'][1], observation)
        self.assertEqual(self.reopen().get(self.pid), second)

    def test_exact_requests_identity_and_stale_updates_leave_history_intact(self):
        self.capture()
        before = self.path.read_bytes()
        request = dict(self.request, expected_revision=1)
        for change in (dict(checks=[]), dict(status='pass'), dict(expected_revision=False),
                       dict(expected_revision=-1), dict(spec_sha256='bad')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.store.capture(self.pid, dict(request, **change), self.audit)
        for note in ('', ' \n', '\u200b', 'x' * 513, '\0discard', '\ud800', None, []):
            with self.subTest(note=note), self.assertRaises(ValueError):
                self.store.capture(self.pid, dict(request, note=note), self.audit)
        with self.assertRaises(ValueError):
            self.store.capture(self.pid, {k: v for k, v in request.items() if k != 'note'}, self.audit)
        with self.assertRaisesRegex(ValueError, 'another project'):
            self.store.capture(self.pid, request, dict(self.audit, project_id='another'))
        for req, audit in ((self.request, self.audit),
                           (dict(request, spec_sha256='a' * 64), self.audit),
                           (request, dict(self.audit, spec_sha256='b' * 64))):
            with self.assertRaises(FileExistsError):
                self.store.capture(self.pid, req, audit)
        self.assertEqual(self.path.read_bytes(), before)

    def test_rejects_missing_duplicate_or_inconsistent_audit_checks(self):
        checks = self.audit['checks']
        altered = [
            dict(status='pass'), dict(recommendations={}), dict(checks=checks[:-1]),
            dict(checks=checks[:-1] + [checks[0]]), dict(checks='[]'), dict(extra=True),
        ]
        for change in (dict(evidence=' '), dict(evidence='x' * (history.MAX_EVIDENCE + 1)),
                       dict(id=[]), dict(id='other'), dict(label='incorrect'),
                       dict(status='passed'), dict(status=[]), dict(other='unknown')):
            altered.append(dict(checks=[dict(checks[0], **change), *checks[1:]]))
        for change in altered:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.store.capture(self.pid, self.request, dict(self.audit, **change))
        self.assertFalse(self.path.exists())
        results = ['pass'] * len(checks)
        for state, overall in [('pass', 'pass'), ('pending', 'pending'), ('warn', 'attention'), ('fail', 'blocked')]:
            results.insert(0, state)
            rows = [dict(check, status=result) for check, result in zip(checks, results)]
            history.validate_checks(overall, rows)

    def test_corruption_locks_out_reads_and_writes_without_erasing_evidence(self):
        self.capture()
        record = json.loads(self.path.read_bytes())
        item = record['items'][0]
        records = [dict(record, project_id='other'), dict(record, revision=True), dict(record, revision=2),
                   dict(record, items=[]), dict(record, items=[item, item], revision=2), dict(record, extra=True)]
        for change in [dict(created_at='yesterday'), dict(created_at='2026-01-01'), dict(status='pass'),
                       dict(spec_sha256='xx'), dict(id='xx'), dict(note=''), dict(checks=[])]:
            records.append(dict(record, items=[dict(item, **change)]))
        records.append(dict(record, revision=2, items=[
            dict(item, created_at='2000-01-01T00:00:00+00:00'), dict(item, id='f' * 32)]))
        for raw in (b'{', b'\xff', b' ' * (history.MAX_FILE_BYTES + 1),
                    *(json.dumps(bad).encode() for bad in records)):
            self.path.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.store.get(self.pid)
            with self.assertRaises(ValueError):
                self.capture(1)
            self.assertEqual(self.path.read_bytes(), raw)

    def test_untrusted_file_types_rejected_and_failed_write_cleans_up(self):
        self.capture()
        before = self.path.read_bytes()
        for file in (self.path, self.path.parent / 'spec.json', self.path.parent / 'project.json'):
            original = self.workspace / file.name
            file.rename(original)
            file.symlink_to(original)
            with self.assertRaises(ValueError):
                self.store.get(self.pid)
            with self.assertRaises(ValueError):
                self.capture(1)
            file.unlink()
            os.mkfifo(file)
            with self.assertRaises(ValueError):
                self.store.get(self.pid)
            file.unlink()
            original.rename(file)
        entries = set(self.path.parent.iterdir())
        for operation in ('fsync', 'replace'):
            with patch.object(history.os, operation, side_effect=OSError('storage failure')):
                with self.assertRaisesRegex(OSError, 'storage failure'):
                    self.capture(1)
            self.assertEqual(set(self.path.parent.iterdir()), entries)
            self.assertEqual(self.path.read_bytes(), before)
        with patch.object(history, 'MAX_FILE_BYTES', len(before)), self.assertRaisesRegex(ValueError, 'limit'):
            self.capture(1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.capture(1)['revision'], 2)

    def test_one_hundred_capture_limit_never_evicts_history(self):
        for revision in range(history.MAX_ITEMS):
            last = self.capture(revision)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'at most 100'):
            self.capture(last['revision'])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.reopen().get(self.pid), last)

    def test_independent_concurrent_writers_same_revision_only_commit_once(self):
        barrier = threading.Barrier(2)

        def write(note):
            store = self.reopen()
            barrier.wait(timeout=5)
            try:
                return store.capture(self.pid, dict(self.request, note=note), self.audit)
            except FileExistsError:
                return None

        with ThreadPoolExecutor(max_workers=2) as threads:
            outcomes = list(threads.map(write, ('Review A', 'Review B')))
        self.assertEqual(outcomes.count(None), 1)
        final = self.reopen().get(self.pid)
        self.assertIn(final, outcomes)
        self.assertEqual(final['revision'], 1)
        self.assertEqual(len(final['items']), 1)

    def test_writer_rechecks_spec_after_waiting_for_lock(self):
        event = threading.Event()

        def write():
            event.set()
            return self.capture()

        with ThreadPoolExecutor(max_workers=1) as threads:
            fd = os.open(self.path.parent, os.O_DIRECTORY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                pending = threads.submit(write)
                self.assertTrue(event.wait(2))
                with self.assertRaises(TimeoutError):
                    pending.result(timeout=.1)
                changed = dict(self.project['spec'], seed=self.project['spec']['seed'] + 1)
                (self.path.parent / 'spec.json').write_text(json.dumps(changed))
            finally:
                os.close(fd)
            with self.assertRaisesRegex(FileExistsError, 'specification changed'):
                pending.result(timeout=2)
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()
