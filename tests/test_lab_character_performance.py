from copy import deepcopy
import unittest

from command_center import lab_character_performance as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def failed(data):
    return {r['id'] for r in lab.assess('character-performance', data) if r['status'] == 'fail'}


class CharacterPerformanceTests(unittest.TestCase):
    def test_example_samples_sparse_keys_and_matches_criteria(self):
        data = example()
        original = deepcopy(data)
        result = lab.assess('character-performance', data)
        self.assertEqual([r['id'] for r in result], [c['id'] for c in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in result))
        self.assertIn('10, 64, 12', result[4]['detail'])
        self.assertEqual(lab.assess('character-performance', data), result)
        self.assertEqual(data, original)

    def test_semantic_roles_follow_renamed_controls_and_signed_axes(self):
        data = example()
        for c in data['rig']:
            old = c['id']
            c['id'] = 'copy_' + old
            keys = data['curves'].pop(old)
            if c['unit'] != 'percent':
                c['sign'] *= -1
                keys = [[f, -v] for f, v in keys]
            data['curves'][c['id']] = keys
        data['rig'].reverse()
        self.assertFalse(failed(data))
        data['target_yaw_deg'] *= -1
        for c in data['rig']:
            if c['role'] in ('eyes', 'head'):
                c['sign'] *= -1
        self.assertFalse(failed(data))

    def test_unbound_aliases_and_incompatible_units_do_not_produce_sample_passes(self):
        for defect in ('duplicate_id', 'duplicate_role', 'bad_units', 'missing', 'extra',
                       'absent_role', 'unsigned_face', 'zero_axis'):
            with self.subTest(defect=defect):
                data = example()
                rig, curves = data['rig'], data['curves']
                if defect == 'duplicate_id':
                    rig[0]['id'] = rig[1]['id']
                elif defect == 'duplicate_role':
                    rig[0]['role'] = rig[1]['role']
                elif defect == 'bad_units':
                    rig[0]['unit'] = 'degrees'
                elif defect == 'missing':
                    del curves[rig[0]['id']]
                elif defect == 'extra':
                    curves['extra_face'] = [[0, 0], [47, 100]]
                elif defect == 'absent_role':
                    del curves[rig.pop()['id']]
                elif defect == 'unsigned_face':
                    rig[0]['sign'] = -1
                else:
                    rig[3]['sign'] = 0
                failures = failed(data)
                self.assertIn('retarget-map', failures)
                self.assertTrue({'lip-sync', 'gaze', 'weight-contact'} <= failures)

    def test_keyframes_span_clip_stay_in_units_and_are_strictly_ordered(self):
        for keys in ([[1, 0], [47, 0]], [[0, 0], [48, 0]], [[0, 0], [8, 20], [8, 30], [47, 0]],
                     [[0, 0], [13, 30], [8, 30], [47, 0]], [[0, 0], [47, 101]]):
            with self.subTest(keys=keys):
                data = example()
                data['curves']['jaw_drop'] = keys
                self.assertIn('curve-coverage', failed(data))

    def test_cues_require_order_both_shapes_and_lead_time_in_ms(self):
        for change in (
            lambda d: d['beats'].update(look=0),
            lambda d: d['beats'].update(prepare=17),
            lambda d: d['beats'].update(settle=48),
            lambda d: d.update(target_yaw_deg=14),
            lambda d: d.update(target_yaw_deg=-36),
            lambda d: d.update(fps=12),
            lambda d: d['phonemes'].reverse(),
            lambda d: d['phonemes'].clear(),
            lambda d: d['phonemes'][0].update(sound='aa'),
            lambda d: d['phonemes'][1].update(frame=14),
            lambda d: d['phonemes'][1].update(frame=37),
        ):
            with self.subTest(change=change):
                data = example()
                change(data)
                self.assertIn('beat-sheet', failed(data))
        data = example()
        data.update(fps=25)
        data['beats']['look'] = 7  # Ten frames, exactly 400 ms.
        self.assertNotIn('beat-sheet', failed(data))
        data['beats']['look'] = 6
        self.assertIn('beat-sheet', failed(data))
        data.update(fps=100)
        data['beats'].update(look=13, prepare=15)
        self.assertNotIn('beat-sheet', failed(data))  # Four frames, exactly 40 ms.
        data['beats']['look'] = 14
        self.assertIn('beat-sheet', failed(data))

    def test_lip_sync_reads_both_controls_at_each_landmark_including_between_keys(self):
        data = example()
        data['curves']['jaw_drop'] = [[0, 0], [14, 20], [20, 100], [47, 0]]
        data['curves']['lips_press'] = [[0, 0], [14, 70], [17, 20], [47, 0]]
        self.assertEqual(failed(data), {'lip-sync'})  # Interpolated jaw at frame 17 is 60.
        data['curves']['jaw_drop'][2][0] = 18
        self.assertFalse(failed(data))  # Interpolated value at frame 17 is 80.
        for sound in ('b', 'p'):
            data['phonemes'][0]['sound'] = sound
            self.assertFalse(failed(data))
        data['curves']['lips_press'][1][1] = 69
        self.assertEqual(failed(data), {'lip-sync'})
        data['curves']['lips_press'][1][1] = 70
        data['curves']['lips_press'][2][1] = 21
        self.assertEqual(failed(data), {'lip-sync'})

    def test_brow_gaze_and_hand_are_independent(self):
        for channel, keys, criterion in (
            ('brow_lift', [[0, 10], [17, 54], [47, 10]], 'expression'),
            ('brow_lift', [[0, 10], [17, 70], [36, 21], [47, 0]], 'expression'),
            ('arm_lift', [[0, 0], [12, 4], [17, 45], [47, 0]], 'gesture'),
            ('arm_lift', [[0, 0], [12, -8], [17, 34], [36, 3], [47, 0]], 'gesture'),
            ('eye_pan', [[0, 0], [8, -2], [17, -1], [47, -1]], 'gaze'),
            ('neck_turn', [[0, 0], [8, 6], [17, 23], [47, 23]], 'gaze'),
            ('neck_turn', [[0, 0], [8, 1], [17, 23], [36, 0], [47, 0]], 'gaze'),
        ):
            with self.subTest(channel=channel, keys=keys):
                data = example()
                data['curves'][channel] = keys
                self.assertEqual(failed(data), {criterion})
        data = example()
        data['curves']['eye_pan'] = [[0, 0], [8, -23], [17, -9], [47, -9]]
        data['curves']['neck_turn'] = [[0, 0], [8, 1], [17, 15], [47, 15]]
        self.assertEqual(failed(data), {'gaze'})  # Correct world aim, insufficient head follow.

    def test_hip_load_and_drift_use_rest_relative_metric_world_space(self):
        data = example()
        curves = data['curves']
        curves['pelvis_up'] = [[0, 900], [12, 880], [36, 905], [47, 900]]
        curves['shoe_world_x'] = [[0, 100], [22, 106], [36, 100], [47, 100]]
        curves['shoe_world_z'] = [[0, -200], [22, -192], [36, -200], [47, -200]]
        self.assertFalse(failed(data))  # Six and eight millimetres form exactly 10 mm drift.
        curves['shoe_world_x'][1][1] += 1
        self.assertEqual(failed(data), {'weight-contact'})
        curves['shoe_world_x'][1][1] -= 1
        curves['pelvis_up'][1][1] += 1
        self.assertEqual(failed(data), {'weight-contact'})
        curves['pelvis_up'][1][1] -= 1
        curves['pelvis_up'][2][1] += 1
        self.assertEqual(failed(data), {'weight-contact'})
        curves['pelvis_up'][2][1] -= 1
        curves['shoe_world_x'][-1][1] += 40
        self.assertFalse(failed(data))  # The planted interval ended at frame 36.

    def test_malformed_nested_values_and_limits_are_rejected(self):
        for change in (
            lambda d: d.update(fps=True), lambda d: d.update(frame_count=241),
            lambda d: d['beats'].update(accent=17.5), lambda d: d.update(target_yaw_deg=float('nan')),
            lambda d: d.update(extra=1), lambda d: d['rig'][0].update(unit='meters'),
            lambda d: d['rig'][0].update(role='all'), lambda d: d['rig'][0].update(sign=True),
            lambda d: d['rig'][0].update(id='Bad name'), lambda d: d.update(rig=d['rig'] * 2),
            lambda d: d['phonemes'][0].update(sound=[]), lambda d: d.update(phonemes=d['phonemes'] * 17),
            lambda d: d.update(curves=[]), lambda d: d['curves'].update(jaw_drop=[[0, 100, 1], [47, 0]]),
            lambda d: d['curves'].update(jaw_drop=[[0, 0]] * 33),
            lambda d: d['curves'].update(jaw_drop=[[0, True], [47, 0]]),
        ):
            with self.subTest(change=change):
                data = example()
                change(data)
                with self.assertRaises(ValueError):
                    lab.assess('character-performance', data)
        for key, value in [('elsewhere', {}), ('character-performance', None)]:
            with self.assertRaises(ValueError):
                lab.assess(key, value)
