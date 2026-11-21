import copy
import unittest

from command_center.lab_persistence import EXERCISES, TRACK, assess


def sample():
    return copy.deepcopy(EXERCISES[0]['example'])


def scores(submission):
    return {row['id']: row for row in assess('persistence', submission)}


def observation(source, checkpoint, claimed, coins):
    return {'source': source, 'state': {'version': 2, 'checkpoint': checkpoint,
                                       'claimed': claimed, 'coins': coins}}


class PersistenceLabTests(unittest.TestCase):
    def test_catalog_contract_and_repeatability(self):
        self.assertEqual(set(TRACK), {'id', 'title', 'roles', 'workflow', 'deliverables',
                                      'verification', 'exercise'})
        self.assertEqual(TRACK['id'], 'persistence')
        self.assertEqual(TRACK['roles'], ['architecture', 'gameplay', 'verification', 'build_operations'])
        self.assertEqual([entry['id'] for entry in EXERCISES], ['persistence'])
        exercise = EXERCISES[0]
        self.assertEqual(set(exercise), {'id', 'title', 'brief', 'criteria', 'example'})
        original = copy.deepcopy(exercise)
        rows = assess('persistence', exercise['example'])
        self.assertEqual([row['id'] for row in rows], [row['id'] for row in exercise['criteria']])
        self.assertTrue(all(set(row) == {'id', 'status', 'detail'} and row['status'] == 'pass'
                            and row['detail'] for row in rows))
        self.assertEqual(assess('persistence', exercise['example']), rows)
        self.assertEqual(exercise, original)

    def test_fresh_route_decodes_noncontiguous_legacy_bits_and_orders_rewards(self):
        # Loot in the dock and spire predates the save at the kiln.
        old = observation('primary', 'kiln', ['dock', 'spire'], 9)
        first = observation('primary', 'vault', ['dock', 'vault', 'spire'], 14)
        second = observation('primary', 'kiln', ['dock', 'kiln', 'vault', 'spire'], 17)
        submission = {'legacy': {'version': 1, 'checkpoint_id': 1, 'claimed_mask': 9},
                      'route': ['vault', 'kiln'],
                      'expected': {'migration': old, 'interruption': first, 'retry': second,
                                   'fallback': dict(first, source='backup'),
                                   'unreadable': dict(second, source='unchanged')}}
        self.assertTrue(all(row['status'] == 'pass' for row in scores(submission).values()))

    def test_interrupted_writer_cannot_promote_or_destroy_prior_checkpoint(self):
        submission = sample()
        submission['expected']['interruption'] = copy.deepcopy(submission['expected']['retry'])
        result = scores(submission)
        self.assertEqual(result['atomic-write']['status'], 'fail')
        self.assertIn('interruption', result['atomic-write']['detail'])
        self.assertEqual(result['death-retry']['status'], 'pass')

    def test_migration_and_retry_predictions_are_measured(self):
        submission = sample()
        submission['expected']['migration']['state']['coins'] += 1
        submission['expected']['retry']['state']['coins'] += 1
        result = scores(submission)
        self.assertEqual(result['migration']['status'], 'fail')
        self.assertEqual(result['death-retry']['status'], 'fail')

    def test_corruption_requires_correct_state_and_source_for_both_failures(self):
        submission = sample()
        submission['expected']['fallback']['source'] = 'primary'
        self.assertEqual(scores(submission)['recovery']['status'], 'fail')
        submission = sample()
        submission['expected']['unreadable']['state'] = submission['expected']['fallback']['state']
        result = scores(submission)['recovery']
        self.assertEqual(result['status'], 'fail')
        self.assertIn('unreadable', result['detail'])

    def test_observationally_identical_route_cannot_cover_atomicity_or_retry(self):
        submission = sample()
        submission['legacy'] = {'version': 1, 'checkpoint_id': 0, 'claimed_mask': 1}
        submission['route'] = ['dock', 'dock']
        for name, row in submission['expected'].items():
            row['state'] = observation('primary', 'dock', ['dock'], 2)['state']
        result = scores(submission)
        self.assertEqual(result['migration']['status'], 'pass')
        self.assertEqual(result['atomic-write']['status'], 'fail')
        self.assertEqual(result['death-retry']['status'], 'fail')

    def test_malformed_and_unbounded_inputs_raise_value_error(self):
        for field, bad in [('version', 2), ('version', True), ('checkpoint_id', -1),
                           ('checkpoint_id', 4), ('claimed_mask', 16), ('claimed_mask', 1.0)]:
            with self.subTest(field=field, bad=bad):
                submission = sample()
                submission['legacy'][field] = bad
                with self.assertRaises(ValueError):
                    assess('persistence', submission)
        for bad in [['dock'] * 33, ['dock', 'void'], ['dock', []], []]:
            with self.subTest(route=bad):
                submission = sample()
                submission['route'] = bad
                with self.assertRaises(ValueError):
                    assess('persistence', submission)
        for key, bad in [('version', True), ('claimed', ['dock'] * 8), ('coins', True)]:
            with self.subTest(key=key):
                submission = sample()
                submission['expected']['migration']['state'][key] = bad
                with self.assertRaises(ValueError):
                    assess('persistence', submission)
        for value in [None, [], {'passed': True}, dict(sample(), unexpected=1)]:
            with self.assertRaises(ValueError):
                assess('persistence', value)
        with self.assertRaises(ValueError):
            assess('other', sample())


if __name__ == '__main__':
    unittest.main()
