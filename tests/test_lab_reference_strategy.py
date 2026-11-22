from copy import deepcopy
import unittest

from command_center import lab_reference_strategy as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def results(data):
    return {row['id']: row for row in lab.assess('reference-strategy', data)}


def failures(data):
    return {key for key, row in results(data).items() if row['status'] == 'fail'}


class ReferenceStrategyLabTests(unittest.TestCase):
    def test_original_exercise_is_replayable_and_matches_criteria(self):
        data = example()
        checks = results(data)
        self.assertEqual(lab.TRACK['id'], 'reference-strategy')
        self.assertEqual(list(checks), [row['id'] for row in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(row['status'] == 'pass' and row['detail'] for row in checks.values()))
        self.assertEqual(checks, results(data))
        self.assertEqual(data, example())

    def test_terrain_trace_checks_water_transfer_and_persistent_flood(self):
        for turn, field in ((0, 'diverted'), (2, 'bed_water'), (4, 'yard_water'), (3, 'eroded')):
            with self.subTest(turn=turn, field=field):
                data = example()
                cell = data['plans']['nursery'][turn]['expected']
                cell[field] = int(not cell[field])
                self.assertEqual(failures(data), {'terrain-trace'})

    def test_material_cannot_teleport_even_with_correct_total(self):
        data = example()
        recorded = data['plans']['nursery'][3]['expected']
        recorded['sediment'] -= 1
        recorded['spares'] += 1
        self.assertEqual(failures(data), {'material-budget'})

    def test_work_uses_post_drain_water_and_does_not_award_blocked_output(self):
        data = example()
        flooded = data['plans']['freight'][3]['expected']
        self.assertFalse(flooded['accepted'])
        self.assertEqual(flooded['deliveries'], 4)
        flooded.update(accepted=True, deliveries=6)
        self.assertEqual(failures(data), {'resource-trace'})

    def test_refused_earthwork_still_advances_weather(self):
        state = lab._simulate({'barrier': 1, 'spares': 0}, [8], [{'action': 'raise'}])[0]
        self.assertEqual(state, {'accepted': False, 'diverted': 1, 'overflow': 7,
                                 'bed_water': 0, 'yard_water': 5, 'eroded': 1,
                                 'barrier': 0, 'spares': 0, 'sediment': 1,
                                 'seedlings': 0, 'deliveries': 0})

    def test_erosion_threshold_and_water_limit_are_inclusive(self):
        state = lab._simulate({'barrier': 2, 'spares': 0}, [6], [{'action': 'ship'}])[0]
        self.assertTrue(state['accepted'])
        self.assertEqual((state['yard_water'], state['eroded'], state['deliveries']), (2, 1, 2))
        self.assertEqual(state['barrier'], 1)

    def test_strategic_outcomes_follow_declared_targets_not_labels(self):
        data = example()
        data['goals']['freight'] = 8
        self.assertEqual(failures(data), {'strategic-choice'})
        data = example()
        data['goals']['freight'] = 2
        self.assertEqual(failures(data), {'strategic-choice'})

    def test_counterfactual_isolated_change_must_cause_target_loss(self):
        data = example()
        data['counterfactual']['turns'][0]['action'] = 'raise'
        self.assertIn('counterfactual', failures(data))
        data = example()
        data['counterfactual']['turns'][1]['action'] = 'wait'
        self.assertIn('counterfactual', failures(data))
        data = example()
        data['counterfactual']['basis'] = 'freight'
        self.assertEqual(failures(data), {'counterfactual'})

    def test_strict_bounded_shapes_and_values(self):
        for mutate in (
            lambda d: d.update(source_url='https://example.invalid'),
            lambda d: d['start'].update(barrier=True),
            lambda d: d['start'].update(spares=17),
            lambda d: d['goals'].update(nursery=1),
            lambda d: d['rain'].append(999),
            lambda d: d['rain'].pop(),
            lambda d: d['plans']['nursery'][0].update(action='create-matter'),
            lambda d: d['plans']['nursery'][0]['expected'].update(seedlings=True),
            lambda d: d['plans']['nursery'][0]['expected'].update(accepted=1),
            lambda d: d['counterfactual'].update(basis=[]),
        ):
            with self.subTest(mutation=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess('reference-strategy', data)
        with self.assertRaises(ValueError):
            lab.assess('unknown', example())


if __name__ == '__main__':
    unittest.main()
