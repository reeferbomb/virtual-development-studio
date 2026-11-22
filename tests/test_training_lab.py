"""Contract and boundary tests for the practical academy lab."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from command_center.provenance import spec_digest
from command_center.studio_curriculum import curriculum
from command_center.training_lab import assess_submission, lab_catalog, reject_duplicate_keys
from command_center.training_lab_cli import main


class TrainingLabTests(unittest.TestCase):
    def test_all_thirty_four_reference_exercises_have_measured_passing_checks(self):
        catalog = lab_catalog()
        tracks = curriculum()['tracks']
        self.assertEqual(catalog['version'], 5)
        self.assertEqual(len(tracks), 34)
        # Every original rubric and teaching artifact remains byte-identical
        # under the v2 catalog contract, despite the new catalog identity.
        self.assertEqual(spec_digest({**{k: v for k, v in catalog.items() if k != 'lab_sha256'},
                                      'version': 2, 'exercises': catalog['exercises'][:16]}),
                         'e6cafd623df8cd1863e39d46da19b133d3a9679efd18cf078a3d30082b6f2722')
        self.assertEqual(spec_digest({**{k: v for k, v in catalog.items() if k != 'lab_sha256'},
                                      'version': 3, 'exercises': catalog['exercises'][:22]}),
                         'b65506b5b1d6446baf9f62d71a1db6efae37bf1889d18acb75616feba04e3f7c')
        self.assertEqual(spec_digest({**{k: v for k, v in catalog.items() if k != 'lab_sha256'},
                                      'version': 4, 'exercises': catalog['exercises'][:28]}),
                         '4e5f88eb5266c45a8931327e7ac50aeaf99c4f2183e99846c0ca9d977080c2b0')
        self.assertEqual([e['id'] for e in catalog['exercises']], [t['id'] for t in tracks])
        self.assertEqual(catalog['lab_sha256'], spec_digest({k: v for k, v in catalog.items() if k != 'lab_sha256'}))
        for exercise, track in zip(catalog['exercises'], tracks, strict=True):
            with self.subTest(exercise=exercise['id']):
                self.assertEqual(exercise['roles'], track['roles'])
                result = assess_submission(exercise['id'], exercise['example'])
                self.assertEqual(result['status'], 'pass')
                self.assertEqual(result['summary'], {'pass': len(exercise['criteria']), 'fail': 0})
                self.assertEqual(result['submission_sha256'], spec_digest(exercise['example']))
                self.assertEqual(result['lab_sha256'], catalog['lab_sha256'])
                self.assertEqual(result['assessment_sha256'], spec_digest({k: v for k, v in result.items() if k != 'assessment_sha256'}))
                self.assertEqual(result, assess_submission(exercise['id'], exercise['example']))
                self.assertEqual([c['id'] for c in result['checks']], [c['id'] for c in exercise['criteria']])
        catalog['exercises'][0]['example'].clear()
        self.assertTrue(lab_catalog()['exercises'][0]['example'])

    def test_interface_assesses_real_layout_contrast_navigation_and_feedback(self):
        exercise = next(e for e in lab_catalog()['exercises'] if e['id'] == 'interface')
        bad = copy.deepcopy(exercise['example'])
        bad['screens'][0]['widgets'][0]['rect'][0] = -1
        bad['screens'][0]['widgets'][0]['foreground'] = bad['screens'][0]['widgets'][0]['background']
        bad['navigation']['edges'] = []
        bad['states'].pop('error')
        result = assess_submission('interface', bad)
        self.assertEqual(result['status'], 'fail')
        failures = {c['id'] for c in result['checks'] if c['status'] == 'fail'}
        self.assertTrue({'layout', 'contrast', 'focus', 'feedback'} <= failures)

    def test_rejects_unknown_malformed_and_unbounded_data(self):
        for exercise_id, submission in [
            ('unknown', {}), ('interface', []), ('interface', {}),
            ('interface', {'x': float('nan')}), ('interface', {'x': 'a' * 4097}),
            ('interface', {'x': [0] * 20001}), ('interface', {'x': {1: 'a'}}),
            (['interface'], {}), ('interface', {'x': 1 << 4096}),
            ('interface', {'x': ['a' * 4096] * 40}),
            ('interface', {'x': '\ud800'}),
        ]:
            with self.subTest(exercise=exercise_id):
                with self.assertRaises(ValueError):
                    assess_submission(exercise_id, submission)

    def test_duplicate_keys_are_rejected_instead_of_overwriting_evidence(self):
        with self.assertRaises(ValueError):
            json.loads('{"outer":{"accepted":true,"accepted":false}}',
                       object_pairs_hook=reject_duplicate_keys)

    def test_interface_rejects_invisible_feedback_and_fails_clipped_text_geometry(self):
        example = next(e['example'] for e in lab_catalog()['exercises'] if e['id'] == 'interface')
        example['screens'][0]['widgets'][0]['rect'][3] = 1
        result = assess_submission('interface', example)
        self.assertIn('layout', {c['id'] for c in result['checks'] if c['status'] == 'fail'})
        example['states'] = {'empty': '\u200b', 'full': '\u200c', 'error': '\u200d'}
        with self.assertRaises(ValueError):
            assess_submission('interface', example)

    def test_repeated_submission_does_not_mutate_input(self):
        example = next(e['example'] for e in lab_catalog()['exercises'] if e['id'] == 'interface')
        original = copy.deepcopy(example)
        assess_submission('interface', example)
        self.assertEqual(example, original)

    def test_cli_reference_run_and_individual_submission(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['examples']), 0)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary['summary'], {'pass': 34, 'fail': 0})
        example = next(e['example'] for e in lab_catalog()['exercises'] if e['id'] == 'interface')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'submission.json'
            path.write_text(json.dumps(example))
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(['assess', 'interface', str(path)]), 0)
            self.assertEqual(json.loads(output.getvalue()), assess_submission('interface', example))
            example['states'].pop('full')
            path.write_text(json.dumps(example))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(['assess', 'interface', str(path)]), 1)
            path.write_text('not a JSON document')
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(['assess', 'interface', str(path)]), 2)
