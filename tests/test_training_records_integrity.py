"""Independent checks for the workspace training ledger's integrity and durability."""

import copy
import json
import multiprocessing
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from command_center import lab_interface, studio_curriculum, training_lab
from command_center.provenance import spec_digest
from command_center.training_records import TrainingRecordStore


def record_action(empty_message='No equipment assigned'):
    submission = next(exercise['example'] for exercise in training_lab.lab_catalog()['exercises']
                      if exercise['id'] == 'interface')
    submission['states']['empty'] = empty_message
    return {'op': 'record', 'exercise_id': 'interface', 'role': 'ui', 'submission': submission}


def review_action(record_id, **changes):
    return {'op': 'review', 'record_id': record_id, 'reviewer_role': 'verification',
            'decision': 'accepted', 'note': 'Checked focus paths and both layouts.', **changes}


def competing_writer(workspace, barrier, responses, worker):
    store = TrainingRecordStore(workspace)
    data = {'expected_revision': 0, 'action': record_action(f'No equipment in slot {worker}')}
    barrier.wait(timeout=15)
    try:
        written = store.apply(data)
    except FileExistsError:
        responses.put(('conflict', worker))
    else:
        responses.put(('saved', written['records'][0]['id']))


class TrainingRecordIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name) / 'studio'
        self.workspace.mkdir()
        self.path = self.workspace / 'training-records.json'
        self.store = TrainingRecordStore(self.workspace)

    def apply(self, revision, action):
        return self.store.apply({'expected_revision': revision, 'action': action})

    def test_persisted_assessment_review_and_historical_rubric(self):
        self.assertEqual(self.store.read()['records'], [])
        action = record_action()
        original = copy.deepcopy(action)
        written = self.apply(0, action)
        record, = written['records']
        self.assertEqual(action, original)
        self.assertEqual(record['submission'], original['submission'])
        self.assertEqual(record['report'], training_lab.assess_submission('interface', original['submission']))
        self.assertIs(record['current'], True)
        self.assertIs(record['reference'], False)
        self.assertIsNone(record['review'])
        self.assertIsNotNone(datetime.fromisoformat(record['created_at']).utcoffset())
        reviewed = self.apply(1, review_action(record['id']))
        reviewed_record, = reviewed['records']
        review = reviewed_record['review']
        self.assertEqual({key: value for key, value in review.items() if key != 'reviewed_at'},
                         {key: review_action(record['id'])[key] for key in ('reviewer_role', 'decision', 'note')})
        self.assertGreaterEqual(datetime.fromisoformat(review['reviewed_at']), datetime.fromisoformat(record['created_at']))
        self.assertEqual(reviewed_record, dict(record, review=review))
        self.assertEqual(reviewed['revision'], 2)
        self.assertEqual(TrainingRecordStore(self.workspace).read(), reviewed)

        persisted = self.path.read_bytes()
        with patch.object(training_lab, 'VERSION', training_lab.VERSION + 1):
            historical = TrainingRecordStore(self.workspace).read()
            self.assertNotEqual(historical['lab_sha256'], written['lab_sha256'])
            self.assertEqual(historical['records'], [dict(reviewed_record, current=False)])
            self.assertEqual(self.path.read_bytes(), persisted)
            mixed = self.apply(2, record_action('No salvage in this hold'))
            by_id = {item['id']: item for item in mixed['records']}
            self.assertEqual(by_id.pop(record['id']), dict(reviewed_record, current=False))
            current, = by_id.values()
            self.assertIs(current['current'], True)
            self.assertEqual(current['report']['lab_sha256'], historical['lab_sha256'])

    def test_archived_exercise_remains_readable_after_catalog_removal(self):
        record, = self.apply(0, record_action())['records']
        catalog = training_lab.curriculum()
        catalog['tracks'] = [track for track in catalog['tracks'] if track['id'] != 'interface']
        with patch.object(training_lab, 'curriculum', return_value=catalog), patch.object(lab_interface, 'EXERCISES', []):
            snapshot = TrainingRecordStore(self.workspace).read()
            self.assertEqual(snapshot['records'], [dict(record, current=False)])
            self.assertEqual(snapshot['lab_sha256'], training_lab.lab_catalog()['lab_sha256'])
            before = self.path.read_bytes()
            with self.assertRaises(FileExistsError):
                self.apply(1, review_action(record['id']))
            self.assertEqual(self.path.read_bytes(), before)

    def test_v30_records_survive_the_v31_curriculum_expansion_without_rescoring(self):
        # Reconstruct the exact shipped v30 catalog, not merely an invented stale digest.
        with patch.object(studio_curriculum, 'extension_modules', return_value=()), \
                patch.object(training_lab, 'VERSION', 1):
            old_catalog = training_lab.lab_catalog()
            self.assertEqual(old_catalog['lab_sha256'],
                             '5d9ba57de3369cb03647c5da893cf14ee217025f81e0b79e4f3d523d7fa2afaf')
            record, = self.apply(0, record_action())['records']
            reviewed, = self.apply(1, review_action(record['id']))['records']
        persisted = self.path.read_bytes()
        snapshot = self.store.read()
        self.assertEqual(snapshot['revision'], 2)
        self.assertEqual(snapshot['records'], [dict(reviewed, current=False)])
        self.assertEqual(self.path.read_bytes(), persisted)
        self.assertNotEqual(snapshot['lab_sha256'], old_catalog['lab_sha256'])
        mixed = self.apply(2, record_action('No tools in this crate'))
        self.assertEqual(mixed['revision'], 3)
        self.assertEqual(next(row for row in mixed['records'] if row['id'] == record['id']),
                         dict(reviewed, current=False))
        self.assertEqual(sum(row['current'] for row in mixed['records']), 1)

    def test_v32_reviewed_records_survive_v33_without_rescoring(self):
        old_modules = studio_curriculum.extension_modules()[:6]
        with patch.object(studio_curriculum, 'extension_modules', return_value=old_modules), \
                patch.object(training_lab, 'VERSION', 2):
            old_catalog = training_lab.lab_catalog()
            self.assertEqual(old_catalog['lab_sha256'],
                             'e6cafd623df8cd1863e39d46da19b133d3a9679efd18cf078a3d30082b6f2722')
            record, = self.apply(0, record_action())['records']
            reviewed, = self.apply(1, review_action(record['id']))['records']
        persisted = self.path.read_bytes()
        current = self.store.read()
        self.assertEqual(current['records'], [dict(reviewed, current=False)])
        self.assertEqual(self.path.read_bytes(), persisted)
        self.assertNotEqual(current['lab_sha256'], old_catalog['lab_sha256'])
        self.assertEqual(current['revision'], 2)

    def test_stale_unreviewed_record_cannot_be_reviewed(self):
        written = self.apply(0, record_action())
        record, = written['records']
        before = self.path.read_bytes()
        with patch.object(training_lab, 'VERSION', training_lab.VERSION + 1):
            self.assertFalse(self.store.read()['records'][0]['current'])
            with self.assertRaises(FileExistsError):
                self.apply(1, review_action(record['id']))
        self.assertEqual(self.path.read_bytes(), before)

    def test_examples_and_failing_submissions_keep_their_provenance(self):
        action = record_action()
        example = next(exercise['example'] for exercise in training_lab.lab_catalog()['exercises']
                       if exercise['id'] == 'interface')
        reference, = self.apply(0, dict(action, submission=example))['records']
        self.assertIs(reference['reference'], True)
        self.assertEqual(reference['report']['status'], 'pass')
        action['submission']['states'].pop('full')
        result = self.apply(1, action)
        attempt, = [item for item in result['records'] if item['id'] != reference['id']]
        self.assertIs(attempt['reference'], False)
        self.assertEqual(attempt['report']['status'], 'fail')
        self.assertIn('feedback', [check['id'] for check in attempt['report']['checks'] if check['status'] == 'fail'])
        persisted = self.path.read_bytes()
        for item in (reference, attempt):
            with self.subTest(record=item['id']), self.assertRaises((ValueError, FileExistsError)):
                self.apply(2, review_action(item['id']))
            self.assertEqual(self.path.read_bytes(), persisted)
        for revision, item in enumerate((reference, attempt), start=2):
            reviewed = self.apply(revision, review_action(item['id'], decision='rejected'))
            rejected = next(row for row in reviewed['records'] if row['id'] == item['id'])
            self.assertEqual(rejected['review']['decision'], 'rejected')
            self.assertEqual(rejected['report'], item['report'])

    def test_invalid_actions_and_revision_conflicts_preserve_exact_ledger(self):
        written = self.apply(0, record_action())
        record, = written['records']
        action = record_action()
        review = review_action(record['id'])
        invalid_actions = [
            dict(action, role='unknown'), dict(action, role='architecture'), dict(action, exercise_id='unknown'),
            dict(action, submission={'x': ['y' * 4096] * 40}), dict(action, submission={'x': float('nan')}),
            dict(action, submission={}), dict(action, report=record['report']), dict(action, reference=False),
            dict(review, reviewer_role='ui'), dict(review, reviewer_role='unknown'), dict(review, note=' '),
            dict(review, note='z' * 513), dict(review, decision='pass'), dict(review, reviewed_at=record['created_at']),
        ]
        invalid_requests = [{'expected_revision': 1, 'action': bad} for bad in invalid_actions]
        invalid_requests += [
            {'expected_revision': True, 'action': action}, {'expected_revision': 1.0, 'action': action},
            {'expected_revision': 1, 'action': action, 'records': []}, {'action': action},
        ]
        before = self.path.read_bytes()
        for request in invalid_requests:
            with self.subTest(op=request.get('action', {}).get('op'), fields=list(request)):
                with self.assertRaises(ValueError):
                    self.store.apply(request)
                self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(FileExistsError):
            self.apply(0, review)
        self.assertEqual(self.path.read_bytes(), before)
        self.apply(1, review)
        before = self.path.read_bytes()
        with self.assertRaises((ValueError, FileExistsError)):
            self.apply(2, dict(review, reviewer_role='lead', decision='rejected'))
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_or_ambiguous_state_cannot_be_read_or_overwritten(self):
        self.apply(0, record_action())
        pristine = self.path.read_bytes()
        ledger = json.loads(pristine)
        modified = copy.deepcopy(ledger)
        modified['records'][0]['submission']['states']['empty'] = 'Different equipment'
        bodies = [
            b'{', b'null', json.dumps(modified).encode(),
            b'{"revision":1,' + pristine.lstrip()[1:],
        ]
        # Resealing the outer document cannot repair a broken report-to-submission link.
        modified['ledger_sha256'] = spec_digest({key: value for key, value in modified.items()
                                                if key != 'ledger_sha256'})
        bodies.append(json.dumps(modified).encode())
        for index, body in enumerate(bodies):
            with self.subTest(damage=index):
                self.path.write_bytes(body)
                with self.assertRaises(ValueError):
                    TrainingRecordStore(self.workspace).read()
                with self.assertRaises(ValueError):
                    self.apply(1, record_action())
                self.assertEqual(self.path.read_bytes(), body)

    def test_symlink_to_an_existing_valid_ledger_is_never_followed(self):
        alternate = self.workspace.parent / 'other-studio'
        alternate.mkdir()
        TrainingRecordStore(alternate).apply({'expected_revision': 0, 'action': record_action()})
        external = alternate / self.path.name
        original = external.read_bytes()
        self.path.symlink_to(external)
        with self.assertRaises(ValueError):
            self.store.read()
        with self.assertRaises(ValueError):
            self.apply(1, record_action())
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(external.read_bytes(), original)

    def test_independent_processes_have_one_winner_per_revision(self):
        context = multiprocessing.get_context('spawn')
        count = 4
        barrier = context.Barrier(count)
        responses = context.Queue()
        processes = [context.Process(target=competing_writer, args=(self.workspace, barrier, responses, worker))
                     for worker in range(count)]
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=20)
                self.assertEqual(process.exitcode, 0)
            outcomes = [responses.get(timeout=3) for _ in processes]
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=3)
            responses.close()
            responses.join_thread()
        self.assertEqual(sorted(status for status, _ in outcomes), ['conflict'] * (count - 1) + ['saved'])
        saved_id, = [value for status, value in outcomes if status == 'saved']
        snapshot = TrainingRecordStore(self.workspace).read()
        self.assertEqual(snapshot['revision'], 1)
        self.assertEqual([record['id'] for record in snapshot['records']], [saved_id])
