import copy
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from command_center import recovery
from command_center.checkpoints import CheckpointStore
from command_center.defect_store import DefectStore
from command_center.evidence_history import EvidenceHistory
from command_center.handoff_store import HandoffStore
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest
from command_center.release_store import ReleaseStore
from command_center.supervisor import audit_project
from command_center.task_store import TaskStore
from command_center.work_orders import work_orders


ROOT = Path(__file__).resolve().parents[1]


def reseal(bundle):
    bundle['bundle_sha256'] = spec_digest({key: value for key, value in bundle.items()
                                          if key != 'bundle_sha256'})


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.projects = ProjectStore(ROOT, self.workspace)
        self.project = self.projects.create('Recovery city', 'city')
        self.pid = self.project['id']
        self.digest = spec_digest(self.project['spec'])
        self.path = self.projects.directory(self.pid)

    def capture(self):
        return recovery.capture_recovery(self.projects, self.pid)

    def write_records(self):
        def request(revision, action):
            return dict(expected_revision=revision, spec_sha256=self.digest, action=action)

        tasks = TaskStore(self.projects)
        task = dict(id='scene', title='Inspect scene', role='content', priority=2, gate='manual', depends_on=[])
        tasks.apply(self.pid, request(0, dict(op='add', task=task)))
        board = tasks.apply(self.pid, request(1, dict(op='start', task_id='scene')))
        order = work_orders(self.project, board)['orders'][0]
        HandoffStore(self.projects).apply(self.pid, request(0, dict(
            op='submit', task_id='scene', order_id=order['order_id'], summary='Inspected scene',
            outcome='progress', evidence=['Scene reported one light'], changed_paths=[],
            next_action='Lead to review scene')))
        CheckpointStore(self.projects).save(self.pid, dict(
            expected_revision=0, spec_sha256=self.digest, elapsed_seconds=5, status='paused',
            completed_work=['Scene inspection'], verification_evidence=['Scene opened'],
            remaining_work=['Lead review'], next_action='Review handoff'))
        DefectStore(self.projects).apply(self.pid, request(0, dict(
            op='add', title='Dim entrance', severity='low', description='Lamp obstructed',
            evidence=['Door obscures lamp'])))
        audit = audit_project(self.project, None, None, None, None, None)
        EvidenceHistory(self.projects).capture(self.pid, dict(
            expected_revision=0, spec_sha256=self.digest, note='Before lighting fix'), audit)
        # A release can remain on record after its external output goes offline.
        releases = ReleaseStore(self.projects, SimpleNamespace(jobs=self.workspace / 'jobs'))
        with patch.object(releases, '_verified_seal', return_value='a' * 64):
            releases.apply(self.pid, request(0, dict(op='promote', job_id='b' * 32)))

    def test_complete_snapshot_preserves_historical_records_without_jobs(self):
        self.write_records()
        self.projects.save_spec(self.pid, dict(self.project['spec'], seed=self.project['spec']['seed'] + 1))
        expected = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.path.iterdir()}
        directory_time = self.path.stat().st_mtime_ns
        bundle = self.capture()
        self.assertEqual(set(bundle['records']), set(expected))
        for name, record in bundle['records'].items():
            data = json.loads(expected[name][0])
            self.assertEqual(record, {'data': data, 'sha256': spec_digest(data)})
        self.assertNotEqual(bundle['spec_sha256'], self.digest)
        self.assertEqual(bundle['records']['task-board.json']['data']['spec_sha256'], self.digest)
        self.assertTrue(recovery.verify_recovery(json.loads(json.dumps(bundle, indent=4))))
        self.assertEqual(bundle, self.capture())
        self.assertEqual(directory_time, self.path.stat().st_mtime_ns)
        self.assertEqual(expected, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.path.iterdir()})
        self.assertFalse((self.workspace / 'jobs').exists())

    def test_initial_capture_allowlists_paths_and_represents_absence(self):
        outside = self.workspace / 'private'
        outside.write_bytes(b'private bytes')
        (self.path / 'unrelated.json').symlink_to(outside)
        (self.path / 'jobs').mkdir()
        (self.path / 'jobs' / 'job.json').write_bytes(b'not a record')
        bundle = self.capture()
        names = {'project.json', 'spec.json', 'task-board.json', 'checkpoint.json',
                 'defects.json', 'releases.json', 'evidence-history.json', 'handoffs.json'}
        self.assertEqual(set(bundle['records']), names)
        self.assertEqual({n for n, v in bundle['records'].items() if v is None},
                         names - {'project.json', 'spec.json'})
        self.assertTrue(recovery.verify_recovery(bundle))
        self.assertNotIn('private bytes', json.dumps(bundle))
        self.assertEqual(set(p.name for p in self.path.iterdir()),
                         {'project.json', 'spec.json', 'unrelated.json', 'jobs'})

    def test_digests_and_resealed_scope_errors(self):
        original = self.capture()
        mutations = [
            lambda b: b.update(bundle_sha256='0' * 64),
            lambda b: b['records']['spec.json']['data'].update(seed=1011),
            lambda b: b['records']['project.json'].update(sha256='0' * 64),
            lambda b: b.update(format='other'),
            lambda b: b.update(project_id='../outside'),
            lambda b: b.update(project_id='foreign'),
            lambda b: b.update(spec_sha256='0' * 64),
            lambda b: b.update(extra='field'),
            lambda b: b['records'].update({'../job.json': None}),
            lambda b: b['records'].pop('checkpoint.json'),
            lambda b: b['records'].update({'spec.json': None}),
            lambda b: b['records'].update({'handoffs.json': []}),
            lambda b: b['records']['project.json'].update(extra=0),
            lambda b: b['records']['spec.json'].update(data=[]),
        ]
        for index, alter in enumerate(mutations):
            for repair_outer in (False, True):
                if index == 0 and repair_outer:
                    continue
                with self.subTest(index=index, repair_outer=repair_outer):
                    bundle = copy.deepcopy(original)
                    alter(bundle)
                    if repair_outer:
                        reseal(bundle)
                    with self.assertRaises(ValueError):
                        recovery.verify_recovery(bundle)

    def test_matching_hashes_cannot_hide_schema_or_ownership_errors(self):
        self.write_records()
        original = self.capture()
        for name, change in [('project.json', {'kind': 'unknown'}),
                             ('project.json', {'created_at': 'today'}), ('task-board.json', {'tasks': [0]}),
                             ('checkpoint.json', {'elapsed_seconds': True}), ('releases.json', {'releases': []}),
                             ('defects.json', {'items': []}), ('evidence-history.json', {'revision': 59}),
                             ('handoffs.json', {'items': []}), ('handoffs.json', {'project_id': 'elsewhere'})]:
            with self.subTest(name=name, change=change):
                bundle = copy.deepcopy(original)
                entry = bundle['records'][name]
                entry['data'].update(change)
                entry['sha256'] = spec_digest(entry['data'])
                reseal(bundle)
                with self.assertRaises(ValueError):
                    recovery.verify_recovery(bundle)

    def test_source_type_parse_and_size_errors_preserve_bad_records(self):
        path = self.path / 'defects.json'
        for raw in [b'{', b'null', b'[]', b'{"secret":3}', b'\xff', b' ' * (recovery.MAX_RECORD_BYTES + 1)]:
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.capture()
            self.assertEqual(path.read_bytes(), raw)
        path.unlink()
        (self.path / 'spec.json').unlink()
        with self.assertRaisesRegex(ValueError, 'required record spec.json'):
            self.capture()
        self.assertFalse((self.path / 'spec.json').exists())

    def test_unicode_size_limit_uses_utf8_and_hash_uses_studio_identity(self):
        data = {'note': '雪' * 25}
        compact_size = len(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        with patch.object(recovery, 'MAX_RECORD_BYTES', compact_size):
            self.assertEqual(recovery._record_digest(data, 'spec.json'), spec_digest(data))
            with self.assertRaisesRegex(ValueError, 'storage limit'):
                recovery._record_digest({'note': data['note'] + '雪'}, 'spec.json')

    def test_known_file_symlinks_dangling_links_and_fifos_fail(self):
        outside = self.workspace / 'other-spec'
        outside.write_bytes(b'{}')
        for name in recovery.RECORD_NAMES:
            path = self.path / name
            backup = path.read_bytes() if path.exists() else None
            if backup is not None:
                path.unlink()
            for target in [outside, self.workspace / 'absent']:
                path.symlink_to(target)
                with self.assertRaises(ValueError):
                    self.capture()
                self.assertTrue(path.is_symlink())
                path.unlink()
            os.mkfifo(path)
            with self.assertRaises(ValueError):
                self.capture()
            path.unlink()
            if backup is not None:
                path.write_bytes(backup)
        self.assertEqual(outside.read_bytes(), b'{}')

    def test_capture_waits_for_the_same_project_writer_lock(self):
        signal = threading.Event()

        def capture():
            signal.set()
            return self.capture()

        with ThreadPoolExecutor(max_workers=1) as threads:
            fd = os.open(self.path, os.O_DIRECTORY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                pending = threads.submit(capture)
                self.assertTrue(signal.wait(2))
                with self.assertRaises(TimeoutError):
                    pending.result(timeout=0.1)
                spec = dict(self.project['spec'], seed=self.project['spec']['seed'] + 1)
                (self.path / 'spec.json').write_text(json.dumps(spec))
            finally:
                os.close(fd)
            self.assertEqual(pending.result(timeout=3)['spec_sha256'], spec_digest(spec))

    def test_cli_verifies_detached_file_and_fails_on_bad_input(self):
        path = self.workspace / 'download.json'
        bundle = self.capture()
        path.write_text(json.dumps(bundle, indent=2))
        cmd = [sys.executable, '-m', 'command_center.recovery', 'verify', str(path)]
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
        summary = json.loads(result.stdout)
        self.assertTrue(summary['verified'])
        self.assertEqual(summary['bundle_sha256'], bundle['bundle_sha256'])
        self.assertIn('separately', summary['note'])
        for data in ['{', json.dumps(dict(bundle, bundle_sha256=True)),
                     '{"format":"other",' + json.dumps(bundle)[1:]]:
            path.write_text(data)
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('error', json.loads(result.stderr))
            self.assertEqual(path.read_text(), data)
        path.write_bytes(b'x' * 101)
        with patch.object(recovery, 'MAX_BUNDLE_BYTES', 100), self.assertRaisesRegex(ValueError, 'size limit'):
            recovery._read_bundle(path)


if __name__ == '__main__':
    unittest.main()
