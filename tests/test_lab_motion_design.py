from copy import deepcopy
import unittest

from command_center import lab_motion_design as motion


def example():
    return deepcopy(motion.EXERCISES[0]['example'])


def evaluate(data):
    return motion.assess('motion-design', data)


def failed(data):
    return {row['id'] for row in evaluate(data) if row['status'] == 'fail'}


def varying_gait():
    data = example()
    data.update(delay_frames=0, blend_pct=[50, 100])
    for row, dx, sole in zip(data['walk'], [1, 3, 2, 4], [9, 6, 5, 1]):
        row.update(dx_mm=dx, sole_mm=sole)
    for row, dx, angle in zip(data['guard'], [-4, -4, 13, 8, -1, 0], [10, 35, 60, 80, 45, 0]):
        row.update(dx_mm=dx, shield_deg=angle)
    data['takes'] = {
        'complete': {'walk_frame': 6, 'body_mm': [-2, -6, 7, 15, 14, 14, 16], 'event_frames': [2]},
        'cancel_on_marker': {'walk_frame': 2, 'body_mm': [-2, -6, -4], 'event_frames': []},
        'cancel_after_marker': {'walk_frame': 3, 'body_mm': [-2, -6, 7, 11], 'event_frames': [2]},
    }
    return data


class MotionDesignLabTests(unittest.TestCase):
    def test_fixture_is_repeatable_complete_and_does_not_change_input(self):
        data = example()
        original = deepcopy(data)
        result = evaluate(data)
        self.assertEqual([c['id'] for c in result], [c['id'] for c in motion.EXERCISES[0]['criteria']])
        self.assertTrue(all(c['status'] == 'pass' and c['detail'] for c in result))
        self.assertEqual(result, evaluate(data))
        self.assertEqual(data, original)

    def test_uninterrupted_foot_support_crosses_the_loop_seam(self):
        data = example()
        data['walk'] = data['walk'][1:] + data['walk'][:1]
        self.assertEqual(failed(data), set())
        data['walk'][-1]['sole_mm'] += 2
        self.assertEqual(failed(data), set())
        data['walk'][-1]['sole_mm'] += 1
        self.assertEqual(failed(data), {'foot-contacts'})

    def test_drift_uses_whole_stance_and_requires_both_feet_for_two_frames(self):
        data = example()
        data['walk'] = [{'dx_mm': 12, 'foot': 'left' if i < 3 else 'right', 'sole_mm': x}
                        for i, x in enumerate((20, 10, 0, 12, 0, -12))]
        self.assertEqual(failed(data), {'foot-contacts'})
        for foot in ('left', 'right'):
            data = example()
            for row in data['walk']:
                row['foot'] = foot
            self.assertEqual(failed(data), {'foot-contacts'})
        data = example()
        data['walk'][0]['foot'] = 'right'
        self.assertIn('foot-contacts', failed(data))

    def test_crossfade_is_strictly_progressive_and_completes_inside_clip(self):
        for curve in ([0, 50, 100], [20, 20, 70, 100], [30, 25, 65, 100], [10, 45, 99],
                      [70, 100], [10, 20, 30, 40, 50, 75, 100]):
            with self.subTest(curve=curve):
                data = example()
                data['blend_pct'] = curve
                self.assertIn('crossfade', failed(data))

    def test_readable_response_includes_input_delay_and_faded_pose(self):
        data = example()
        data['delay_frames'] = 2
        self.assertNotIn('response', failed(data))
        data['guard'][0]['shield_deg'] = 19  # 25% is only 4.75 degrees.
        self.assertIn('response', failed(data))
        data['guard'][0]['shield_deg'] = 20
        self.assertNotIn('response', failed(data))
        data['delay_frames'] = 3
        self.assertIn('response', failed(data))

    def test_marker_uses_blended_threshold_and_requires_one_raise_and_recovery(self):
        data = example()
        data['guard'][1]['shield_deg'] = 90  # Only 54 degrees after the fade.
        self.assertEqual(failed(data), set())
        data['marker'] = 1
        self.assertIn('event-sync', failed(data))
        data = example()
        data['guard'][3]['shield_deg'] = 20
        data['guard'][4]['shield_deg'] = 75
        self.assertEqual(failed(data), {'event-sync'})
        data = example()
        data['guard'][-1]['shield_deg'] = 60
        self.assertEqual(failed(data), {'event-sync'})

    def test_root_deltas_round_ties_away_from_zero_and_use_global_walk_phase(self):
        data = varying_gait()
        self.assertEqual(failed(data), set())
        data['guard'][0]['dx_mm'] = 4
        for take in data['takes'].values():
            take['body_mm'] = [x + 5 for x in take['body_mm']]
        self.assertEqual(failed(data), set())
        data['takes']['cancel_after_marker']['body_mm'][-1] -= 3  # Resetting the walk phase applies 1 instead of 4.
        self.assertEqual(failed(data), {'root-motion'})

    def test_every_position_is_checked_and_single_owner_must_change_motion(self):
        for take in example()['takes']:
            data = example()
            data['takes'][take]['body_mm'][1] += 12  # Offsetting a bad intermediate sample later cannot hide it.
            self.assertEqual(failed(data), {'root-motion'})
        for root_delta in (0, 12):
            data = example()
            for row in data['guard']:
                row['dx_mm'] = root_delta
            self.assertIn('root-motion', failed(data))

    def test_cancel_preempts_same_frame_event_but_preserves_earlier_events(self):
        for name, events in [('cancel_on_marker', [3]), ('cancel_after_marker', []),
                             ('cancel_after_marker', [3, 3]), ('complete', [2])]:
            with self.subTest(name=name, events=events):
                data = example()
                data['takes'][name]['event_frames'] = events
                self.assertEqual(failed(data), {'interruption'})
        for name in example()['takes']:
            data = example()
            data['takes'][name]['walk_frame'] += 1
            self.assertEqual(failed(data), {'interruption'})

    def test_terminal_or_late_markers_cannot_pass_interrupt_coverage(self):
        for marker in (5, 6, 23):
            data = example()
            data['marker'] = marker
            self.assertTrue({'event-sync', 'interruption'} <= failed(data))

    def test_malformed_shapes_types_bounds_and_names_raise_value_error(self):
        for mutate in (
            lambda d: d.update(guard=d['guard'] * 5), lambda d: d.update(walk=[]),
            lambda d: d.update(delay_frames=True), lambda d: d.update(marker=24),
            lambda d: d.update(blend_pct=[40]), lambda d: d.update(blend_pct=[50, 101]),
            lambda d: d['guard'][0].update(shield_deg=float('nan')),
            lambda d: d['walk'][0].update(dx_mm=0), lambda d: d['walk'][0].update(foot='both'),
            lambda d: d['walk'][0].update(sole_mm=3.0), lambda d: d['guard'][0].update(dx_mm=-101),
            lambda d: d['takes'].pop('cancel_after_marker'), lambda d: d['takes']['complete'].update(body_mm=[0] * 34),
            lambda d: d['takes']['complete'].update(event_frames=[False]), lambda d: d.update(unexpected=True),
        ):
            with self.subTest(mutation=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    evaluate(data)
        for key, data in [('unknown', {}), ('motion-design', None), ('motion-design', [])]:
            with self.assertRaises(ValueError):
                motion.assess(key, data)


if __name__ == '__main__':
    unittest.main()
