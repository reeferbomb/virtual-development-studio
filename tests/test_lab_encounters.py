"""Offline academy checks for the garden-sprite encounter fixture."""

from copy import deepcopy
import unittest

from command_center.lab_encounters import EXERCISES, TRACK, assess


EXERCISE = 'ai-encounters'


def example():
    return deepcopy(EXERCISES[0]['example'])


def results(submission):
    return {row['id']: row for row in assess(EXERCISE, submission)}


class EncounterLabTests(unittest.TestCase):
    def test_track_example_is_repeatable_and_keeps_inputs(self):
        self.assertEqual(TRACK['id'], EXERCISE)
        self.assertEqual(TRACK['roles'], ['architecture', 'gameplay', 'content', 'verification'])
        self.assertEqual([item['id'] for item in EXERCISES], [EXERCISE])
        data = example()
        checks = assess(EXERCISE, data)
        self.assertEqual([row['id'] for row in checks], [c['id'] for c in EXERCISES[0]['criteria']])
        self.assertTrue(all(row['status'] == 'pass' and row['detail'] for row in checks))
        self.assertEqual(checks, assess(EXERCISE, data))
        self.assertEqual(data, example())

    def test_checks_every_gate_even_if_seed_never_selects_isolated_one(self):
        data = example()
        data['arena'][0] = 'G#..P..'
        data['arena'][1] = '###.#..'
        for spawn in data['spawns']:
            spawn['gate'] = 1
        data['spawns'] = data['spawns'][:1]
        self.assertEqual(results(data)['routes']['status'], 'fail')

    def test_near_or_visible_gates_fail_even_when_reachable(self):
        data = example()
        data['arena'][0] = '..G.P..'
        self.assertEqual(results(data)['routes']['status'], 'fail')
        data['arena'][0] = '.G..P..'  # Meets the three-step distance but is in sight.
        self.assertEqual(results(data)['routes']['status'], 'fail')

    def test_wall_occludes_even_when_player_and_sprite_are_in_same_row(self):
        data = example()
        data['arena'][0] = 'G...P#.'
        checks = results(data)
        self.assertEqual(checks['behavior']['status'], 'fail')
        self.assertEqual(checks['replay']['status'], 'fail')

    def test_overlap_counts_active_reservations_and_expires_at_boundary(self):
        data = example()
        self.assertEqual(results(data)['budget']['status'], 'pass')
        data['spawns'][1]['life'] += 1  # Still active when the third sprite enters.
        data['peak'] = 6
        check = results(data)['budget']
        self.assertEqual(check['status'], 'fail')
        self.assertIn('6', check['detail'])
        self.assertEqual(results(data)['replay']['status'], 'pass')

    def test_serial_spawns_and_unreleased_budget_do_not_demonstrate_reuse(self):
        data = example()
        data['spawns'][1]['tick'] = 20
        data['spawns'][2]['tick'] = 24
        data['peak'] = 2
        self.assertEqual(results(data)['budget']['status'], 'fail')
        data = example()
        data['spawns'].pop()
        self.assertEqual(results(data)['budget']['status'], 'fail')

    def test_seed_selects_real_gate_and_untrusted_predictions_do_not_drive_replay(self):
        data = example()
        data['seed'] = 2
        self.assertEqual(results(data)['replay']['status'], 'fail')
        data = example()
        data['spawns'][1]['gate'] ^= 1
        self.assertEqual(results(data)['replay']['status'], 'fail')
        data = example()
        data['steps'][3]['state'] = 'tag'
        self.assertEqual(results(data)['behavior']['status'], 'pass')
        self.assertEqual(results(data)['replay']['status'], 'fail')
        data = example()
        data['peak'] = 3
        self.assertEqual(results(data)['replay']['status'], 'fail')

    def test_independent_seed_can_start_from_other_gate_with_correct_predictions(self):
        data = example()
        data['seed'] = 2
        for spawn, gate in zip(data['spawns'], [0, 0, 1], strict=True):
            spawn['gate'] = gate
        data['steps'] = [dict(cell=cell, interrupt=interrupt, state=state)
                         for cell, interrupt, state in [
                             ([0, 0], False, 'ready'), ([1, 0], False, 'signal'),
                             ([0, 0], False, 'ready'), ([1, 0], False, 'signal'),
                             ([1, 0], True, 'recover'), ([1, 0], False, 'ready'),
                             ([1, 0], False, 'signal'), ([1, 0], False, 'tag'),
                             ([1, 0], False, 'recover'), ([1, 0], False, 'ready')]]
        self.assertTrue(all(row['status'] == 'pass' for row in results(data).values()))

    def test_full_tag_recovery_must_return_to_ready_after_the_tag(self):
        data = example()
        data['steps'].pop()
        self.assertEqual(results(data)['replay']['status'], 'pass')
        self.assertEqual(results(data)['behavior']['status'], 'fail')

    def test_hidden_gate_still_needs_three_walkable_moves(self):
        data = example()
        data['arena'][0] = '....P..'
        data['arena'][1] = '.##G#..'
        self.assertEqual(results(data)['routes']['status'], 'fail')

    def test_equal_tick_spawns_accumulate_in_declaration_order(self):
        data = example()
        data['spawns'][1]['tick'] = 0
        checks = results(data)
        self.assertEqual(checks['budget']['status'], 'pass')
        self.assertIn('at tick 0', checks['budget']['detail'])
        self.assertEqual(checks['replay']['status'], 'pass')

    def test_claimed_states_cannot_replace_interrupts_or_valid_motion(self):
        data = example()
        next(step for step in data['steps'] if step['interrupt'])['interrupt'] = False
        self.assertEqual(results(data)['behavior']['status'], 'fail')
        data = example()
        del data['steps'][1:3]  # Teleport directly from the gate to the signal.
        self.assertEqual(results(data)['replay']['status'], 'fail')
        data = example()
        data['steps'][1]['cell'] = [4, 1]  # Wall tile.
        self.assertEqual(results(data)['replay']['status'], 'fail')
        data = example()
        data['spawns'][0]['life'] = len(data['steps']) - 1
        self.assertEqual(results(data)['replay']['status'], 'fail')

    def test_malformed_and_out_of_bounds_inputs_raise_value_error(self):
        for mutate in [
            lambda s: s.update(seed=True), lambda s: s.update(seed=2147483647),
            lambda s: s.update(extra='x'), lambda s: s.update(arena=['G.P', 'G.']),
            lambda s: s.update(arena=['G.P', 'G.P']), lambda s: s.update(arena=['G.PX', '.G..']),
            lambda s: s.update(arena=['G.P', '...']), lambda s: s.update(arena=['G.P'] * 13),
            lambda s: s.update(spawns=[]), lambda s: s.update(spawns=s['spawns'] * 12),
            lambda s: s['spawns'][0].update(gate=True), lambda s: s['spawns'][0].update(gate=2),
            lambda s: s['spawns'][0].update(cost=0), lambda s: s['spawns'][0].update(life=65),
            lambda s: s['spawns'][0].update(tick=1), lambda s: s['spawns'][2].update(tick=0),
            lambda s: s.update(steps=s['steps'] * 3), lambda s: s.update(steps=[]),
            lambda s: s['steps'][0].update(state=[]), lambda s: s['steps'][0].update(cell=[True, 0]),
            lambda s: s['steps'][0].update(cell=[-1, 0]), lambda s: s['steps'][0].update(cell=[7, 3]),
            lambda s: s['steps'][0].update(interrupt=1), lambda s: s['steps'][0].update(extra=0),
            lambda s: s.update(peak=True), lambda s: s.update(peak=129),
        ]:
            data = example()
            mutate(data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                assess(EXERCISE, data)
        for track in ('unknown', [], None):
            with self.assertRaises(ValueError):
                assess(track, {})
