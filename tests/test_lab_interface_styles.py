from copy import deepcopy
import unittest

from command_center import lab_interface_styles as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def failed(data):
    return {r['id'] for r in lab.assess('interface-styles', data) if r['status'] == 'fail'}


class InterfaceStylesTests(unittest.TestCase):
    def test_example_matches_published_criteria_and_is_repeatable(self):
        data = example()
        rows = lab.assess(lab.TRACK['id'], data)
        self.assertEqual([r['id'] for r in rows], [r['id'] for r in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in rows))
        self.assertEqual(rows, lab.assess(lab.TRACK['id'], data))
        self.assertEqual(data, example())

    def test_structural_differences_survive_a_shared_palette(self):
        data = example()
        dial, chart = data['profiles'].values()
        chart['palette'] = deepcopy(dial['palette'])
        self.assertEqual(failed(data), set())
        for card, field, value in [(dial['cards']['backup'], 'mount', 'instrument'),
                                   (chart['cards']['charge'], 'rect', [56, 479, 230, 56]),
                                   (dial['cards']['charge'], 'rect', [247, 94, 180, 46])]:
            old = card[field]
            card[field] = value
            self.assertEqual(failed(data), {'composition'})
            card[field] = old
        dial['states']['obscured'] = ['alert']
        self.assertEqual(failed(data), {'composition'})
        dial['states']['obscured'] = ['backup']
        chart['states']['critical'].remove('route')
        self.assertEqual(failed(data), {'composition'})

    def test_handheld_safe_edges_and_text_advance(self):
        data = example()
        card = data['profiles']['dial']['cards']['backup']
        # The 23px alert advances 14px per character. Vent needed has eleven characters.
        card['rect'] = [32, 24, 170, 39]
        self.assertEqual(failed(data), set())
        for rect in ([31, 24, 170, 39], [32, 23, 170, 39], [32, 24, 169, 39], [32, 24, 170, 38],
                     [1079, 24, 170, 39], [32, 658, 170, 39]):
            with self.subTest(rect=rect):
                card['rect'] = rect
                self.assertEqual(failed(data), {'fit'})

    def test_collision_only_between_simultaneously_visible_cards(self):
        data = example()
        cards = data['profiles']['chart']['cards']
        # The alert replaces the queue. Both can occupy the same space.
        cards['alert']['rect'] = [602, 520, 212, 56]
        self.assertEqual(failed(data), set())
        cards['route']['rect'] = [286, 520, 250, 56]
        self.assertEqual(failed(data), set())
        cards['route']['rect'][0] -= 1
        self.assertEqual(failed(data), {'fit'})

    def test_fallback_hierarchy_swatch_thresholds_and_shared_warning_meaning(self):
        for role in ('alert', 'backup'):
            data = example()
            data['profiles']['dial']['cards'][role]['glyph_px'] = 20
            self.assertEqual(failed(data), {'hierarchy'})
        data = example()
        data['profiles']['chart']['cards']['queue']['glyph_px'] = 21
        self.assertEqual(failed(data), {'hierarchy'})
        for field, value in (('text', '#747474'), ('focus', '#595959')):
            data = example()
            data['profiles']['chart']['palette'].update(plate='#000000')
            data['profiles']['chart']['palette'][field] = value
            self.assertEqual(failed(data), {'hierarchy'})
        data = example()
        data['labels']['alert'] = 'Orange'
        self.assertEqual(failed(data), {'hierarchy'})
        data['labels']['alert'] = 'Heat critical'
        data['alert_symbol'] = 'none'
        self.assertEqual(failed(data), {'hierarchy'})

    def test_picker_geometry_and_actual_declared_order_both_matter(self):
        data = example()
        dial = data['profiles']['dial']
        dial['cards']['exit']['rect'][0] = 640
        self.assertEqual(failed(data), {'picker-order'})
        data = example()
        data['profiles']['dial']['order'] = ['dial', 'exit', 'chart']
        self.assertEqual(failed(data), {'picker-order', 'preview', 'reduced-motion'})
        data = example()
        data['profiles']['dial']['states']['picker'].remove('chart')
        self.assertEqual(failed(data), {'composition', 'picker-order', 'preview', 'reduced-motion'})

    def test_cancel_restores_opener_and_applied_style_survives_reopening(self):
        for index, component, wrong in [(3, 1, 'chart'), (3, 2, 'dial'), (6, 2, 'dial'), (9, 2, 'dial')]:
            with self.subTest(index=index, component=component):
                data = example()
                data['traces']['standard'][index]['after'][component] = wrong
                self.assertEqual(failed(data), {'preview'})
        data = example()
        data['traces']['standard'][7]['key'] = 'up'  # chart picker is horizontal
        self.assertEqual(failed(data), {'preview'})
        data = example()
        del data['traces']['standard'][9:]
        self.assertEqual(failed(data), {'preview'})  # a correct open/close return alone skips verification

    def test_animation_half_open_interval_and_zero_delay_reduced_motion(self):
        data = example()
        data['traces']['standard'][5]['dt_ms'] = 179
        self.assertEqual(failed(data), {'preview'})
        data['traces']['standard'][5]['dt_ms'] = 180
        self.assertEqual(failed(data), set())
        data['traces']['standard'][3]['dt_ms'] = 180
        self.assertEqual(failed(data), {'preview'})  # canceled after the motion stopped
        data = example()
        data['traces']['reduced'][3]['dt_ms'] = 1
        self.assertEqual(failed(data), {'reduced-motion'})
        data = example()
        data['motion_ms']['reduced'] = 1
        self.assertEqual(failed(data), {'reduced-motion'})

    def test_invalid_shape_and_unknown_values_do_not_enter_simulation(self):
        for mutate in (
            lambda d: d.update(extra=True),
            lambda d: d['labels'].update(alert='a' * 33),
            lambda d: d['profiles']['dial']['cards'].pop('backup'),
            lambda d: d['profiles']['dial']['cards']['dial'].update(rect=[0, 0, 10]),
            lambda d: d['profiles']['dial']['cards']['dial'].update(glyph_px=True),
            lambda d: d['profiles']['dial']['cards']['dial'].update(mount=[]),
            lambda d: d['profiles']['dial']['palette'].update(text='#fff0'),
            lambda d: d['profiles']['dial']['states']['critical'].append('unlisted'),
            lambda d: d['traces']['standard'][0].update(dt_ms=-1),
            lambda d: d['traces']['standard'][0].update(after=['play', 'dial', 'none', 1]),
            lambda d: d['traces']['standard'][0].update(key='tap'),
            lambda d: d['traces'].update(standard=d['traces']['standard'] * 4),
        ):
            with self.subTest(mutate=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess('interface-styles', data)
        with self.assertRaises(ValueError):
            lab.assess('hud-excellence', example())
