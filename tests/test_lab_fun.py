from copy import deepcopy
import unittest

from command_center import lab_fun


def sample():
    return deepcopy(lab_fun.EXERCISES[0]['example'])


def assess(plan):
    return lab_fun.assess('player-enjoyment', plan)


def failures(plan):
    return {row['id'] for row in assess(plan) if row['status'] == 'fail'}


def option(name, ticks, charge):
    return {'id': name, 'ticks': ticks, 'charge': charge, 'feedback': {'after_ticks': 0, 'charge': charge}}


class PlayerEnjoymentTests(unittest.TestCase):
    def test_example_is_deterministic_and_yields_every_published_criterion(self):
        plan = sample()
        original = deepcopy(plan)
        checks = assess(plan)
        self.assertEqual([row['id'] for row in checks], [c['id'] for c in lab_fun.EXERCISES[0]['criteria']])
        self.assertTrue(all(row['status'] == 'pass' and row['detail'] for row in checks))
        self.assertEqual(assess(plan), checks)
        self.assertEqual(plan, original)

    def test_one_unchosen_route_can_fit_both_budgets_without_dominating_either_choice(self):
        plan = {
            'crossings': [
                [option('sprint', 2, 9), option('coast', 10, 1), option('sail', 3, 3)],
                [option('dock', 4, 1), option('linger', 5, 2)],
            ],
            'routes': {
                'urgent': {'choices': ['sprint', 'dock'], 'ticks': 6, 'charge': 10},
                'reserve': {'choices': ['coast', 'dock'], 'ticks': 14, 'charge': 2},
            },
        }
        self.assertEqual(failures(plan), {'tradeoff'})
        detail = next(row['detail'] for row in assess(plan) if row['id'] == 'tradeoff')
        self.assertIn('2/2 chosen routes are efficient', detail)
        self.assertIn('A route fits both budgets', detail)
        plan['crossings'][0].pop()
        self.assertEqual(failures(plan), set())

    def test_dominance_from_either_dimension_and_equal_cost_ties(self):
        for ticks, charge, expected in [(1, 4, {'tradeoff'}), (2, 3, {'tradeoff'}), (2, 4, set())]:
            plan = sample()
            plan['crossings'][0].append(option('shortcut', ticks, charge))
            with self.subTest(ticks=ticks, charge=charge):
                self.assertEqual(failures(plan), expected)

    def test_two_distinct_labels_or_valid_routes_do_not_establish_the_tradeoff(self):
        plan = sample()
        plan['routes']['reserve'] = deepcopy(plan['routes']['urgent'])
        self.assertEqual(failures(plan), {'tradeoff', 'route-budgets'})
        plan = sample()
        plan['routes']['reserve'], plan['routes']['urgent'] = plan['routes']['urgent'], plan['routes']['reserve']
        self.assertEqual(failures(plan), {'tradeoff', 'route-budgets'})

    def test_budget_limits_apply_to_simulated_totals_and_include_equality(self):
        for leg, index, name, ticks, charge in [(0, 0, 'urgent', 3, 5), (2, 1, 'reserve', 6, 2)]:
            plan = sample()
            row = plan['crossings'][leg][index]
            row.update(ticks=ticks, charge=charge)
            row['feedback']['charge'] = charge
            route = plan['routes'][name]
            route['ticks'] += 1
            route['charge'] += 1
            self.assertEqual(failures(plan), set())
            row['ticks'] += 1
            self.assertIn('route-budgets', failures(plan))
            row['ticks'] -= 1
            row['charge'] += 1
            self.assertIn('route-budgets', failures(plan))

    def test_checks_receipts_on_options_unused_by_both_submitted_routes(self):
        plan = sample()
        spare = option('slow_tow', 8, 6)
        plan['crossings'][1].append(spare)
        self.assertEqual(failures(plan), set())
        spare['feedback']['after_ticks'] = 2
        self.assertEqual(failures(plan), {'feedback'})
        spare['feedback'].update(after_ticks=1, charge=0)
        self.assertEqual(failures(plan), {'feedback'})

    def test_predictions_cannot_change_simulation_and_unknown_choices_cannot_finish(self):
        for key in ('charge', 'ticks'):
            plan = sample()
            plan['routes']['urgent'][key] = 0
            self.assertEqual(failures(plan), {'prediction'})
        plan = sample()
        plan['routes']['urgent']['choices'][0] = 'lift_gate'
        self.assertEqual(failures(plan), {'tradeoff', 'route-budgets', 'prediction'})

    def test_checks_exact_shapes_references_types_and_bounds(self):
        for change in (
            lambda p: p.update(mood=10),
            lambda p: p.update(crossings=[]),
            lambda p: p.update(crossings=p['crossings'] * 3),
            lambda p: p['crossings'][0].append(deepcopy(p['crossings'][0][0])),
            lambda p: p['crossings'][0][0].update(id='unsafe/path'),
            lambda p: p['crossings'][0][0].update(ticks=True),
            lambda p: p['crossings'][0][0].update(charge=-1),
            lambda p: p['crossings'][0][0]['feedback'].update(after_ticks=1.5),
            lambda p: p['crossings'][0][0]['feedback'].update(charge=13),
            lambda p: p['crossings'][0][0].pop('feedback'),
            lambda p: p['routes'].pop('reserve'),
            lambda p: p['routes']['urgent']['choices'].pop(),
            lambda p: p['routes']['urgent']['choices'].__setitem__(0, []),
            lambda p: p['routes']['urgent'].update(ticks=97),
        ):
            plan = sample()
            change(plan)
            with self.subTest(change=change), self.assertRaises(ValueError):
                assess(plan)
        for name, plan in [('unknown', sample()), ('player-enjoyment', []), ('player-enjoyment', None)]:
            with self.assertRaises(ValueError):
                lab_fun.assess(name, plan)
