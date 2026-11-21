from copy import deepcopy
import unittest

from command_center import lab_replayability as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def failed(data):
    return {row['id'] for row in lab.assess('replayability', data) if row['status'] == 'fail'}


class ReplayabilityLabTests(unittest.TestCase):
    def test_example_is_deterministic_complete_and_preserves_input(self):
        data = example()
        original = deepcopy(data)
        result = lab.assess('replayability', data)
        self.assertEqual(data, original)
        self.assertEqual(result, lab.assess('replayability', data))
        self.assertEqual([row['id'] for row in result], [c['id'] for c in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(row['status'] == 'pass' and row['detail'] for row in result))
        data['runs'].reverse()
        for leg in data['legs']:
            leg.reverse()
        self.assertEqual(failed(data), set())

    def test_intermediate_efficient_strategy_is_viable(self):
        data = example()
        data['runs'][1] = {'route': ['reed_hide', 'shoreline', 'stairs'], 'minutes': 13, 'observations': 9}
        self.assertEqual(failed(data), set())

    def test_recomputes_route_outcomes_instead_of_believing_claims(self):
        for key in ('minutes', 'observations'):
            with self.subTest(key=key):
                data = example()
                data['runs'][0][key] += 1
                self.assertEqual(failed(data), {'predictions'})

    def test_unlocked_and_on_time_from_first_visit(self):
        data = example()
        data['legs'][0][1]['prior_finishes'] = 1
        self.assertEqual(failed(data), {'fresh-runs', 'viable-tradeoff'})
        data = example()
        data['deadline'] -= 1
        self.assertEqual(failed(data), {'fresh-runs', 'viable-tradeoff'})
        data['deadline'] = 1
        checks = lab.assess('replayability', data)
        self.assertIn('0 feasible itineraries', checks[3]['detail'])
        self.assertEqual(failed(data), {'fresh-runs', 'viable-tradeoff'})

    def test_cosmetic_options_and_identical_runs_do_not_demonstrate_variety(self):
        data = example()
        data['runs'][0] = deepcopy(data['runs'][1])
        self.assertEqual(failed(data), {'decision-variety', 'viable-tradeoff'})
        data = example()
        for leg in data['legs']:
            leg[1].update(minutes=leg[0]['minutes'], observations=leg[0]['observations'])
        data['runs'][1].update(minutes=7, observations=3)
        self.assertEqual(failed(data), {'decision-variety', 'viable-tradeoff'})

    def test_one_changed_decision_does_not_establish_two_distinct_strategies(self):
        data = example()
        data['runs'][1] = {'route': ['reed_hide', 'crossing', 'stairs'], 'minutes': 10, 'observations': 6}
        self.assertEqual(failed(data), {'decision-variety'})

    def test_a_third_unsubmitted_route_can_dominate(self):
        for minutes, observations in ((1, 1), (2, 2), (1, 2)):
            with self.subTest(minutes=minutes, observations=observations):
                data = example()
                data['legs'][0].append({'id': 'shortcut', 'minutes': minutes,
                                        'observations': observations, 'prior_finishes': 0})
                self.assertEqual(failed(data), {'viable-tradeoff'})
                self.assertIn('Run 1 is beaten by shortcut / crossing / stairs',
                              lab.assess('replayability', data)[3]['detail'])

    def test_locked_late_and_tied_alternatives_do_not_dominate(self):
        for minutes, observations, threshold in ((1, 20, 1), (45, 20, 0), (2, 1, 0)):
            with self.subTest(minutes=minutes):
                data = example()
                data['legs'][0].append({'id': 'alternative', 'minutes': minutes,
                                        'observations': observations, 'prior_finishes': threshold})
                self.assertEqual(failed(data), set())

    def test_no_strict_tradeoff_when_faster_also_discovers_as_much(self):
        data = example()
        for leg in data['legs']:
            leg[1]['observations'] = leg[0]['observations']
        data['runs'][1]['observations'] = data['runs'][0]['observations']
        self.assertEqual(failed(data), {'viable-tradeoff'})

    def test_quitting_cannot_cost_progress_or_require_another_run(self):
        for key, value in (('bank_on', 'replay'), ('restart', 'automatic'), ('quit_cost', 1)):
            with self.subTest(key=key):
                data = example()
                data['finish'][key] = value
                self.assertEqual(failed(data), {'clean-stop'})

    def test_local_ids_may_repeat_across_legs(self):
        data = example()
        data['legs'][1][0]['id'] = 'boardwalk'
        data['runs'][0]['route'][1] = 'boardwalk'
        self.assertEqual(failed(data), set())

    def test_entire_largest_first_visit_choice_space_is_compared(self):
        data = example()
        options = [{'id': f'pace_{n}', 'minutes': n, 'observations': n, 'prior_finishes': 0}
                   for n in range(1, 5)]
        data.update(deadline=20, legs=[deepcopy(options) for _ in range(5)], runs=[
            {'route': [f'pace_{n}'] * 5, 'minutes': n * 5, 'observations': n * 5} for n in (1, 4)])
        self.assertEqual(failed(data), set())
        self.assertIn('1024 feasible itineraries', lab.assess('replayability', data)[3]['detail'])

    def test_malformed_submissions_are_rejected(self):
        for mutate in (
            lambda d: d.update(deadline=True), lambda d: d.update(legs=[]),
            lambda d: d.update(finish=None), lambda d: d['legs'][1].clear(),
            lambda d: d['legs'][0].extend(d['legs'][0] * 2),
            lambda d: d['legs'][0][0].update(id='BAD'), lambda d: d['legs'][0][1].update(id='boardwalk'),
            lambda d: d['legs'][0][0].update(prior_finishes=-1),
            lambda d: d['legs'][0][0].update(minutes=0), lambda d: d['legs'][0][0].update(observations=3.5),
            lambda d: d['runs'][0]['route'].pop(), lambda d: d['runs'][0]['route'].__setitem__(0, 'missing'),
            lambda d: d['runs'][1].update(observations=False), lambda d: d['runs'][1].update(minutes=226),
            lambda d: d['runs'].append(deepcopy(d['runs'][0])),
            lambda d: d['finish'].update(restart='maybe'), lambda d: d['finish'].update(bank_on=[]),
            lambda d: d['finish'].update(quit_cost=True), lambda d: d.update(unexpected=True),
        ):
            with self.subTest(mutation=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess('replayability', data)
        for key, value in (('unknown', {}), ('replayability', None), ('replayability', [])):
            with self.assertRaises(ValueError):
                lab.assess(key, value)


if __name__ == '__main__':
    unittest.main()
