from copy import deepcopy
import unittest

from command_center import lab_audio


def example():
    return deepcopy(lab_audio.EXERCISES[0]['example'])


def results(plan):
    return {row['id']: row for row in lab_audio.assess('game-audio', plan)}


class AudioPracticeTests(unittest.TestCase):
    def test_track_and_fixture_contract(self):
        track = lab_audio.TRACK
        self.assertEqual(set(track), {'id', 'title', 'roles', 'workflow', 'deliverables', 'verification', 'exercise'})
        self.assertEqual(track['roles'], ['content', 'gameplay', 'ui', 'verification'])
        exercise, = lab_audio.EXERCISES
        self.assertEqual(track['id'], exercise['id'])
        self.assertEqual(set(exercise), {'id', 'title', 'brief', 'criteria', 'example'})
        plan = example()
        rows = lab_audio.assess('game-audio', plan)
        self.assertEqual([row['id'] for row in rows], [c['id'] for c in exercise['criteria']])
        self.assertTrue(all(set(row) == {'id', 'status', 'detail'} and row['status'] == 'pass' for row in rows), rows)
        self.assertEqual(plan, example())
        plan['events'].reverse()
        plan['assets'].reverse()
        self.assertEqual(rows, lab_audio.assess('game-audio', plan))

    def test_headroom_sums_concurrent_amplitudes_even_between_observations(self):
        plan = example()
        plan['bus_gain_db'] = {'dialogue': -6, 'effects': -6, 'ambience': -6}
        for asset in plan['assets']:
            asset['peak_dbfs'] = 0
        plan['observations'] = []
        # The example has exactly one voice on each bus at the hottest point.
        # Two at -6 dB and one at -15 dB give +1.44 dBFS.
        report = results(plan)
        self.assertEqual(report['headroom']['status'], 'fail')
        self.assertIn('+1.44 dBFS', report['headroom']['detail'])
        self.assertEqual(report['playback']['status'], 'fail')

    def test_headroom_boundary_and_close_overage(self):
        plan = example()
        effect = next(row for row in plan['events'] if row['id'] == 'chime')
        plan['events'] = [effect]
        plan['bus_gain_db']['effects'] = 0
        self.assertEqual(results(plan)['headroom']['status'], 'pass')
        self.assertIn('-3.00 dBFS', results(plan)['headroom']['detail'])
        plan['bus_gain_db']['effects'] = -6
        plan['events'].append(dict(effect, id='second'))
        self.assertEqual(results(plan)['headroom']['status'], 'fail')
        self.assertIn('-2.98 dBFS', results(plan)['headroom']['detail'])

    def test_distinct_loop_wrap_requires_its_own_observation(self):
        plan = example()
        plan['assets'][0]['duration_ms'] = 900
        for row in plan['observations']:
            if 'bed' in row['playheads_ms']:
                row['playheads_ms']['bed'] = row['at_ms'] % 900
        self.assertEqual(results(plan)['playback']['status'], 'fail')
        plan['observations'].append({'at_ms': 900, 'ambience_duck_db': 0, 'playheads_ms': {'bed': 0}})
        # A time-shifted independent plan also passes across the full rubric.
        for field in ('events', 'subtitles', 'ducking'):
            for row in plan[field]:
                row['start_ms'] += 325
                row['end_ms'] += 325
        for row in plan['observations']:
            row['at_ms'] += 325
        self.assertTrue(all(row['status'] == 'pass' for row in results(plan).values()))

    def test_simultaneous_restart_uses_half_open_intervals(self):
        plan = example()
        effect = next(cue for cue in plan['events'] if cue['id'] == 'chime')
        plan['events'].append(dict(effect, id='echo', start_ms=effect['end_ms'],
                                   end_ms=effect['end_ms'] + 200))
        self.assertEqual(results(plan)['headroom'], results(example())['headroom'])

    def test_unrouted_assets_and_dangling_cues_fail(self):
        plan = example()
        plan['assets'].append(dict(plan['assets'][0], id='orphan'))
        self.assertEqual(results(plan)['routing']['status'], 'fail')
        plan['events'][0]['asset'] = 'unknown'
        report = results(plan)
        self.assertEqual(report['routing']['status'], 'fail')
        self.assertEqual(report['headroom']['status'], 'fail')

    def test_provenance_requires_credit_and_source_fingerprint(self):
        for field, value in [('source', '  '), ('credit', '\u200b'), ('license', ''), ('source', '\u034f'), ('sha256', 'xyz')]:
            with self.subTest(field=field):
                plan = example()
                plan['assets'][0][field] = value
                self.assertEqual(results(plan)['provenance']['status'], 'fail')

    def test_subtitle_timing_follows_interruption_and_dialogue_coverage(self):
        plan = example()
        caption = plan['subtitles'][-1]
        caption['end_ms'] += 101
        self.assertEqual(results(plan)['subtitles']['status'], 'fail')
        caption['end_ms'] -= 1
        self.assertEqual(results(plan)['subtitles']['status'], 'pass')
        caption['event'] = 'chime'
        self.assertEqual(results(plan)['subtitles']['status'], 'fail')
        plan['subtitles'] = []
        self.assertEqual(results(plan)['subtitles']['status'], 'fail')

    def test_ducking_checks_gaps_depth_bed_coverage_and_restoration(self):
        for change in [dict(end_ms=2499), dict(end_ms=2501), dict(gain_db=-5)]:
            with self.subTest(change=change):
                plan = example()
                plan['ducking'][0].update(change)
                self.assertEqual(results(plan)['ducking']['status'], 'fail')
        plan = example()
        plan['events'][0]['end_ms'] = 3200
        self.assertEqual(results(plan)['ducking']['status'], 'fail')

    def test_playback_checks_phase_boundaries_and_release(self):
        plan = example()
        wrapped = next(row for row in plan['observations'] if row['at_ms'] == 1000)
        wrapped['playheads_ms']['bed'] = 1000
        self.assertEqual(results(plan)['playback']['status'], 'fail')
        wrapped['playheads_ms']['bed'] = 0
        wrapped['ambience_duck_db'] = 0
        self.assertEqual(results(plan)['playback']['status'], 'fail')
        plan = example()
        plan['observations'].pop()
        self.assertEqual(results(plan)['playback']['status'], 'fail')
        plan = example()
        stopped = next(row for row in plan['observations'] if row['at_ms'] == 3500)
        stopped['playheads_ms']['warning'] = 500
        self.assertEqual(results(plan)['playback']['status'], 'fail')

    def test_transport_rejects_early_completion_false_interrupt_and_no_wrap(self):
        for cue, change in [('call', dict(end_ms=2499)), ('warning', dict(ending='complete')),
                            ('chime', dict(ending='interrupt')), ('bed', dict(end_ms=1000))]:
            with self.subTest(cue=cue):
                plan = example()
                next(row for row in plan['events'] if row['id'] == cue).update(change)
                self.assertEqual(results(plan)['transport']['status'], 'fail')

    def test_bounded_unambiguous_schema(self):
        cases = [
            ('events', 0, 'end_ms', True), ('events', 0, 'start_ms', -1),
            ('assets', 0, 'peak_dbfs', float('nan')), ('assets', 0, 'loop', 1),
            ('assets', 0, 'source', 'x' * 300), ('events', 0, 'id', 'INVALID'),
            ('ducking', 0, 'end_ms', 999), ('observations', 0, 'playheads_ms', []),
        ]
        for key, index, field, value in cases:
            with self.subTest(key=key, field=field), self.assertRaises(ValueError):
                plan = example()
                plan[key][index][field] = value
                results(plan)
        for key in ['assets', 'events', 'observations', 'ducking']:
            with self.subTest(key=key), self.assertRaises(ValueError):
                plan = example()
                plan[key].append(dict(plan[key][0]))
                results(plan)
        for value in [[], {**example(), 'unrecognized': 1}, {**example(), 'events': [{}] * 33}]:
            with self.assertRaises(ValueError):
                results(value)
        with self.assertRaises(ValueError):
            lab_audio.assess('other', {})


if __name__ == '__main__':
    unittest.main()
