import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from command_center.checkpoints import CheckpointStore
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest


ROOT = Path(__file__).resolve().parents[1]


class CheckpointStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.projects = ProjectStore(ROOT, self.workspace)
        self.project = self.projects.create('Test Project', 'city')
        self.project_id = self.project['id']
        self.path = self.projects.directory(self.project_id) / 'checkpoint.json'
        self.digest = spec_digest(self.project['spec'])
        self.store = CheckpointStore(self.projects)
        self.data = {
            'expected_revision': 0, 'spec_sha256': self.digest, 'elapsed_seconds': 42,
            'status': 'in_progress', 'completed_work': ['Built the scene'],
            'verification_evidence': ['Smoke test passed'], 'remaining_work': ['Review lighting'],
            'next_action': 'Inspect the night scene',
        }

    def test_empty_then_durable_projection_and_manual_time(self):
        empty = {'project_id': self.project_id, 'spec_sha256': self.digest, 'state': 'empty',
                 'revision': 0, 'checkpoint': None, 'target_seconds': 18000, 'remaining_seconds': 18000}
        self.assertEqual(self.store.get(self.project_id), empty)
        self.assertFalse(self.path.exists())
        saved = self.store.save(self.project_id, self.data)
        record = dict(self.data, project_id=self.project_id, revision=1)
        del record['expected_revision']
        stamp = saved['checkpoint']['updated_at']
        self.assertIsNotNone(datetime.fromisoformat(stamp).utcoffset())
        record['updated_at'] = stamp
        self.assertEqual(saved, dict(empty, state='current', revision=1, checkpoint=record,
                                     remaining_seconds=17958))
        self.assertEqual(json.loads(self.path.read_text()), record)
        reloaded = CheckpointStore(ProjectStore(ROOT, self.workspace))
        self.assertEqual(reloaded.get(self.project_id), saved)
        for revision, status in enumerate(('paused', 'blocked', 'completed'), 1):
            updated = dict(self.data, expected_revision=revision, status=status)
            if status == 'completed':
                updated.update(elapsed_seconds=18000, remaining_work=[], next_action='')
            saved = reloaded.save(self.project_id, updated)
            self.assertEqual(saved['checkpoint']['status'], status)
            self.assertEqual(saved['revision'], revision + 1)
            self.assertEqual(saved['remaining_seconds'], 18000 - updated['elapsed_seconds'])

    def test_spec_change_requires_explicit_zero_time_reset_and_matching_revision(self):
        first = self.store.save(self.project_id, self.data)
        changed = dict(self.project['spec'], seed=self.project['spec']['seed'] + 1)
        self.projects.save_spec(self.project_id, changed)
        current_digest = spec_digest(changed)
        stale = dict(first, state='stale', spec_sha256=current_digest, remaining_seconds=None)
        self.assertEqual(self.store.get(self.project_id), stale)
        reset = dict(self.data, spec_sha256=current_digest, expected_revision=1,
                     elapsed_seconds=0, reset_for_spec_change=True)
        for fields in ({'reset_for_spec_change': False}, {'expected_revision': 0},
                       {'spec_sha256': self.digest}):
            with self.subTest(fields=fields), self.assertRaises(FileExistsError):
                self.store.save(self.project_id, dict(reset, **fields))
            self.assertEqual(self.store.get(self.project_id), stale)
        with self.assertRaises(ValueError):
            self.store.save(self.project_id, dict(reset, elapsed_seconds=1))
        second = self.store.save(self.project_id, reset)
        self.assertEqual(second['revision'], 2)
        self.assertEqual(second['state'], 'current')
        self.assertEqual(second['checkpoint']['spec_sha256'], current_digest)
        self.assertEqual(second['remaining_seconds'], 18000)

    def test_prevents_lost_updates_and_same_spec_time_rewind(self):
        self.store.save(self.project_id, self.data)
        previous = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.store.save(self.project_id, self.data)
        for extra in ({}, {'reset_for_spec_change': True}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.store.save(self.project_id, dict(self.data, expected_revision=1, elapsed_seconds=0, **extra))
        self.assertEqual(self.path.read_bytes(), previous)

    def test_bad_payloads_cannot_change_prior_record(self):
        self.store.save(self.project_id, self.data)
        previous = self.path.read_bytes()
        valid = dict(self.data, expected_revision=1)
        bad = [None, [], {**valid, 'unexpected': 'field'}]
        bad.extend({k: v for k, v in valid.items() if k != field} for field in valid)
        for field, values in {
            'expected_revision': [True, -1, 1.0, '1'],
            'elapsed_seconds': [True, -1, 18001, 1.0],
            'status': [[], None, 'done'],
            'spec_sha256': [None, '', '0' * 63, 'x' * 64],
            'reset_for_spec_change': [None, 0, 'true'],
            'next_action': [None, '', '   ', 'a' * 1025],
            'completed_work': [None, {}, [True], [''], ['a' * 1025], ['ok'] * 33],
            'verification_evidence': ['smoke', ['  ']],
            'remaining_work': [4, [{}]],
        }.items():
            bad.extend({**valid, field: value} for value in values)
        for data in bad:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.store.save(self.project_id, data)
        self.assertEqual(self.path.read_bytes(), previous)

    def test_stale_client_digest_rejected_before_first_save(self):
        with self.assertRaises(FileExistsError):
            self.store.save(self.project_id, dict(self.data, spec_sha256='0' * 64))
        self.assertFalse(self.path.exists())

    def test_new_run_requires_current_completed_record_zero_time_and_latest_revision(self):
        new = dict(self.data, start_new_run=True, elapsed_seconds=0)
        with self.assertRaises(ValueError):
            self.store.save(self.project_id, new)
        self.store.save(self.project_id, self.data)
        with self.assertRaises(ValueError):
            self.store.save(self.project_id, dict(new, expected_revision=1))
        done = self.store.save(self.project_id, dict(self.data, expected_revision=1,
                               elapsed_seconds=18000, status='completed', next_action=''))
        new['expected_revision'] = done['revision']
        for field, value, error in [('expected_revision', 1, FileExistsError), ('elapsed_seconds', 1, ValueError),
                                    ('reset_for_spec_change', True, ValueError), ('start_new_run', 1, ValueError)]:
            with self.subTest(field=field), self.assertRaises(error):
                self.store.save(self.project_id, {**new, field: value})
            self.assertEqual(self.store.get(self.project_id), done)
        second = self.store.save(self.project_id, new)
        self.assertEqual(second['state'], 'current')
        self.assertEqual(second['revision'], 3)
        self.assertEqual(second['remaining_seconds'], 18000)
        self.assertEqual(second['checkpoint']['status'], 'in_progress')
        self.assertNotIn('start_new_run', second['checkpoint'])

    def test_concurrent_stores_have_one_winner_for_a_revision(self):
        ready = threading.Barrier(6)

        def save(worker):
            other = CheckpointStore(ProjectStore(ROOT, self.workspace))
            ready.wait(timeout=10)
            try:
                return other.save(self.project_id, dict(self.data, next_action=str(worker)))
            except FileExistsError:
                return None

        with ThreadPoolExecutor(max_workers=6) as pool:
            winners = [saved for saved in pool.map(save, range(6)) if saved is not None]
        self.assertEqual(winners, [self.store.get(self.project_id)])

    def test_rejects_invalid_persisted_records_without_overwriting_them(self):
        saved = self.store.save(self.project_id, self.data)['checkpoint']
        invalid = [None, [], {}, dict(saved, elapsed_seconds=-10), dict(saved, revision=0),
                   dict(saved, project_id='other'), dict(saved, updated_at='yesterday'),
                   dict(saved, next_action=9), dict(saved, unexpected=True)]
        for value in ['{broken', *(json.dumps(item) for item in invalid)]:
            self.path.write_text(value)
            for operation in (self.store.get, lambda pid: self.store.save(pid, self.data)):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    operation(self.project_id)
            self.assertEqual(self.path.read_text(), value)

    def test_rejects_links_nonregular_storage_and_unknown_project_ids(self):
        with self.assertRaises(FileNotFoundError):
            self.store.get('missing')
        with self.assertRaises(ValueError):
            self.store.get('../escape')
        destination = self.workspace / 'external'
        destination.write_text('unchanged')
        self.path.symlink_to(destination)
        for make in (None, os.mkfifo, lambda path: path.mkdir()):
            if make:
                self.path.unlink()
                make(self.path)
            with self.assertRaises(ValueError):
                self.store.get(self.project_id)
            with self.assertRaises(ValueError):
                self.store.save(self.project_id, self.data)
        self.assertEqual(destination.read_text(), 'unchanged')
        (self.path.parent.parent / 'alias').symlink_to(self.path.parent)
        with self.assertRaises(ValueError):
            self.store.get('alias')
        spec = self.path.with_name('spec.json')
        spec.unlink()
        spec.symlink_to(destination)
        with self.assertRaises(ValueError):
            self.store.get(self.project_id)

    def test_failed_atomic_write_preserves_previous_revision_and_cleans_stage(self):
        saved = self.store.save(self.project_id, self.data)
        entries = sorted(self.path.parent.iterdir())
        with patch('command_center.checkpoints.os.replace', side_effect=OSError('Disk error')):
            with self.assertRaises(OSError):
                self.store.save(self.project_id, dict(self.data, expected_revision=1))
        self.assertEqual(sorted(self.path.parent.iterdir()), entries)
        self.assertEqual(self.store.get(self.project_id), saved)


if __name__ == '__main__':
    unittest.main()
