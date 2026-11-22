from copy import deepcopy
import unittest

from command_center import lab_diegetic_narrative as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def reports(data):
    return {row['id']: row for row in lab.assess('diegetic-narrative', data)}


def failed(data):
    return {key for key, row in reports(data).items() if row['status'] == 'fail'}


class DiegeticNarrativeTests(unittest.TestCase):
    def test_example_covers_all_six_route_presentations_and_is_replayable(self):
        data = example()
        rows = reports(data)
        self.assertEqual(list(rows), [c['id'] for c in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(row['status'] == 'pass' and row['detail'] for row in rows.values()))
        self.assertIn('6/6', rows['discovery-pacing']['detail'])
        self.assertIn('1/2', rows['optional-discovery']['detail'])
        self.assertEqual(data, example())
        data['cues'].reverse()
        self.assertEqual(reports(data), rows)

    def test_every_offered_path_is_traced_including_shortcuts_and_dead_ends(self):
        data = example()
        data['rooms'][0]['next'].append('loft_choice')
        self.assertEqual(failed(data), {'clue-layers', 'optional-discovery', 'sensory-alternatives', 'discovery-pacing'})
        self.assertIn('vestibule/loft_choice', reports(data)['discovery-pacing']['detail'])
        data = example()
        data['rooms'][1]['next'].clear()
        self.assertIn('1 premature endings', reports(data)['routes']['detail'])
        self.assertIn('routes', failed(data))
        data = example()
        data['rooms'][0]['next'].remove('cart_bay')
        self.assertIn('1 unreachable rooms', reports(data)['routes']['detail'])
        self.assertIn('routes', failed(data))

    def test_complete_routes_and_empty_cue_sheets_cannot_pass_vacuously(self):
        data = example()
        data['rooms'][3]['next'].clear()
        self.assertEqual(failed(data), set(reports(data)) - {'primary-samples'})
        data = example()
        data['cues'].clear()
        self.assertEqual(failed(data), set(reports(data)) - {'routes'})

    def test_all_primary_sample_thresholds_and_offscreen_signs(self):
        for i, field, minimum in ((0, 'visible_height_px', 24), (1, 'above_ambience_db', 6), (2, 'visible_glyph_px', 14)):
            with self.subTest(field=field):
                data = example()
                cue = data['cues'][i]
                cue['sample'][field] = minimum
                self.assertEqual(failed(data), set())
                cue['sample'][field] = minimum - 1
                self.assertIn('primary-samples', failed(data))
                self.assertIn('clue-layers', failed(data))
                self.assertIn(cue['id'], reports(data)['primary-samples']['detail'])
        data = example()
        data['cues'][4]['sample']['visible_glyph_px'] = 0
        self.assertEqual(failed(data), {'primary-samples', 'optional-discovery'})

    def test_optional_clue_can_be_missed_but_must_have_a_playable_discovery(self):
        data = example()
        data['cues'][4].update(room='hoist', second=2)
        self.assertEqual(failed(data), {'optional-discovery'})
        data['cues'].pop(4)
        self.assertEqual(failed(data), {'optional-discovery'})

    def test_each_route_needs_independent_kinds_for_each_essential_beat(self):
        data = example()
        cue = data['cues'][2]
        cue.update(kind='sound', sample={'above_ambience_db': 9}, alternative=None)
        self.assertEqual(failed(data), {'clue-layers'})
        self.assertIn('1/2', reports(data)['clue-layers']['detail'])

    def test_audio_only_cannot_borrow_visual_cues_or_take_a_detour(self):
        data = example()
        # Both routes now use visible props and signs for the response. Only the nook has a description.
        data['cues'][-1].update(kind='prop', sample={'visible_height_px': 40}, alternative=None)
        data['cues'][3].update(kind='sign', sample={'visible_glyph_px': 16})
        data['cues'][2]['alternative'] = None
        self.assertEqual(failed(data), {'sensory-alternatives', 'discovery-pacing'})
        self.assertIn('3/4', reports(data)['sensory-alternatives']['detail'])
        data['cues'][2]['alternative'] = {'channel': 'audio-description', 'beat': 'response',
                                           'evidence': 'The cart bears the drying-loft stamp.'}
        self.assertEqual(failed(data), set())

    def test_muted_profile_uses_matched_captions(self):
        data = example()
        cue = data['cues'][0]
        cue.update(kind='sound', sample={'above_ambience_db': 9}, alternative=None)
        data['cues'][1]['alternative'] = None
        self.assertEqual(failed(data), {'clue-layers', 'sensory-alternatives', 'discovery-pacing'})
        cue['alternative'] = {'channel': 'caption', 'beat': 'disruption', 'evidence': 'Dripping water echoes inside the drawers.'}
        self.assertEqual(failed(data), {'clue-layers'})
        for field, value in (('channel', 'audio-description'), ('beat', 'aside')):
            broken = deepcopy(data)
            broken['cues'][0]['alternative'][field] = value
            self.assertIn('sensory-alternatives', failed(broken))

    def test_pacing_uses_first_discovery_and_inclusive_exercise_windows(self):
        data = example()
        for index in (2, 3):
            data['cues'][index]['second'] = 0
        for entrance_dwell, passes in ((5, True), (4, False), (31, True), (32, False)):
            with self.subTest(entrance_dwell=entrance_dwell):
                data['rooms'][0]['dwell_s'] = entrance_dwell
                self.assertEqual('discovery-pacing' not in failed(data), passes)
        data = example()
        for cue in data['cues']:
            if cue['beat'] == 'response':
                cue.update(room='hoist', second=4)
        self.assertEqual(failed(data), set())
        for cue in data['cues']:
            if cue['beat'] == 'response':
                cue['second'] = 5
        self.assertEqual(failed(data), {'discovery-pacing'})

    def test_inaccessible_early_primary_can_still_trigger_its_timed_alternative(self):
        data = example()
        early = deepcopy(data['cues'][2])
        early.update(id='small_tag', room='vestibule', second=2, sample={'visible_glyph_px': 1})
        data['cues'].append(early)
        rows = reports(data)
        self.assertEqual(failed(data), {'primary-samples', 'discovery-pacing'})
        self.assertIn('audio-only', rows['discovery-pacing']['detail'])
        self.assertIn('4/6', rows['discovery-pacing']['detail'])

    def test_schema_rejects_unknown_fields_invalid_graphs_and_out_of_room_cues(self):
        for mutate in (
            lambda d: d.update(extra=True),
            lambda d: d['beats'].update(aside=d['beats']['disruption']),
            lambda d: d['rooms'][1].update(id='vestibule'),
            lambda d: d['rooms'][0]['next'].append('cart_bay'),
            lambda d: d['rooms'][0]['next'].append('unknown'),
            lambda d: d['rooms'][1].update(next=['vestibule']),
            lambda d: d['rooms'][-1].update(dwell_s=1),
            lambda d: d['cues'][0].update(room='loft_choice', second=0),
            lambda d: d['cues'][0].update(second=8),
            lambda d: d['cues'][0].update(second=False),
            lambda d: d['cues'][0].update(room='unknown'),
            lambda d: d['cues'][0].update(id='drips'),
            lambda d: d['cues'][0].update(kind=[]),
            lambda d: d['cues'][0].update(sample={'above_ambience_db': 8}),
            lambda d: d['cues'][0].update(sample={'visible_height_px': -1}),
            lambda d: d['cues'][0].update(evidence='\u200b'),
            lambda d: d['cues'][0].update(alternative=[]),
            lambda d: d['cues'][0]['alternative'].update(beat='unknown'),
            lambda d: d['cues'][0]['alternative'].update(evidence='x' * 141),
            lambda d: d.update(cues=d['cues'] * 9),
        ):
            with self.subTest(mutate=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess('diegetic-narrative', data)
        with self.assertRaises(ValueError):
            lab.assess('storytelling', example())
