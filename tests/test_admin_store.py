import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from command_center import admin_store as store
from command_center.provenance import spec_digest


def _race_writer(path, stream, barrier, results):
    revision = store.load(path)['revision']
    barrier.wait(timeout=10)
    try:
        snapshot = store.append(path, revision, stream, {'op': 'record', 'stream_name': stream})
        results.put(('committed', snapshot['revision'], stream))
    except FileExistsError:
        results.put(('stale', revision, stream))


class AdminStoreTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.parent / 'journal.json'

    def seed(self):
        return store.append(self.path, 0, 'registry', {'op': 'record', 'payload': {'last': 2, 'first': 'café'}})

    def test_empty_load_is_read_only_and_append_preserves_both_streams(self):
        self.assertEqual(store.load(self.path), {'revision': 0, 'events': []})
        self.assertFalse(self.path.exists())
        first = self.seed()
        second = store.append(self.path, 1, 'tribunal', {'op': 'review'})
        self.assertEqual(second['revision'], 2)
        self.assertEqual(second['events'][0], first['events'][0])
        self.assertEqual([row['stream'] for row in second['events']], ['registry', 'tribunal'])
        self.assertEqual(second['events'][0]['previous_sha256'], '0' * 64)
        self.assertEqual(second['events'][1]['previous_sha256'], first['events'][0]['event_sha256'])
        for number, entry in enumerate(second['events'], 1):
            self.assertEqual(entry['revision'], number)
            self.assertEqual(entry['event_sha256'], spec_digest({key: value for key, value in entry.items()
                                                                 if key != 'event_sha256'}))
        self.assertEqual(store.load(self.path), second)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.parent.iterdir()), [self.path])

    def test_sorted_canonical_bytes_ignore_dict_insertion_order(self):
        first = self.seed()
        other = self.parent / 'other.json'
        changed = store.append(other, 0, 'registry', {'payload': {'first': 'café', 'last': 2}, 'op': 'record'})
        self.assertEqual(first, changed)
        self.assertEqual(self.path.read_bytes(), other.read_bytes())

    def test_stale_revision_and_invalid_candidate_preserve_the_original(self):
        first = self.seed()
        original = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            store.append(self.path, 0, 'tribunal', {'op': 'review'}, validator=self.fail)

        def reject(candidate):
            self.assertEqual(candidate['revision'], 2)
            self.assertEqual(candidate['events'][0], first['events'][0])
            self.assertEqual(candidate['events'][1]['stream'], 'tribunal')
            raise ValueError('Policy refused candidate')

        with self.assertRaisesRegex(ValueError, 'Policy refused'):
            store.append(self.path, 1, 'tribunal', {'op': 'review'}, validator=reject)
        with self.assertRaises(ValueError):
            store.append(self.path, 1, 'tribunal', {}, validator=lambda _: False)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(store.load(self.path), first)

        def inspect(candidate):
            candidate['events'][0]['event'].clear()
            candidate['events'].pop()

        second = store.append(self.path, 1, 'tribunal', {'op': 'review'}, validator=inspect)
        self.assertEqual(second['events'][0], first['events'][0])
        self.assertEqual(store.load(self.path, validator=inspect), second)

    def test_structural_json_and_history_tampering_are_rejected_on_read_and_write(self):
        self.seed()
        store.append(self.path, 1, 'tribunal', {'op': 'review'})
        original = self.path.read_bytes()
        for mutate in (
            lambda d: d.update(revision=True),
            lambda d: d.update(revision=1),
            lambda d: d.update(head_sha256='a' * 64),
            lambda d: d['events'][0].update(previous_sha256='a' * 64),
            lambda d: d['events'][0].update(stream='tribunal'),
            lambda d: d['events'][1]['event'].update(op='other'),
            lambda d: d['events'].reverse(),
            lambda d: (d['events'].pop(), d.update(revision=1)),
            lambda d: d['events'][1]['event'].update(number=float('inf')),
        ):
            with self.subTest(mutation=mutate):
                document = json.loads(original)
                mutate(document)
                tampered = json.dumps(document).encode()
                self.path.write_bytes(tampered)
                with self.assertRaises(ValueError):
                    store.load(self.path)
                with self.assertRaises(ValueError):
                    store.append(self.path, 2, 'registry', {'op': 'record'})
                self.assertEqual(self.path.read_bytes(), tampered)

        for invalid in (b'{"schema_version":1,"schema_version":1}', b'{"price": 1e9999}', b'\xff', b'{'):
            with self.subTest(invalid=invalid):
                self.path.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    store.load(self.path)

    def test_event_and_storage_limits_reject_without_replacing_the_journal(self):
        self.seed()
        original = self.path.read_bytes()
        nested = {}
        for _ in range(30):
            nested = {'child': nested}
        cyclic = {}
        cyclic['child'] = cyclic
        for event in ({'x': float('nan')}, {'x': '\ud800'}, {1: 'coerced'}, {'x': (1, 2)},
                      {'x': 'a' * store.MAX_EVENT_BYTES}, nested, cyclic, []):
            with self.assertRaises(ValueError):
                store.append(self.path, 1, 'tribunal', event)
        for revision, stream in ((True, 'registry'), (-1, 'registry'), (1, 'unexpected'), (1, [])):
            with self.assertRaises(ValueError):
                store.append(self.path, revision, stream, {})
        with patch.object(store, 'MAX_EVENTS', 1), self.assertRaises(ValueError):
            store.append(self.path, 1, 'tribunal', {})
        with patch.object(store, 'MAX_FILE_BYTES', len(original) + 1), self.assertRaises(ValueError):
            store.append(self.path, 1, 'tribunal', {})
        with patch.object(store, 'MAX_FILE_BYTES', len(original) - 1), self.assertRaises(ValueError):
            store.load(self.path)
        self.assertEqual(self.path.read_bytes(), original)

    def test_checkout_symlinks_nonregular_and_shared_paths_are_refused(self):
        self.seed()
        alias = self.parent / 'alias'
        alias.symlink_to(self.path)
        dangling = self.parent / 'dangling'
        dangling.symlink_to(self.parent / 'nonexistent')
        parent_alias = self.parent / 'parent-alias'
        parent_alias.symlink_to(self.parent, target_is_directory=True)
        shared = self.parent / 'shared'
        shared.mkdir()
        shared.chmod(0o777)
        fifo = self.parent / 'fifo'
        os.mkfifo(fifo)
        checkout = Path(store.__file__).resolve().parents[1] / 'unsafe-admin.json'
        for path in (checkout, alias, dangling, parent_alias / 'new.json', shared / 'new.json', fifo):
            with self.subTest(path=path.name):
                with self.assertRaises(ValueError):
                    store.load(path)
                with self.assertRaises(ValueError):
                    store.append(path, 0, 'registry', {})
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            store.load(self.path)
        self.path.chmod(0o600)
        hardlink = self.parent / 'hardlink'
        os.link(self.path, hardlink)
        with self.assertRaises(ValueError):
            store.load(self.path)

    def test_stage_failure_leaves_prior_bytes_and_cleans_temporary_file(self):
        self.seed()
        original = self.path.read_bytes()
        with patch.object(store.os, 'fsync', side_effect=OSError('expected failure')), self.assertRaises(OSError):
            store.append(self.path, 1, 'tribunal', {})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.parent.iterdir()), [self.path])

    def test_two_processes_attempt_one_revision_and_only_one_commits(self):
        context = multiprocessing.get_context('spawn')
        barrier = context.Barrier(2)
        results = context.Queue()
        workers = []
        try:
            for stream in ('registry', 'tribunal'):
                worker = context.Process(target=_race_writer, args=(self.path, stream, barrier, results))
                worker.start()
                workers.append(worker)
            for worker in workers:
                worker.join(timeout=15)
                self.assertEqual(worker.exitcode, 0)
            outcomes = [results.get(timeout=2) for _ in workers]
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                worker.join()
                worker.close()
            results.close()
        self.assertCountEqual([outcome for outcome, _, _ in outcomes], ['committed', 'stale'])
        winner = next(stream for outcome, revision, stream in outcomes if outcome == 'committed' and revision == 1)
        snapshot = store.load(self.path)
        self.assertEqual(snapshot['revision'], 1)
        self.assertEqual(snapshot['events'][0]['stream'], winner)


if __name__ == '__main__':
    unittest.main()
