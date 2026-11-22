from copy import deepcopy
import unittest

from command_center import lab_reference_worlds as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def failed(data):
    return {row['id'] for row in lab.assess('reference-worlds', data) if row['status'] == 'fail'}


class ReferenceWorldsTests(unittest.TestCase):
    def test_teaching_fixture_is_deterministic_and_matches_rubric(self):
        data = example()
        original = deepcopy(data)
        result = lab.assess('reference-worlds', data)
        self.assertEqual([r['id'] for r in result], [c['id'] for c in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in result))
        self.assertEqual(result, lab.assess('reference-worlds', data))
        self.assertEqual(original, data)

    def test_residents_need_gapless_repeating_moving_itineraries(self):
        for stops in ([[1, 4, 'tower'], [4, 8, 'press']], [[0, 2, 'tower'], [3, 8, 'press']],
                      [[0, 4, 'tower'], [3, 8, 'press']], [[0, 4, 'tower'], [4, 7, 'press']],
                      [[0, 4, 'tower'], [4, 9, 'press']], [[0, 4, 'tower'], [4, 8, 'tower']],
                      [[0, 4, 'tower'], [4, 4, 'press'], [4, 8, 'landing']]):
            with self.subTest(stops=stops):
                data = example()
                data['schedules']['reader'] = stops
                self.assertEqual(len(failed(data)), len(lab.EXERCISES[0]['criteria']))

    def test_new_stop_applies_on_boundary_and_repeats(self):
        data = example()
        data['trace'][11]['present'].clear()  # Shift two, phase three, reader has just reached the press.
        self.assertEqual(failed(data), {'encounters'})
        data = example()
        for phase in (1, 6):
            for tick in (phase, phase + data['period']):
                with self.subTest(tick=tick):
                    bad = deepcopy(data)
                    bad['trace'][tick]['present'] = ['invented']
                    self.assertIn('encounters', failed(bad))
        data['trace'][0]['present'] *= 2
        self.assertEqual(failed(data), {'encounters'})

    def test_two_residents_sharing_a_stop_can_be_reported_in_either_order(self):
        data = example()
        data['schedules']['apprentice'] = deepcopy(data['schedules']['reader'])
        for row in data['trace']:
            if 'reader' in row['present']:
                row['present'] = ['reader', 'apprentice']
        self.assertFalse(failed(data))
        for row in data['trace']:
            row['present'].reverse()
        self.assertFalse(failed(data))

    def test_world_response_uses_witnesses_saturation_and_real_cooldown(self):
        for tick, change in [(3, {'result': 'noticed'}), (5, {'attention': 0}), (7, {'attention': 1}),
                             (12, {'attention': 0}), (13, {'attention': 1})]:
            with self.subTest(tick=tick):
                data = example()
                data['trace'][tick].update(change)
                self.assertIn('public-response', failed(data))
        data = example()
        data['trace'][3].update(action='wait', result='quiet')
        self.assertEqual(failed(data), {'public-response'})  # Every remaining ring was witnessed.
        data = example()
        data['trace'][5].update(action='wait', result='quiet', attention=0)
        data['trace'][6]['attention'] = 1  # Reaches two but never rings at two.
        self.assertEqual(failed(data), {'public-response'})
        data = example()
        data['trace'][10].update(action='wait', attention=0, result='quiet')
        data['trace'][11].update(action='wait', attention=0, result='quiet')
        data['trace'][12]['attention'] = 0  # The boundary reset is the only remaining drop to zero.
        self.assertEqual(failed(data), {'public-response'})

    def test_busy_service_then_last_tick_of_cooldown_and_known_expiry(self):
        data = example()
        data['trace'][12].update(site='press', action='stamp', present=['reader'], result='denied')
        data['trace'][13].update(action='stamp', permit=True, result='issued')
        self.assertFalse(failed(data))
        data['trace'][12]['result'] = 'issued'
        self.assertEqual(failed(data), {'service'})
        data = example()
        data['trace'][14].update(site='tower', present=['clerk'], result='denied', permit=False)
        data['trace'][15]['permit'] = False
        self.assertEqual(failed(data), {'service'})  # Offsite denial is correct, second-shift service still missing.
        data = example()
        data['trace'][8]['known'] = False
        self.assertEqual(failed(data), {'knowledge', 'rollover'})

    def test_lesson_requires_guide_presence_and_updated_calm_state(self):
        data = example()
        data['trace'][12].update(site='press', action='listen', present=['reader'], result='missed')
        data['trace'][13].update(action='listen', result='lesson')
        self.assertFalse(failed(data))
        data['trace'][12]['result'] = 'lesson'
        self.assertEqual(failed(data), {'encounters'})
        data = example()
        data['trace'][9]['result'] = 'lesson'
        self.assertEqual(failed(data), {'encounters'})

    def test_reset_is_before_action_and_exposes_ownership_on_both_sides(self):
        for tick, field, value, lane in [(7, 'permit', False, 'service'), (8, 'permit', True, 'service'),
                                          (7, 'attention', 1, 'public-response'),
                                          (8, 'attention', 1, 'public-response')]:
            with self.subTest(tick=tick, field=field):
                data = example()
                data['trace'][tick][field] = value
                self.assertEqual(failed(data), {lane, 'rollover'})
        data = example()
        data['trace'][8].update(site='landing', action='ring', present=[], result='unheard')
        self.assertEqual(failed(data), {'rollover'})  # First action explicitly needs to expose the quiet reset.

    def test_rejects_wrong_types_unknown_places_unbounded_inputs(self):
        for change in (
            lambda d: d.update(period=True), lambda d: d.update(period=17),
            lambda d: d.update(office='remote'), lambda d: d.update(guide='ghost'),
            lambda d: d['sites'].append('press'), lambda d: d['sites'].append({}),
            lambda d: d.update(schedules=[]), lambda d: d['schedules']['clerk'][0].append(3),
            lambda d: d['schedules']['clerk'][0].__setitem__(2, 'unknown'),
            lambda d: d['schedules']['clerk'][0].__setitem__(1, 2.0),
            lambda d: d['trace'].pop(), lambda d: d['trace'][0].update(known=1),
            lambda d: d['trace'][0].update(permit='false'), lambda d: d['trace'][0].update(attention=True),
            lambda d: d['trace'][0].update(action='teleport'), lambda d: d['trace'][0].update(result=[]),
            lambda d: d['trace'][0].update(present=['clerk'] * 5), lambda d: d.update(typo=True),
        ):
            with self.subTest(change=change):
                data = example()
                change(data)
                with self.assertRaises(ValueError):
                    lab.assess('reference-worlds', data)
        for key, value in [('other', {}), ('reference-worlds', None)]:
            with self.assertRaises(ValueError):
                lab.assess(key, value)
