from copy import deepcopy
import json
import unittest

from command_center import intelligence_ui as ui


def statuses(report):
    return {c['id']: c['status'] for c in report['checks'] if c['status'] != 'pass'}


class IntelligenceUITests(unittest.TestCase):
    def test_example_report_contract_is_replayable_and_does_not_mutate_inputs(self):
        data = ui.example()
        original = deepcopy(data)
        result = ui.analyze(data)
        self.assertEqual(result['schema_version'], 1)
        self.assertEqual(result['kind'], 'ui')
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(statuses(result), {})
        self.assertEqual(len(result['checks']), 7)
        self.assertTrue(all(set(c) == {'id', 'label', 'status', 'detail'} for c in result['checks']))
        self.assertEqual(result['metrics']['profile_count'], 2)
        self.assertEqual(result['metrics']['locale_count'], 2)
        self.assertEqual(ui.analyze(json.loads(json.dumps(data))), result)
        self.assertEqual(data, original)
        result['metrics']['profiles'][0]['viewport'][0] = 0
        self.assertEqual(data, original)
        data['profiles'][0]['widgets'].clear()
        self.assertEqual(ui.example(), original)

    def test_longer_localized_text_only_overflows_its_own_profile(self):
        data = ui.example()
        widget = data['profiles'][1]['widgets'][1]
        # Content area is 288×48. The displayed physical box itself remains in bounds.
        widget['measured_text'] = [288, 48]
        self.assertEqual(ui.analyze(data)['status'], 'pass')
        widget['measured_text'] = [288.75, 49.5]
        result = ui.analyze(data)
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(statuses(result), {'text-fit': 'fail'})
        desktop, handheld = result['metrics']['profiles']
        self.assertEqual(desktop['overflowing_boxes'], 0)
        self.assertEqual(handheld['overflowing_boxes'], 1)
        self.assertEqual(handheld['max_width_overflow_px'], 0.75)
        self.assertEqual(handheld['max_height_overflow_px'], 1.5)
        self.assertIn('hand-de/inspect', next(c['detail'] for c in result['checks'] if c['id'] == 'text-fit'))

    def test_asymmetric_safe_insets_and_exact_viewport_boundaries(self):
        data = ui.example()
        profile = data['profiles'][1]
        profile['widgets'][0].update(rect=[48, 24, 1280 - 48 - 56, 720 - 24 - 32])
        self.assertEqual(statuses(ui.analyze(data)), {})  # nonfocusable backing may intentionally span controls
        rect = profile['widgets'][0]['rect']
        for axis, delta in ((0, -1), (1, -1), (2, 1), (3, 1)):
            rect[axis] += delta
            self.assertEqual(statuses(ui.analyze(data)), {'safe-area': 'fail'})
            rect[axis] -= delta
        profile['widgets'][0]['rect'] = [0, 0, 1280, 720]
        self.assertEqual(statuses(ui.analyze(data)), {'safe-area': 'fail'})
        profile['widgets'][0]['rect'][0] = -1
        self.assertEqual(statuses(ui.analyze(data)), {'viewport-bounds': 'fail', 'safe-area': 'fail'})

    def test_touching_hit_rectangles_are_valid_and_overlap_is_review_only(self):
        data = ui.example()
        p = data['profiles'][1]
        a, b = p['widgets'][1:]
        ax, ay, aw, ah = a['rect']
        b['rect'][:2] = [ax + aw, ay]
        self.assertEqual(statuses(ui.analyze(data)), {})
        b['rect'][0] -= 0.25
        result = ui.analyze(data)
        self.assertEqual(result['status'], 'warn')
        self.assertEqual(statuses(result), {'control-overlap': 'warn'})
        self.assertEqual(result['metrics']['profiles'][1]['overlapping_control_pairs'], 1)
        p['widgets'][0]['measured_text'] = [1000, 10]
        self.assertEqual(ui.analyze(data)['status'], 'fail')

    def test_required_controls_must_exist_and_be_focusable_in_each_profile(self):
        data = ui.example()
        p = data['profiles'][0]
        p['widgets'][1]['focusable'] = False
        p['widgets'].pop()
        result = ui.analyze(data)
        self.assertEqual(statuses(result), {'required-controls': 'fail', 'focus-reachability': 'fail'})
        detail = next(c['detail'] for c in result['checks'] if c['id'] == 'required-controls')
        self.assertIn('desk-en/inspect is nonfocusable', detail)
        self.assertIn('desk-en/return is missing', detail)
        self.assertEqual(result['metrics']['profiles'][0]['missing_or_nonfocusable_required'], 2)
        self.assertEqual(result['metrics']['profiles'][1]['missing_or_nonfocusable_required'], 0)

    def test_focus_analysis_distinguishes_unreachable_trapped_and_dangling_targets(self):
        data = ui.example()
        p = data['profiles'][0]
        p['focus_edges'] = [['inspect', 'return'], ['return', 'return'], ['return', 'heading']]
        result = ui.analyze(data)
        self.assertEqual(statuses(result), {'focus-reachability': 'fail'})
        row = result['metrics']['profiles'][0]
        self.assertEqual((row['unreachable_focusable'], row['reachable_without_return'], row['invalid_focus_edges']), (0, 1, 1))
        p['focus_edges'] = [['return', 'inspect']]
        row = ui.analyze(data)['metrics']['profiles'][0]
        self.assertEqual((row['unreachable_focusable'], row['reachable_without_return']), (1, 0))
        p['initial_focus'] = None
        self.assertEqual(ui.analyze(data)['metrics']['profiles'][0]['unreachable_focusable'], 2)

    def test_nontext_hud_has_no_spurious_focus_error_and_notes_unmeasured_text(self):
        data = ui.example()
        data['profiles'] = [data['profiles'][0]]
        data['required_controls'] = []
        p = data['profiles'][0]
        p.update(widgets=[p['widgets'][0]], focus_edges=[], initial_focus=None)
        p['widgets'][0].update(measured_text=None)
        self.assertEqual(statuses(ui.analyze(data)), {'text-coverage': 'warn'})
        p['widgets'][0]['padding'][0] = 999
        self.assertEqual(statuses(ui.analyze(data)), {'text-fit': 'fail', 'text-coverage': 'warn'})

    def test_bounded_dense_profile_keeps_actionable_examples_short_but_counts_all(self):
        data = ui.example()
        p = data['profiles'][0]
        data['profiles'] = [p]
        data['required_controls'] = []
        first = p['widgets'][1]
        p['widgets'] = [dict(deepcopy(first), id=f'control{i}') for i in range(128)]
        p.update(initial_focus='control0', focus_edges=[])
        result = ui.analyze(data)
        row = result['metrics']['profiles'][0]
        self.assertEqual(row['overlapping_control_pairs'], 128 * 127 // 2)
        self.assertEqual(row['unreachable_focusable'], 127)
        self.assertTrue(all(len(check['detail']) < 1200 for check in result['checks']))

    def test_strict_schema_types_ranges_and_no_file_or_executable_fields(self):
        for change in (
            lambda d: d.update(path='/private/layout.json'),
            lambda d: d.update(required_controls=['inspect', 'inspect']),
            lambda d: d.update(profiles=[]),
            lambda d: d.update(profiles=d['profiles'] * 9),
            lambda d: d['profiles'][1].update(id=d['profiles'][0]['id']),
            lambda d: d['profiles'][0].update(locale='\n'),
            lambda d: d['profiles'][0].update(viewport=[100, 0]),
            lambda d: d['profiles'][0].update(viewport=[True, 100]),
            lambda d: d['profiles'][0].update(safe_insets=[960, 0, 960, 0]),
            lambda d: d['profiles'][0].update(widgets=d['profiles'][0]['widgets'] * 44),
            lambda d: d['profiles'][0]['widgets'][0].update(id='inspect'),
            lambda d: d['profiles'][0]['widgets'][0].update(rect=[0, 0, 32, 0]),
            lambda d: d['profiles'][0]['widgets'][0].update(rect=[False, 0, 10, 30]),
            lambda d: d['profiles'][0]['widgets'][0].update(padding=[0, -1, 0, 0]),
            lambda d: d['profiles'][0]['widgets'][0].update(measured_text=[10**10000, 1]),
            lambda d: d['profiles'][0]['widgets'][0].update(measured_text=[float('nan'), 1]),
            lambda d: d['profiles'][0]['widgets'][0].update(measured_text=[2, float('inf')]),
            lambda d: d['profiles'][0]['widgets'][0].update(measured_text=[0, 0]),
            lambda d: d['profiles'][0]['widgets'][0].update(text='private localized copy'),
            lambda d: d['profiles'][0]['widgets'][0].update(focusable=1),
            lambda d: d['profiles'][0].update(initial_focus={}),
            lambda d: d['profiles'][0].update(focus_edges=[['inspect', 'return']] * 2),
            lambda d: d['profiles'][0].update(focus_edges=[['inspect', 'return']] * 513),
            lambda d: d['profiles'][0].update(focus_edges=[['inspect', []]]),
        ):
            with self.subTest(change=change):
                data = ui.example()
                change(data)
                with self.assertRaises(ValueError):
                    ui.analyze(data)
        for invalid in (None, [], True):
            with self.assertRaises(ValueError):
                ui.analyze(invalid)
