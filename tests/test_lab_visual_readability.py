from copy import deepcopy
import unittest

from command_center import lab_visual_readability as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def failed(data):
    return {row['id'] for row in lab.assess('visual-readability', data) if row['status'] == 'fail'}


class VisualReadabilityLabTests(unittest.TestCase):
    def test_example_is_replayable_and_matches_published_criteria(self):
        exercise = lab.EXERCISES[0]
        data = example()
        first = lab.assess(exercise['id'], data)
        self.assertEqual([c['id'] for c in first], [c['id'] for c in exercise['criteria']])
        self.assertTrue(all(c['status'] == 'pass' and c['detail'] for c in first))
        self.assertEqual(lab.assess(exercise['id'], data), first)
        self.assertEqual(data, exercise['example'])

    def test_relative_luminance_and_thresholds_use_unrounded_ratios(self):
        data = example()
        hud = data['hud']
        hud.update(text_color='#FFFFFF', panel_color='#000000')
        self.assertIn('21.000:1', lab.assess(lab.TRACK['id'], data)[0]['detail'])
        hud['text_color'] = '#747474'  # 4.49295:1 against black
        self.assertEqual(failed(data), {'hud-contrast'})
        hud['text_color'] = '#757575'  # 4.55777:1
        self.assertEqual(failed(data), set())
        data['cues'][-1]['tint'] = '#595959'  # 2.99797:1 against black
        self.assertEqual(failed(data), {'hud-contrast'})
        data['cues'][-1]['tint'] = '#5A5A5A'
        self.assertEqual(failed(data), set())
        hud.update(text_color='#0000FF', panel_color='#000000')
        self.assertEqual(failed(data), {'hud-contrast'})
        hud['text_color'] = '#00FF00'
        self.assertEqual(failed(data), set())

    def test_gate_needs_a_dark_view_and_contrasting_subject_samples_in_all_views(self):
        data = example()
        dark, bright = data['views']
        dark.update(silhouette='#FFFFFF', backdrop='#FFFFFF')
        self.assertEqual(failed(data), {'camera-readability'})
        dark['silhouette'] = '#000000'
        self.assertEqual(failed(data), {'camera-readability'})  # contrast passes but neither view is dark
        dark.update(silhouette='#5A5A5A', backdrop='#000000')
        self.assertEqual(failed(data), set())
        bright.update(silhouette='#595959', backdrop='#000000')
        self.assertEqual(failed(data), {'camera-readability'})

    def test_subject_bounds_and_half_open_overlap_use_scaled_panel(self):
        data = example()
        view = data['views'][1]
        # 256px panel grows to 384px at 150%; its right edge is 36 + 384.
        view['gate_rect'] = [420, 380, 24, 24]
        self.assertEqual(failed(data), set())
        for rect in ([419, 380, 24, 24], [420, 380, 23, 24], [831, 40, 24, 24],
                     [-1, 100, 24, 24], [500, 457, 24, 24]):
            with self.subTest(rect=rect):
                view['gate_rect'] = rect
                self.assertEqual(failed(data), {'camera-readability'})

    def test_nonuniform_safe_insets_and_rounding_of_fractional_scale(self):
        data = example()
        view = data['views'][1]
        view['scale_percent'] = 151
        # Width ceil(256 * 1.51) = 387. Height ceil(56 * 1.51) = 85.
        view['panel_xy'] = [854 - 48 - 387, 480 - 24 - 85]
        self.assertEqual(failed(data), set())
        for axis in range(2):
            view['panel_xy'][axis] += 1
            self.assertEqual(failed(data), {'safe-scaling'})
            view['panel_xy'][axis] -= 1
        view['panel_xy'] = [31, 16]
        self.assertEqual(failed(data), {'safe-scaling'})
        view['panel_xy'] = [32, 15]
        self.assertEqual(failed(data), {'safe-scaling'})

    def test_device_fixture_needs_resolution_scale_and_inset_variation(self):
        for defect in ('same-resolution', 'normal-only', 'enlarged-only', 'no-inset'):
            with self.subTest(defect=defect):
                data = example()
                first, second = data['views']
                if defect == 'same-resolution':
                    second.update(width=first['width'], height=first['height'])
                elif defect == 'normal-only':
                    second['scale_percent'] = 100
                elif defect == 'enlarged-only':
                    first['scale_percent'] = 150
                    first['panel_xy'] = [40, 590]
                else:
                    for view in data['views']:
                        view['insets'] = [0, 0, 0, 0]
                self.assertEqual(failed(data), {'safe-scaling'})

    def test_type_hierarchy_needs_both_font_sizes_and_vertical_space(self):
        for change in ({'headline_px': 19}, {'hint_px': 13}, {'size': [256, 43]}, {'size': [19, 56]}):
            with self.subTest(change=change):
                data = example()
                data['hud'].update(change)
                self.assertEqual(failed(data), {'type-hierarchy'})

    def test_noncolor_cues_remain_decodable_with_identical_tints_and_on_state_returns(self):
        data = example()
        for cue in data['cues']:
            cue['tint'] = '#FFFFFF'
            if cue['state'] == 'locked':
                cue.update(label='Key required', icon='keyhole')
        self.assertEqual(failed(data), set())
        for key, replacement in [('label', 'Unlocked'), ('icon', 'open-door'), ('label', 'Blue'), ('icon', 'circle')]:
            with self.subTest(key=key, replacement=replacement):
                broken = deepcopy(data)
                for cue in broken['cues']:
                    if cue['state'] == 'locked':
                        cue[key] = replacement
                self.assertEqual(failed(broken), {'noncolor-cues'})

    def test_valid_alternatives_must_be_consistent_and_actions_match_each_state(self):
        for field, value in [('label', 'Key required'), ('icon', 'keyhole'), ('action', 'open-gate')]:
            with self.subTest(field=field):
                data = example()
                data['cues'][2][field] = value
                self.assertEqual(failed(data), {'stable-response'})
        data = example()
        for cue in data['cues']:
            cue['action'] = 'open-gate'
        self.assertEqual(failed(data), {'stable-response'})
        data = example()
        data['cues'].sort(key=lambda cue: cue['state'])
        self.assertEqual(failed(data), {'stable-response'})

    def test_malformed_input_is_bounded_and_rejected(self):
        for mutate in (
            lambda d: d.update(extra=True),
            lambda d: d['views'][0].update(width=True),
            lambda d: d['views'][0].update(scale_percent=150.5),
            lambda d: d['views'][0].update(height=100_000),
            lambda d: d['views'][0].update(insets=[0, -1, 0, 0]),
            lambda d: d['views'][0].update(panel_xy=[1]),
            lambda d: d.update(views=d['views'] * 3),
            lambda d: d.update(cues=d['cues'] * 5),
            lambda d: d['hud'].update(size=[False, True]),
            lambda d: d['hud'].update(panel_color='#2228'),
            lambda d: d['views'][0].update(silhouette='transparent'),
            lambda d: d['cues'][0].update(tint=['#ffffff']),
            lambda d: d['cues'][0].update(state='ajar'),
            lambda d: d['cues'][0].update(icon={}),
            lambda d: d['cues'][0].update(label='x' * 65),
        ):
            with self.subTest(mutate=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess(lab.TRACK['id'], data)
        with self.assertRaises(ValueError):
            lab.assess('interface', example())
