from copy import deepcopy
import unittest

from command_center import lab_fallout_playstyles as lab


def sample():
    return deepcopy(lab.EXERCISES[0]['example'])


def assess(data):
    return lab.assess('fallout-playstyles', data)


def failed(data):
    return {row['id'] for row in assess(data) if row['status'] == 'fail'}


def option(name, rank=0, minutes=3, supplies=-1):
    return dict(id=name, skill='quiet', rank=rank, minutes=minutes, supplies=supplies, standing=0, need=0)


class FalloutPlaystyleTests(unittest.TestCase):
    def test_example_matches_all_published_criteria_without_mutation(self):
        data = sample()
        original = deepcopy(data)
        checks = assess(data)
        self.assertEqual([r['id'] for r in checks], [r['id'] for r in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in checks))
        self.assertEqual(checks, assess(data))
        self.assertEqual(data, original)

    def test_unselected_detours_make_one_half_of_hybrid_redundant(self):
        data = sample()
        data['stops'][0].append(option('marked_detour'))
        data['stops'][2].append(option('home_detour'))
        self.assertEqual(failed(data), {'investments'})

    def test_unselected_superior_result_invalidates_fast_claim_but_tie_is_allowed(self):
        data = sample()
        extra = dict(data['stops'][0][0], id='short_exhibition')
        data['stops'][0].append(extra)
        self.assertEqual(failed(data), set())
        extra['supplies'] += 1
        self.assertEqual(failed(data), {'tradeoffs'})

    def test_budget_and_signature_rules_require_different_specialists_and_balanced_hybrid(self):
        for build, ranks in [('fast', {'contest': 3, 'craft': 2}), ('stock', {'contest': 3, 'quiet': 1}),
                             ('hybrid', {'survey': 3, 'craft': 1})]:
            with self.subTest(build=build):
                data = sample()
                data['builds'][build]['ranks'] = ranks
                self.assertTrue({'builds', 'investments'}.issubset(failed(data)))

    def test_prediction_is_recomputed_and_a_chosen_id_is_local_to_its_stop(self):
        data = sample()
        data['builds']['hybrid']['expected']['standing'] = 2
        self.assertEqual(failed(data), {'consequences'})
        data = sample()
        data['builds']['stock']['route'][1] = 'volunteer'
        routes = next(r for r in assess(data) if r['id'] == 'routes')
        self.assertEqual(routes['status'], 'fail')
        self.assertIn('stop 2', routes['detail'])

    def test_cannot_borrow_future_stock_or_future_standing(self):
        data = sample()
        data['supplies'] = 1
        data['stops'][1][0]['supplies'] = 3
        self.assertIn('fast cannot take exhibition at stop 1', next(r['detail'] for r in assess(data) if r['id'] == 'routes'))
        data = sample()
        data['stops'][0][1]['need'] = 1
        self.assertIn('stock cannot take volunteer at stop 1', next(r['detail'] for r in assess(data) if r['id'] == 'routes'))

    def test_deadline_is_inclusive_and_zero_supply_is_legal(self):
        data = sample()
        data['deadline'] = 7
        data['supplies'] -= 1
        for build in data['builds'].values():
            build['expected']['supplies'] -= 1
        self.assertEqual(failed(data), set())
        data['deadline'] -= 1
        self.assertIn('routes', failed(data))

    def test_positive_standing_must_unlock_a_selected_later_option(self):
        data = sample()
        for opt in data['stops'][2]:
            opt['need'] = 0
        self.assertEqual(failed(data), {'consequences'})

    def test_cost_search_keeps_slower_arrivals_with_required_standing(self):
        data = sample()
        alternate = dict(data['stops'][0][1], id='quick_volunteer', minutes=1, standing=0)
        data['stops'][0].append(alternate)
        self.assertEqual(failed(data), set())
        data['builds']['stock']['route'][0] = 'quick_volunteer'
        self.assertIn('stock cannot take guest_lift at stop 3', next(r['detail'] for r in assess(data) if r['id'] == 'routes'))

    def test_bounds_types_and_shape_fail_early(self):
        for edit in [
            lambda d: d.update(deadline=True),
            lambda d: d['stops'].extend(d['stops'] * 2),
            lambda d: d['stops'][0].append(d['stops'][0][0]),
            lambda d: d['stops'][0][0].update(standing=3),
            lambda d: d['stops'][0][0].update(skill=['contest']),
            lambda d: d['stops'][0][0].update(path='skip'),
            lambda d: d['builds']['hybrid'].update(ranks={'survey': False}),
            lambda d: d['builds']['hybrid']['route'].pop(),
            lambda d: d['builds']['fast']['expected'].update(supplies=31),
        ]:
            with self.subTest(edit=edit):
                data = sample()
                edit(data)
                with self.assertRaises(ValueError):
                    assess(data)
        with self.assertRaises(ValueError):
            lab.assess('another-exercise', sample())
