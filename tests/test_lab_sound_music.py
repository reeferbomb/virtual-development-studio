from copy import deepcopy
import unittest

from command_center import lab_sound_music as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def failed(data):
    return {r['id'] for r in lab.assess('sound-music', data) if r['status'] == 'fail'}


class SoundMusicLabTests(unittest.TestCase):
    def test_fixture_matches_rubric_and_preserves_inputs(self):
        data = example()
        original = deepcopy(data)
        result = lab.assess('sound-music', data)
        self.assertEqual([r['id'] for r in result], [c['id'] for c in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in result))
        self.assertEqual(lab.assess('sound-music', data), result)
        self.assertEqual(data, original)

    def test_new_music_and_takes_with_different_source_levels(self):
        data = example()
        data['motif'] = [2, 6, 5, 9, 11]
        for change, pitch in zip(data['expected']['changes'], [2, 11, 9]):
            change['pitch'] = pitch
        data['materials']['timber'] = ['hollow_a', 'hollow_b']
        names = {'plank_heel': 'hollow_a', 'plank_toe': 'hollow_b'}
        data['expected']['voices'] = [[names.get(name, name) for name in row] for row in data['expected']['voices']]
        data['levels']['room'] += 2
        data['expected']['peak'] += 2
        data['expected']['muted_radio_peak'] += 2
        self.assertEqual(failed(data), set())

    def test_each_material_has_its_own_cursor_and_a_culled_request_consumes_its_take(self):
        data = example()
        data['expected']['voices'][8] = ['plank_toe']
        self.assertEqual(failed(data), {'voice-priority'})
        data = example()
        data['steps'].pop()  # The only audible timber B at tick 10 is gone.
        self.assertIn('material-foley', failed(data))
        data = example()
        data['steps'][1]['surface'] = 'timber'
        self.assertIn('material-foley', failed(data))

    def test_older_same_priority_is_retained_and_dropped_voice_never_returns(self):
        data = example()
        data['steps'] = [{'tick': 0, 'surface': 'timber'}, {'tick': 1, 'surface': 'tile'}]
        data['pop'] = [1]
        data['alert'] = []
        voices, *_ = lab._effects(data)
        self.assertEqual(voices[:4], [['plank_heel'], ['pop', 'plank_heel'], ['pop'], []])

    def test_predictions_alone_cannot_replace_audible_competition(self):
        data = example()
        data['steps'] = [s for s in data['steps'] if s['tick'] != 4]
        data['pop'] = []
        data['expected']['voices'] = lab._effects(data)[0]
        self.assertIn('voice-priority', failed(data))

    def test_requests_coalesce_and_a_boundary_request_precedes_commit(self):
        data = example()
        data['requests'] = [{'tick': 1, 'state': 'lift'}, {'tick': 3, 'state': 'quiet'},
                            {'tick': 4, 'state': 'lift'}, {'tick': 6, 'state': 'quiet'}]
        changes, states, delayed = lab._score(data)
        self.assertEqual(changes, data['expected']['changes'])
        self.assertEqual(states, ['quiet'] * 4 + ['lift'] * 4 + ['quiet'] * 4)
        self.assertEqual(delayed, {'quiet'})
        self.assertEqual(failed(data), {'adaptive-score'})
        data['requests'].pop(2)
        self.assertEqual(lab._score(data)[0], [{'tick': 0, 'state': 'quiet', 'pitch': 0}])

    def test_phase_preserves_transport_after_music_state_changes(self):
        data = example()
        data['expected']['changes'][2]['pitch'] = data['motif'][0]
        self.assertEqual(failed(data), {'adaptive-score'})
        data = example()
        data['motif'] = [0, 0, 0]
        for change in data['expected']['changes']:
            change['pitch'] = 0
        self.assertEqual(failed(data), {'adaptive-score'})
        data = example()
        data['motif'] = [0, 3, 7, 10]
        for change in data['expected']['changes']:
            change['pitch'] = 0
        self.assertEqual(failed(data), {'adaptive-score'})

    def test_earliest_peak_radio_interval_and_inclusive_budget(self):
        data = example()
        data['expected']['peak_tick'] = 5  # Same level, later tick.
        self.assertEqual(failed(data), {'mix-headroom'})
        data = example()
        data['levels']['radio'] += 3
        data['expected']['peak'] = 80
        self.assertEqual(failed(data), set())
        data['levels']['radio'] += 1
        data['expected']['peak'] += 1
        self.assertEqual(failed(data), {'mix-headroom'})
        data = example()
        data['radio'] = {'start': 3, 'end': 4}
        data['expected'].update(peak=68, peak_tick=4, muted_radio_peak=68)
        self.assertEqual(failed(data), {'mix-headroom'})
        data['radio']['end'] = 5
        data['expected']['peak'] = 77
        self.assertEqual(failed(data), set())

    def test_every_alert_requires_one_same_tick_visual_marker(self):
        for markers in ([], [3], [4, 5]):
            data = example()
            data['markers'] = markers
            self.assertEqual(failed(data), {'visual-cues'})

    def test_malformed_shapes_types_ranges_and_identifiers_are_rejected(self):
        for mutate in (
            lambda d: d.update(ticks=33), lambda d: d.update(alert=[True]), lambda d: d.update(pop=[3, 2]),
            lambda d: d.update(markers=[4, 4]), lambda d: d['steps'][0].update(surface='stone'),
            lambda d: d['levels'].update(alert=0), lambda d: d['levels'].update(radio=2.0),
            lambda d: d['materials']['tile'].__setitem__(1, 'pop'),
            lambda d: d['materials']['tile'].__setitem__(0, 'plank_heel'), lambda d: d.update(motif=[2, 13, 4]),
            lambda d: d['radio'].update(start=7), lambda d: d['requests'][0].update(state='end'),
            lambda d: d['expected']['voices'].pop(), lambda d: d['expected']['voices'][0].extend(['a', 'b']),
            lambda d: d['expected']['changes'][0].update(pitch=[]), lambda d: d.update(unexpected=[]),
        ):
            with self.subTest(mutation=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess('sound-music', data)
        for key, data in [('unknown', {}), ('sound-music', []), ('sound-music', None)]:
            with self.assertRaises(ValueError):
                lab.assess(key, data)


if __name__ == '__main__':
    unittest.main()
