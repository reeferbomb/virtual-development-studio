"""Storage boundaries and practice-review rules for the private Academy ledger."""
import copy
import json
import os
import stat
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from command_center import training_lab, training_records
from command_center.provenance import spec_digest


class TrainingRecordTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.path = Path(workspace.name)
        self.file = self.path / 'training-records.json'
        self.store = training_records.TrainingRecordStore(self.path)
        self.example = next(row['example'] for row in training_lab.lab_catalog()['exercises']
                            if row['id'] == 'interface')

    def record(self):
        submission = copy.deepcopy(self.example)
        submission['states']['full'] = 'Trade or discard an item before picking up another.'
        return dict(op='record', exercise_id='interface', role='ui', submission=submission)

    def review(self, identifier, **changes):
        return {**dict(op='review', record_id=identifier, reviewer_role='verification',
                       decision='accepted', note='Checked the inventory states.'), **changes}

    def apply(self, action, revision=0):
        return self.store.apply(dict(expected_revision=revision, action=action))

    def test_empty_read_has_no_side_effects(self):
        result = self.store.read()
        self.assertEqual(set(result), {'revision', 'records', 'lab_sha256', 'note'})
        self.assertEqual(result, dict(revision=0, records=[], note=result['note'],
                                      lab_sha256=training_lab.lab_catalog()['lab_sha256']))
        self.assertTrue(result['note'])
        absent = training_records.TrainingRecordStore(self.path / 'not-created')
        self.assertEqual(result, absent.read())
        self.assertEqual(list(self.path.iterdir()), [])

    def test_repository_workspace_and_traversal_into_it_are_rejected(self):
        checkout = Path(training_records.__file__).resolve().parents[1]
        for path in (checkout, checkout / 'command_center', checkout.parent / 'absent' / '..' / checkout.name):
            with self.subTest(path=path), self.assertRaises(ValueError):
                training_records.TrainingRecordStore(path).read()

    def test_roundtrip_assessment_review_ownership_and_order(self):
        action = self.record()
        snapshot = self.apply(action)
        item, = snapshot['records']
        self.assertEqual(set(item), {'id', 'exercise_id', 'role', 'created_at', 'reference',
                                     'submission', 'report', 'review', 'current'})
        self.assertRegex(item['id'], r'^[a-f0-9]{32}$')
        self.assertEqual(item['report'], training_lab.assess_submission('interface', action['submission']))
        self.assertEqual(item['submission'], action['submission'])
        original_message = item['submission']['states']['full']
        action['submission']['states']['full'] = 'A later caller edit.'
        self.assertEqual(item['submission']['states']['full'], original_message)
        self.assertTrue(item['current'])
        self.assertFalse(item['reference'])
        self.assertIsNone(item['review'])
        self.assertNotIn('current', json.loads(self.file.read_text())['records'][0])
        self.assertEqual(stat.S_IMODE(self.file.stat().st_mode), 0o600)
        second = self.apply(action, 1)['records'][0]
        self.assertNotEqual(item['id'], second['id'])
        result = self.apply(self.review(item['id']), 2)
        self.assertEqual(result['revision'], 3)
        newest, oldest = result['records']
        self.assertEqual(newest, second)
        self.assertEqual(oldest['review'], dict(decision='accepted', reviewer_role='verification',
                         note='Checked the inventory states.', reviewed_at=oldest['review']['reviewed_at']))
        self.assertGreaterEqual(oldest['review']['reviewed_at'], oldest['created_at'])
        self.assertEqual(training_records.TrainingRecordStore(self.path).read(), result)
        with self.assertRaises(ValueError):
            self.apply(self.review(item['id'], decision='rejected'), 3)
        self.assertEqual(result, self.store.read())

    def test_record_can_require_the_exact_previously_assessed_report(self):
        action = self.record()
        preview = training_lab.assess_submission(action['exercise_id'], action['submission'])
        bound = dict(action, expected_assessment_sha256=preview['assessment_sha256'])
        saved = self.apply(bound)
        self.assertEqual(saved['records'][0]['report'], preview)
        original = self.file.read_bytes()
        with patch.object(training_lab, 'VERSION', training_lab.VERSION + 1):
            with self.assertRaises(FileExistsError):
                self.apply(bound, 1)
        for bad in (None, False, 'invalid', 'f' * 63):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.apply(dict(action, expected_assessment_sha256=bad), 1)
        with self.assertRaises(ValueError):
            self.apply(dict(bound, extra=True), 1)
        with self.assertRaises(ValueError):
            self.apply(dict(self.review(saved['records'][0]['id']),
                            expected_assessment_sha256=preview['assessment_sha256']), 1)
        self.assertEqual(self.file.read_bytes(), original)

    def test_reference_and_failed_evidence_can_only_be_rejected(self):
        role_action = self.record()
        role_action['submission'] = dict(reversed(self.example.items()))
        reference = self.apply(role_action)['records'][0]
        self.assertTrue(reference['reference'])
        bad = self.record()
        bad['submission']['states'].pop('empty')
        failed = self.apply(bad, 1)['records'][0]
        self.assertEqual(failed['report']['status'], 'fail')
        for index, item in enumerate((reference, failed), start=2):
            with self.assertRaises(ValueError):
                self.apply(self.review(item['id']), index)
            result = self.apply(self.review(item['id'], reviewer_role='lead', decision='rejected'), index)
            self.assertEqual(result['revision'], index + 1)

    def test_strict_request_and_review_fields_leave_data_unchanged(self):
        action = self.record()
        for data in (None, {'action': action}, dict(action=action, expected_revision=False),
                     dict(action=action, expected_revision=-1), dict(action=action, expected_revision=0, actor='x')):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.store.apply(data)
        for invalid in ({}, dict(action, op='edit'), dict(action, report={}), dict(action, role='content'),
                        dict(action, role='lead'), dict(action, exercise_id=[]), dict(action, submission=[])):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.apply(invalid)
        self.assertFalse(self.file.exists())
        item = self.apply(action)['records'][0]
        original = self.file.read_bytes()
        for changes in ({'reviewer_role': 'ui'}, {'reviewer_role': ['lead']}, {'reviewer_role': 'manager'},
                        {'decision': 'pending'}, {'note': '  '}, {'note': 'x' * 513}, {'reference': False},
                        {'record_id': []}, {'record_id': '1' * 32}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.apply(self.review(item['id'], **changes), 1)
        with self.assertRaises(FileExistsError):
            self.apply(self.review(item['id']), 0)
        self.assertEqual(original, self.file.read_bytes())

    def test_stale_catalog_preserves_history_and_blocks_reviews(self):
        item = self.apply(self.record())['records'][0]
        original = self.file.read_bytes()
        with patch.object(training_lab, 'VERSION', training_lab.VERSION + 1):
            historical = self.store.read()['records'][0]
            self.assertEqual(historical, dict(item, current=False))
            for decision in ('accepted', 'rejected'):
                with self.assertRaises(FileExistsError):
                    self.apply(self.review(item['id'], decision=decision), 1)
            self.assertEqual(original, self.file.read_bytes())
            recent, old = self.apply(self.record(), 1)['records']
            self.assertTrue(recent['current'])
            self.assertEqual(historical, old)

    def test_tampering_and_resealed_fabricated_reports_cannot_be_loaded_or_overwritten(self):
        self.apply(self.record())
        saved = json.loads(self.file.read_text())
        for variant in ('review', 'report', 'valuation', 'revision', 'reference', 'duplicate'):
            record = copy.deepcopy(saved)
            item = record['records'][0]
            if variant == 'review':
                item['role'] = 'gameplay'  # Valid role; edit without resealing the ledger.
            elif variant == 'report':
                item['report']['checks'][0]['detail'] = 'A different calculated detail'
                item['report']['assessment_sha256'] = spec_digest(
                    {k: v for k, v in item['report'].items() if k != 'assessment_sha256'})
            elif variant == 'valuation':
                item['report']['summary']['fail'] = False
            elif variant == 'revision':
                record['revision'] = 2
            elif variant == 'reference':
                item['reference'] = True
            if variant != 'review':
                record['ledger_sha256'] = spec_digest({k: v for k, v in record.items() if k != 'ledger_sha256'})
            raw = json.dumps(record)
            if variant == 'duplicate':
                raw = raw.replace('"role": "ui"', '"role": "ui", "role": "ui"')
            self.file.write_text(raw)
            with self.subTest(variant=variant):
                with self.assertRaises(ValueError):
                    self.store.read()
                with self.assertRaises(ValueError):
                    self.apply(self.record(), 1)
                self.assertEqual(raw, self.file.read_text())

    def test_full_ledger_preserves_all_records_and_still_allows_review(self):
        self.assertEqual(training_records.MAX_RECORDS, 600)
        with patch.object(training_records, 'MAX_RECORDS', 2):
            first = self.apply(self.record())['records'][0]
            self.apply(self.record(), 1)
            original = self.file.read_bytes()
            with self.assertRaises(ValueError):
                self.apply(self.record(), 2)
            self.assertEqual(original, self.file.read_bytes())
            self.assertEqual(self.apply(self.review(first['id']), 2)['revision'], 3)

    def test_symlinks_nonregular_and_oversize_files_fail_closed(self):
        target = self.path / 'private-target'
        target.write_text('untouched')
        self.file.symlink_to(target)
        with self.assertRaises(ValueError):
            self.store.read()
        with self.assertRaises(ValueError):
            self.apply(self.record())
        self.assertEqual(target.read_text(), 'untouched')
        self.file.unlink()
        alias = self.path / 'alias'
        alias.symlink_to(self.path, target_is_directory=True)
        with self.assertRaises(ValueError):
            training_records.TrainingRecordStore(alias).read()
        self.file.mkdir()
        with self.assertRaises(ValueError):
            self.store.read()
        self.file.rmdir()
        os.mkfifo(self.file)
        with self.assertRaises(ValueError):
            self.store.read()
        self.file.unlink()
        with self.file.open('wb') as stream:
            stream.truncate(training_records.MAX_FILE_BYTES + 1)
        with self.assertRaises(ValueError):
            self.store.read()

    def test_staging_failure_leaves_prior_record_and_cleans_temp_file(self):
        self.apply(self.record())
        previous = self.file.read_bytes()
        with patch.object(os, 'replace', side_effect=OSError('simulated storage failure')):
            with self.assertRaises(OSError):
                self.apply(self.record(), 1)
        self.assertEqual(previous, self.file.read_bytes())
        self.assertEqual(list(self.path.iterdir()), [self.file])

    def test_competing_independent_handles_have_one_revision_winner(self):
        ready = Barrier(2)
        def writer():
            store = training_records.TrainingRecordStore(self.path)
            revision = store.read()['revision']
            ready.wait(timeout=10)
            try:
                store.apply({'expected_revision': revision, 'action': self.record()})
            except FileExistsError:
                return 'conflict'
            return 'saved'
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(writer) for _ in range(2)]
            self.assertCountEqual([f.result(timeout=10) for f in futures], ['saved', 'conflict'])
        self.assertEqual(len(self.store.read()['records']), 1)
