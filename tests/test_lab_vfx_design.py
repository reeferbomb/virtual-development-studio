from copy import deepcopy
import unittest

from command_center import lab_vfx_design as vfx


def example():
    return deepcopy(vfx.EXERCISES[0]['example'])


def failed(data):
    return {c['id'] for c in vfx.assess('vfx-design', data) if c['status'] == 'fail'}


class VfxDesignTests(unittest.TestCase):
    def test_example_replays_and_measures_profiles(self):
        data = example()
        original = deepcopy(data)
        rows = vfx.assess('vfx-design', data)
        self.assertEqual([r['id'] for r in rows], [c['id'] for c in vfx.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in rows))
        data['layers'].reverse()
        self.assertEqual(vfx.assess('vfx-design', data), rows)
        data['layers'].reverse()
        self.assertEqual(data, original)

    def test_signals_cover_the_exact_event_window_and_survive_low_and_reduced(self):
        for key, value in [('offset', -4), ('emit', 4), ('low', None), ('reduced', 'off'),
                           ('form', 'particles'), ('form', 'glyph')]:
            with self.subTest(key=key):
                data = example()
                data['layers'][0][key] = value
                self.assertIn('cue-timing', failed(data))
        data = example()
        data['layers'][1]['offset'] = -1
        self.assertIn('cue-timing', failed(data))

    def test_other_bursts_cannot_supply_the_missing_event_local_warning(self):
        data = example()
        data['contacts'] = [8, 9, 10]
        # Combined warning geometry still covers the union of desired frames;
        # each individual event, however, has an uncovered middle frame.
        lead = data['layers'][0]
        lead.update(emit=1)
        tail = deepcopy(lead)
        tail.update(id='rim_end', offset=-1)
        data['layers'].append(tail)
        self.assertIn('cue-timing', failed(data))

    def test_cover_from_an_earlier_event_can_hide_the_following_warning(self):
        data = example()
        cover = vfx._layer('front_panel', 'detail', 'cover', 2, 1, 1, 1, 1, None, 0, 'still', 'off')
        data['layers'].append(cover)
        self.assertNotIn('visibility', failed(data))
        cover['offset'] = 3
        self.assertIn('visibility', failed(data))
        cover['form'] = 'decal'
        self.assertNotIn('visibility', failed(data))

    def test_accessibility_mode_uses_stable_alternative_or_omission(self):
        data = example()
        data['layers'][2]['standard'] = 'shake'
        self.assertFalse(failed(data))
        for style in ('flash', 'shake', 'motion'):
            with self.subTest(style=style):
                data['layers'][2]['reduced'] = style
                self.assertIn('reduced-motion', failed(data))
        data['layers'][2]['reduced'] = 'still'
        self.assertNotIn('reduced-motion', failed(data))
        self.assertIn('peak-predictions', failed(data))

    def test_particles_persist_after_stop_and_pool_reuse_is_half_open(self):
        data = example()
        spray = data['layers'][2]
        self.assertEqual((spray['emit'], spray['life'], spray['release'], spray['pool']), (2, 5, 6, 1))
        spray['release'] = 5
        self.assertIn('pool-cleanup', failed(data))
        spray['release'] = 7
        self.assertIn('pool-cleanup', failed(data))
        spray['pool'] = 2
        self.assertNotIn('pool-cleanup', failed(data))
        data['frames'] = 25
        self.assertIn('pool-cleanup', failed(data))

    def test_peaks_use_actual_particle_cohorts_for_each_quality_and_mode(self):
        data = example()
        # Two births per burst, three particles per birth. The three bursts now overlap by a frame.
        data['contacts'] = [8, 9]
        data['layers'] = data['layers'][:3]
        for layer in data['layers']:
            layer['pool'] = 2
        result = vfx._simulate(data, 'high', 'standard')
        self.assertEqual(result['peaks'][0], 12)
        self.assertEqual(vfx._simulate(data, 'low', 'standard')['peaks'][0], 4)
        for tier in ('high', 'low'):
            self.assertEqual(vfx._simulate(data, tier, 'reduced')['peaks'][0], 0)
        spray = data['layers'][2]
        spray['life'] = 1
        self.assertEqual(vfx._simulate(data, 'high', 'standard')['peaks'][0], 6)
        spray['life'] = 5
        spray['pool'] = 1
        self.assertEqual(vfx._simulate(data, 'high', 'standard')['peaks'][0], 12)
        self.assertIn('pool-cleanup', failed(data))

    def test_correct_predictions_can_exceed_budgets(self):
        data = example()
        data['layers'][3]['high'] = 32
        result = vfx._simulate(data, 'high', 'standard')
        self.assertEqual(result['peaks'], [102, 4])
        data['peaks']['high']['standard'] = result['peaks']
        self.assertEqual(failed(data), {'quality-budgets'})
        # Instance demand has a separate cap, even on static geometry without particles.
        data = example()
        for i in range(6):
            layer = deepcopy(data['layers'][1])
            layer.update(id=f'trim_{i}', role='detail')
            data['layers'].append(layer)
        self.assertIn('quality-budgets', failed(data))

    def test_zero_rate_still_has_geometry_and_reserved_slots(self):
        data = example()
        rim = data['layers'][0]
        self.assertEqual(rim['low'], 0)
        rim['life'] = 60  # no particles were emitted, so no tail is owed
        self.assertFalse(failed(data))
        rim['low'] = None
        self.assertIn('cue-timing', failed(data))
        data = example()
        for mode in data['peaks']['low']:
            data['peaks']['low'][mode][1] = 0
        self.assertEqual(failed(data), {'peak-predictions'})

    def test_invalid_data_stays_outside_the_simulator(self):
        for mutate in (lambda d: d.update(frames=True), lambda d: d.update(lead=0),
                       lambda d: d.update(contacts=[4, 4]), lambda d: d.update(contacts=[13, 7]),
                       lambda d: d.update(contacts=[4, 32]), lambda d: d.update(layers=d['layers'] * 4),
                       lambda d: d['layers'][1].update(id='rim'), lambda d: d['layers'][1].update(high=-1),
                       lambda d: d['layers'][1].update(low=False), lambda d: d['layers'][1].update(release=0),
                       lambda d: d['layers'][0].update(pool=99), lambda d: d['layers'][0].update(role=[]),
                       lambda d: d['layers'][2].update(standard='off'), lambda d: d['layers'][2].update(extra=False),
                       lambda d: d['peaks']['low'].update(reduced=[0.5, 2])):
            with self.subTest(mutate=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    vfx.assess('vfx-design', data)
        with self.assertRaises(ValueError):
            vfx.assess('missing', example())


if __name__ == '__main__':
    unittest.main()
