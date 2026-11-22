from copy import deepcopy
import unittest

from command_center import lab_reference_combat as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def failed(data):
    return {row['id'] for row in lab.assess('reference-combat', data) if row['status'] == 'fail'}


class CombatReferenceLabTests(unittest.TestCase):
    def test_example_is_repeatable_complete_and_immutable(self):
        data = example()
        original = deepcopy(data)
        result = lab.assess('reference-combat', data)
        self.assertEqual(data, original)
        self.assertEqual(lab.assess('reference-combat', data), result)
        self.assertEqual([row['id'] for row in result], [c['id'] for c in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in result))

    def test_different_timing_and_same_frame_deposit_with_two_reactions(self):
        data = example()
        data.update(frames=18, delay=2, recovery=2)
        data['inputs'] = {'tap': [0, 1, 4, 8, 12], 'spark': [2, 6, 14],
                          'bank': [5, 14, 16], 'watch': [6, 14]}
        data['expected'] = {
            'accepted': [0, 4, 8, 12], 'busy': [1], 'deposits': [14], 'refused': [5, 16],
            'final_panel': 2, 'impacts': [{'frame': f, 'kind': k} for f, k in
                                          [(2, 'chip'), (6, 'open'), (10, 'miss'), (14, 'chime')]],
            'keeper': [{'frame': f, 'kind': k} for f, k in [(6, 'inspect'), (14, 'cheer'), (14, 'work')]],
            'hidden_opening': [{'frame': 14, 'kind': 'search'}, {'frame': 14, 'kind': 'work'}],
        }
        self.assertEqual(failed(data), set())
        data['expected']['keeper'][-2:] = reversed(data['expected']['keeper'][-2:])
        self.assertEqual(failed(data), {'witness-memory'})

    def test_only_the_earliest_legal_repeat_counts_and_delay_is_bounded(self):
        data = example()
        data['frames'] = 16
        data['inputs']['tap'] = [0, 1, 3, 6, 9]
        data['expected']['accepted'] = [0, 3, 6, 9]
        self.assertIn('command-timing', failed(data))
        data = example()
        data['delay'] = 3
        self.assertIn('command-timing', failed(data))
        data = example()
        data['inputs']['tap'].remove(1)
        data['expected']['busy'] = []
        self.assertEqual(failed(data), {'command-timing'})

    def test_impact_frame_is_busy_and_cannot_overwrite_pending_contact(self):
        data = example()
        data['inputs']['tap'] = list(range(8))
        data['expected']['busy'] = [1, 3, 5, 7]
        self.assertEqual(failed(data), set())
        data['expected']['accepted'].append(7)
        self.assertEqual(failed(data), {'command-timing'})

    def test_a_tap_left_pending_at_the_horizon_fails_even_with_exact_predictions(self):
        data = example()
        data['inputs']['tap'].append(9)
        data['expected']['accepted'].append(9)
        self.assertEqual(failed(data), {'changing-scene'})

    def test_impact_requires_a_matching_frame_and_a_real_change_of_scenery(self):
        for wrong_kind in ('chip', 'open', 'miss'):
            data = example()
            data['expected']['impacts'][-1]['kind'] = wrong_kind
            self.assertEqual(failed(data), {'changing-scene'})
        data = example()
        data['expected']['final_panel'] = 1
        self.assertEqual(failed(data), {'changing-scene'})
        data = example()
        data['inputs']['spark'] = [2, 4, 6]
        self.assertTrue({'changing-scene', 'team-objective', 'witness-memory'} <= failed(data))

    def test_one_light_banks_once_and_unlit_attempts_are_required(self):
        data = example()
        data['expected']['deposits'] = [8, 9]
        self.assertEqual(failed(data), {'team-objective'})
        data = example()
        data['inputs']['bank'] = [8]
        data['expected']['refused'] = []
        self.assertEqual(failed(data), {'team-objective'})
        data = example()
        data['inputs']['bank'] = []
        data['expected'].update(deposits=[], refused=[], final_panel=0)
        data['expected']['keeper'].pop()
        data['expected']['hidden_opening'].pop()
        self.assertEqual(failed(data), {'team-objective'})

    def test_late_observer_sees_chime_without_knowledge_of_the_opening(self):
        data = example()
        data['inputs']['watch'] = [7]
        data['expected']['keeper'] = deepcopy(data['expected']['hidden_opening'])
        self.assertEqual(failed(data), {'witness-memory'})
        data = example()
        data['expected']['hidden_opening'] = deepcopy(data['expected']['keeper'])
        self.assertEqual(failed(data), {'witness-memory'})
        data = example()
        data['inputs']['watch'] = [5]
        self.assertEqual(failed(data), {'witness-memory'})

    def test_an_opening_changes_future_impacts_until_deposit_restores_the_panel(self):
        data = example()
        data['frames'] = 15
        data['inputs']['tap'] += [10, 12]
        data['inputs']['spark'] += [11, 13]
        data['expected']['accepted'] += [10, 12]
        data['expected']['impacts'] += [{'frame': 11, 'kind': 'chip'}, {'frame': 13, 'kind': 'open'}]
        data['expected']['final_panel'] = 0
        self.assertEqual(failed(data), set())

    def test_malformed_and_unbounded_data_are_rejected(self):
        for mutate in (
            lambda d: d.update(frames=49), lambda d: d.update(delay=False), lambda d: d.update(recovery=0),
            lambda d: d['inputs'].update(tap=[1, 0]), lambda d: d['inputs'].update(watch=[5, 5]),
            lambda d: d['inputs'].update(spark=[-1]), lambda d: d['inputs'].update(bank=[10]),
            lambda d: d['inputs'].update(tap=[[]]), lambda d: d['inputs'].update(extra=[]),
            lambda d: d['expected'].update(final_panel=3), lambda d: d['expected'].update(refused=[1.0]),
            lambda d: d['expected']['keeper'][0].update(kind='glare'),
            lambda d: d['expected']['impacts'][0].update(kind='inspect'),
            lambda d: d['expected']['impacts'][0].update(extra='x'),
            lambda d: d['expected'].update(keeper=d['expected']['keeper'] * 8),
            lambda d: d['expected'].pop('hidden_opening'),
        ):
            with self.subTest(mutation=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess('reference-combat', data)
        for key, value in [('unknown', {}), ('reference-combat', None), ('reference-combat', [])]:
            with self.assertRaises(ValueError):
                lab.assess(key, value)


if __name__ == '__main__':
    unittest.main()
