from copy import deepcopy
import unittest

from command_center import lab_hud_excellence as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def failed(data):
    return {r['id'] for r in lab.assess('hud-excellence', data) if r['status'] == 'fail'}


class HudExcellenceTests(unittest.TestCase):
    def test_example_is_replayable_and_matches_published_criteria(self):
        data = example()
        rows = lab.assess(lab.TRACK['id'], data)
        self.assertEqual([r['id'] for r in rows], [r['id'] for r in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in rows))
        self.assertEqual(lab.assess(lab.TRACK['id'], data), rows)
        self.assertEqual(data, example())

    def test_context_preserves_warning_and_expires_prompts(self):
        for state, key in [('compact-alarm', 'warning'), ('console', 'use'), ('travel', 'route')]:
            with self.subTest(state=state):
                data = example()
                data['visible'][state].remove(key)
                self.assertEqual(failed(data), {'context'})
        data = example()
        data['visible']['alarm'].remove('route')
        self.assertEqual(failed(data), set())
        data['visible']['travel'].append('use')
        self.assertEqual(failed(data), {'context'})

    def test_safe_bounds_apply_to_right_and_bottom_anchors(self):
        for offset, passes in (([52, 29], True), ([51, 29], False), ([52, 28], False)):
            data = example()
            data['widgets']['route']['offset'] = offset
            self.assertEqual(failed(data), set() if passes else {'layout'})

    def test_enlarged_collision_and_exact_touching_edges(self):
        data = example()
        # Resume starts at 120 with height 40 normally and 60 enlarged.
        for y, passes in ((180, True), (179, False)):
            data['widgets']['settings']['offset'] = [100, y]
            self.assertEqual(failed(data), set() if passes else {'layout'})
        data = example()
        data['widgets']['use'].update(corner='br', offset=data['widgets']['route']['offset'])
        self.assertEqual(failed(data), set())  # the two widgets never share a state

    def test_glyph_floor_width_height_and_rounded_advance(self):
        for updates in ({'glyph_px': 13}, {'size': [200, 31]}, {'label': 'W' * 24}, {'size': [101, 64]}):
            with self.subTest(updates=updates):
                data = example()
                data['widgets']['status'].update(updates)
                self.assertEqual(failed(data), {'type-fit'})
        data = example()
        data['widgets']['status'].update(label='x' * 12, size=[136, 32])
        self.assertEqual(failed(data), set())

    def test_independent_text_focus_and_noncolor_contracts(self):
        for mode, swatches in [('default', {'text': '#747474', 'plate': '#000000'}),
                               ('high-contrast', {'text': '#888888', 'plate': '#000000'}),
                               ('default', {'focus': '#595959', 'plate': '#000000'})]:
            with self.subTest(mode=mode, swatches=swatches):
                data = example()
                data['palettes'][mode].update(swatches)
                self.assertEqual(failed(data), {'contrast-feedback'})
        for state, change in [('applied', {'text': 'Green'}), ('blocked', {'symbol': 'check'})]:
            data = example()
            data['feedback'][state].update(change)
            self.assertEqual(failed(data), {'contrast-feedback'})

    def test_require_bidirectional_reachability_and_visible_modal_focus(self):
        data = example()
        # The sample trace never selects Return. Moving focus there must still allow a way out.
        data['focus']['links']['return'] = {'up': 'return', 'down': 'return'}
        self.assertEqual(failed(data), {'menu-focus'})
        data['focus']['links']['return']['up'] = 'settings'
        self.assertEqual(failed(data), {'menu-focus'})
        data = example()
        data['visible']['options'].remove('compact')
        self.assertEqual(failed(data), {'context', 'menu-focus', 'state-replay'})
        data = example()
        data['focus']['restore'] = 'resume'
        self.assertEqual(failed(data), {'menu-focus', 'state-replay'})

    def test_active_bindings_drive_replay_independently_of_prompt_copy(self):
        for name in ('keyboard', 'controller'):
            data = example()
            device = data['devices'][name]
            device['confirm_prompt'] = device['default']['confirm']
            self.assertEqual(failed(data), {'remap'})
            device['confirm_prompt'] = device['active']['confirm']
            device['trace'][2] = device['default']['confirm']
            self.assertEqual(failed(data), {'state-replay'})
            device['active']['confirm'] = device['active']['down']
            self.assertEqual(failed(data), {'remap', 'state-replay'})

    def test_both_settings_must_remain_enabled_when_resuming(self):
        for mutation in ('toggle-again', 'omit-resume', 'wrong-key', 'only-pause'):
            with self.subTest(mutation=mutation):
                data = example()
                keys = data['devices']['controller']['trace']
                if mutation == 'toggle-again':
                    keys.insert(4, 'west')
                elif mutation == 'omit-resume':
                    keys.pop()
                elif mutation == 'wrong-key':
                    keys[0] = 'north'
                else:
                    keys[:] = ['menu', 'west']
                self.assertEqual(failed(data), {'state-replay'})
        data = example()
        device = data['devices']['controller']
        device['trace'][6:7] = ['dpad-down', 'west']  # Return control restores the opener like Back.
        self.assertEqual(failed(data), set())

    def test_rejects_malformed_and_out_of_bounds_data(self):
        for mutate in (
            lambda d: d.update(extra=True),
            lambda d: d['widgets']['size'].update(size=[0, 10]),
            lambda d: d['widgets']['status'].update(glyph_px=True),
            lambda d: d['widgets']['warning'].update(label='\n'),
            lambda d: d['widgets']['warning'].update(label='x' * 33),
            lambda d: d['widgets']['warning'].update(offset=[4097, 0]),
            lambda d: d['visible']['pause'].append([]),
            lambda d: d['palettes']['default'].update(text='#FFF8'),
            lambda d: d['focus']['links'].pop('return'),
            lambda d: d['devices']['controller'].update(trace=['menu'] * 33),
            lambda d: d['devices']['keyboard']['trace'].append('dpad-down'),
        ):
            with self.subTest(mutate=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess('hud-excellence', data)
        with self.assertRaises(ValueError):
            lab.assess('interface', example())
