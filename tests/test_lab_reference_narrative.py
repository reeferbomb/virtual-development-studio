from copy import deepcopy
import unittest

from command_center import lab_reference_narrative as narrative


def sample():
    return deepcopy(narrative.EXERCISES[0]['example'])


def assess(data):
    return narrative.assess('reference-narrative', data)


def failed(data):
    return {row['id'] for row in assess(data) if row['status'] == 'fail'}


class NarrativeReferenceTests(unittest.TestCase):
    def test_teaching_example_is_repeatable_and_matches_published_criteria(self):
        data = sample()
        original = deepcopy(data)
        result = assess(data)
        self.assertEqual([r['id'] for r in result], [c['id'] for c in narrative.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in result))
        self.assertEqual(result, assess(data))
        self.assertEqual(data, original)

    def test_alternate_unplayed_branch_leaks_a_recipient_even_when_replays_match(self):
        data = sample()
        data['rooms'][0]['links'].append(dict(to='turntable', layout='low', pledge='either'))
        data['rooms'].append({'id': 'turntable', 'valve': True,
                              'links': [dict(to='pottery_dock', layout='high', pledge='either')]})
        self.assertEqual(failed(data), {'continuity'})

    def test_unplayed_bypass_removes_the_need_to_shift_even_if_replay_still_shifts(self):
        data = sample()
        data['rooms'][0]['links'].append(dict(to='bindery_dock', layout='low', pledge='bindery'))
        self.assertEqual(failed(data), {'layouts'})

    def test_ability_cannot_go_into_debt_and_must_demonstrate_each_refusal(self):
        data = sample()
        data['cost'] = 3
        self.assertEqual(failed(data), {'continuity', 'layouts', 'ability', 'handoffs', 'predictions'})
        for index in (0, 4):
            data = sample()
            for steps in data['runs'].values():
                del steps[index]
            self.assertEqual(failed(data), {'ability'})

    def test_repeat_switches_preserve_the_promise_and_charge_only_once_each(self):
        data = sample()
        data['charge'] = 6
        for steps in data['runs'].values():
            for step in steps[:3]:
                step['charge'] = 6
            steps[3]['charge'] = 4
            steps[4:4] = [
                dict(action='shift', room='gantry', layout='low', charge=2, result='shifted'),
                dict(action='shift', room='gantry', layout='high', charge=0, result='shifted'),
            ]
        self.assertEqual(failed(data), set())

    def test_link_refusals_check_existence_then_pledge_then_layout(self):
        data = sample()
        data['rooms'][0]['links'].append(dict(to='junction', layout='high', pledge='pottery'))
        for pledge, result in [('bindery', 'other_pledge'), ('pottery', 'wrong_layout')]:
            data['runs'][pledge][:0] = [
                dict(action='unmapped', room='yard', layout='low', charge=2, result='no_link'),
                dict(action='junction', room='yard', layout='low', charge=2, result=result),
            ]
        self.assertEqual(failed(data), set())

    def test_exact_trace_must_match_even_when_the_final_state_is_correct(self):
        for key, value in [('result', 'no_link'), ('charge', 0), ('layout', 'high'), ('room', 'gantry')]:
            data = sample()
            data['runs']['bindery'][0][key] = value
            self.assertEqual(failed(data), {'predictions'})
            self.assertIn('bindery step 1', assess(data)[-1]['detail'])

    def test_first_arrival_ends_the_trace(self):
        data = sample()
        data['runs']['pottery'].append(dict(action='shift', room='pottery_dock', layout='high',
                                            charge=0, result='closed'))
        self.assertEqual(failed(data), {'handoffs'})

    def test_correct_actual_actions_must_cover_layout_and_pledge_refusals(self):
        for index, expected in [(2, 'layouts'), (6, 'handoffs')]:
            data = sample()
            for steps in data['runs'].values():
                del steps[index]
            self.assertEqual(failed(data), {expected})

    def test_bounds_unique_keys_terminal_shape_and_structural_references(self):
        for change in (
            lambda d: d.update(charge=True),
            lambda d: d.update(cost=0),
            lambda d: d.update(entry='outside'),
            lambda d: d.update(entry='pottery_dock'),
            lambda d: d['docks'].update(bindery='pottery_dock'),
            lambda d: d['rooms'][-1].update(valve=True),
            lambda d: d['rooms'][0].update(id='shift'),
            lambda d: d['rooms'][0].update(valve=1),
            lambda d: d['rooms'][0]['links'][0].update(to='unknown'),
            lambda d: d['rooms'][0]['links'][0].update(pledge='outsider'),
            lambda d: d['rooms'][0]['links'].append(d['rooms'][0]['links'][0]),
            lambda d: d['runs'].update(bindery=[]),
            lambda d: d['runs'].update(bindery=d['runs']['bindery'] * 5),
            lambda d: d['runs']['bindery'][0].update(room=[]),
            lambda d: d['runs']['bindery'][0].update(result='unknown'),
            lambda d: d['runs']['bindery'][0].update(override=1),
        ):
            data = sample()
            change(data)
            with self.subTest(change=change), self.assertRaises(ValueError):
                assess(data)
        for name, data in [('unknown', sample()), ('reference-narrative', None)]:
            with self.assertRaises(ValueError):
                narrative.assess(name, data)
