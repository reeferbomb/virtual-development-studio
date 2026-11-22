from copy import deepcopy
import json
import unittest

from command_center import intelligence_audio as audio


def check(result, identifier):
    return next(item for item in result['checks'] if item['id'] == identifier)


class AudioIntelligenceTests(unittest.TestCase):
    def test_synthetic_example_is_fresh_replayable_and_json_finite(self):
        data = audio.example()
        original = deepcopy(data)
        result = audio.analyze(data)
        self.assertEqual(set(result), {'schema_version', 'kind', 'status', 'checks', 'metrics', 'advisory'})
        self.assertEqual((result['schema_version'], result['kind'], result['status']), (1, 'audio', 'pass'))
        self.assertTrue(all(set(c) == {'id', 'label', 'status', 'detail'} and c['status'] == 'pass'
                            for c in result['checks']))
        self.assertEqual(result['metrics']['essential_cue_occurrences'], 3)
        self.assertEqual(result['metrics']['minimum_quiet_peak_reduction_db'], 4.5)
        self.assertEqual(result['metrics']['minimum_headroom_db'], 1.8)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        self.assertEqual(audio.analyze(data), result)
        self.assertEqual(data, original)
        data['scenarios'].clear()
        self.assertEqual(audio.example(), original)

    def test_peak_ceiling_equality_warn_and_over_full_scale_fail(self):
        data = audio.example()
        for peak, expected in [(-1, 'pass'), (-.9999, 'warn'), (0, 'warn'), (.001, 'fail')]:
            with self.subTest(peak=peak):
                data['scenarios'][1]['standard']['peak_dbtp'] = peak
                result = audio.analyze(data)
                self.assertEqual(check(result, 'peak-headroom')['status'], expected)
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['metrics']['minimum_headroom_db'], -peak)
        data['scenarios'][1]['quiet']['peak_dbtp'] = 1
        result = audio.analyze(data)
        self.assertIn('scenario 2 (quiet)', check(result, 'peak-headroom')['detail'])

    def test_two_equal_stems_cost_three_db_of_margin(self):
        data = audio.example()
        mix = data['scenarios'][0]['standard']
        mix.update(dialogue_rms_dbfs=-18, music_rms_dbfs=-26, effects_rms_dbfs=-26)
        report = audio.analyze(data)
        self.assertAlmostEqual(report['metrics']['minimum_dialogue_margin_db']['standard'], 4.990, places=3)
        self.assertEqual(check(report, 'dialogue-margin')['status'], 'warn')
        mix['effects_rms_dbfs'] = None
        report = audio.analyze(data)
        self.assertEqual(report['metrics']['minimum_dialogue_margin_db']['standard'], 8)
        self.assertEqual(check(report, 'dialogue-margin')['status'], 'pass')

    def test_margin_checks_unrounded_values_and_failure_dominates(self):
        data = audio.example()
        mix = data['scenarios'][0]['quiet']
        mix.update(dialogue_rms_dbfs=-20, music_rms_dbfs=-26, effects_rms_dbfs=None)
        for level, expected in [(-26, 'pass'), (-25.9999, 'warn'), (-20, 'warn'), (-19.9999, 'fail')]:
            with self.subTest(level=level):
                mix['music_rms_dbfs'] = level
                report = audio.analyze(data)
                self.assertEqual(check(report, 'dialogue-margin')['status'], expected)
        data['scenarios'][0]['standard']['peak_dbtp'] = -.5
        result = audio.analyze(data)
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(check(result, 'peak-headroom')['status'], 'warn')

    def test_no_spoken_measurements_and_unopposed_speech_are_distinct(self):
        data = audio.example()
        for p in ('standard', 'quiet'):
            data['scenarios'][0][p].update(music_rms_dbfs=None, effects_rms_dbfs=None)
        result = audio.analyze(data)
        self.assertEqual(result['metrics']['minimum_dialogue_margin_db'], {'standard': None, 'quiet': None})
        self.assertEqual(result['metrics']['overlap_windows'], {'standard': 0, 'quiet': 0})
        self.assertEqual(check(result, 'dialogue-margin')['status'], 'pass')
        data['scenarios'][0]['quiet']['dialogue_rms_dbfs'] = None
        result = audio.analyze(data)
        self.assertEqual(check(result, 'dialogue-margin')['status'], 'warn')
        self.assertEqual(check(result, 'quiet-profile')['status'], 'warn')
        self.assertEqual(result['metrics']['dropped_quiet_speech_windows'], 1)

    def test_counts_each_expected_occurrence_by_profile_and_mode(self):
        data = audio.example()
        cues = data['scenarios'][0]['essential_cues']
        cues.append({'kind': 'speech', 'standard': ['visual'], 'quiet': ['haptic']})
        result = audio.analyze(data)
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['metrics']['essential_cue_occurrences'], 4)
        self.assertEqual(result['metrics']['delivered_cues'], {'standard': 3, 'quiet': 3})
        self.assertIn('scenario 1, cue 3 (standard)', check(result, 'essential-cues')['detail'])
        self.assertIn('scenario 1, cue 3', check(result, 'quiet-profile')['detail'])
        cues[-1]['standard'] = ['caption']
        cues[-1]['quiet'] = ['audio']
        result = audio.analyze(data)
        self.assertEqual(check(result, 'essential-cues')['status'], 'pass')
        self.assertEqual(check(result, 'quiet-profile')['status'], 'fail')
        cues[-1]['quiet'] = ['caption']
        data['scenarios'][0]['standard']['dialogue_rms_dbfs'] = None
        result = audio.analyze(data)
        self.assertIn('scenario 1, cue 1 (standard)', check(result, 'essential-cues')['detail'])
        self.assertEqual(result['metrics']['delivered_cues']['standard'], 3)

    def test_empty_cue_inventory_and_absent_delivery(self):
        data = audio.example()
        for scene in data['scenarios']:
            scene['essential_cues'] = []
        report = audio.analyze(data)
        self.assertEqual(check(report, 'essential-cues')['status'], 'warn')
        self.assertEqual(check(report, 'quiet-profile')['status'], 'warn')
        data['scenarios'][0]['essential_cues'].append({'kind': 'signal', 'standard': ['visual'], 'quiet': []})
        report = audio.analyze(data)
        self.assertEqual(check(report, 'essential-cues')['status'], 'fail')
        self.assertEqual(check(report, 'quiet-profile')['status'], 'fail')

    def test_quiet_reduction_is_paired_and_checks_worst_scene(self):
        data = audio.example()
        standard = data['scenarios'][0]['standard']['peak_dbtp']
        for reduction, expected in [(4.001, 'pass'), (4, 'pass'), (3.999, 'warn'), (0, 'warn'), (-.01, 'fail')]:
            with self.subTest(reduction=reduction):
                data['scenarios'][0]['quiet']['peak_dbtp'] = standard - reduction
                report = audio.analyze(data)
                self.assertEqual(check(report, 'quiet-profile')['status'], expected)
                self.assertAlmostEqual(report['metrics']['minimum_quiet_peak_reduction_db'], reduction)
        # Compare each scenario against its own standard peak even when the absolute peaks change order.
        data['scenarios'][1]['standard']['peak_dbtp'] = -25
        data['scenarios'][1]['quiet']['peak_dbtp'] = -21
        self.assertEqual(audio.analyze(data)['metrics']['minimum_quiet_peak_reduction_db'], -4)

    def test_schema_rejects_nonfinite_values_duplicates_and_unknown_identity_fields(self):
        bad = (
            lambda d: d.update(schema_version=1),
            lambda d: d.update(scenarios=[]),
            lambda d: d.update(scenarios=d['scenarios'] * 17),
            lambda d: d['targets'].update(peak_ceiling_dbtp=None),
            lambda d: d['targets'].update(min_dialogue_margin_db=-.01),
            lambda d: d['targets'].update(quiet_peak_reduction_db=0),
            lambda d: d['scenarios'][0].update(name='unexpected'),
            lambda d: d['scenarios'][0]['standard'].update(clip_id='no'),
            lambda d: d['scenarios'][0]['standard'].update(peak_dbtp=float('nan')),
            lambda d: d['scenarios'][0]['quiet'].update(peak_dbtp=float('inf')),
            lambda d: d['scenarios'][0]['quiet'].update(music_rms_dbfs=10**1000),
            lambda d: d['scenarios'][0]['standard'].update(peak_dbtp=-121),
            lambda d: d['scenarios'][0]['standard'].update(dialogue_rms_dbfs=True),
            lambda d: d['scenarios'][0]['quiet'].update(effects_rms_dbfs='-12'),
            lambda d: d['scenarios'][0]['essential_cues'][0].update(kind='speaker_name'),
            lambda d: d['scenarios'][0]['essential_cues'][0].update(quiet=['visual', 'visual']),
            lambda d: d['scenarios'][0]['essential_cues'][0].update(quiet=[{}]),
            lambda d: d['scenarios'][0]['essential_cues'][0].update(quiet=['other']),
            lambda d: d['scenarios'][0]['essential_cues'][0].update(quiet='caption'),
            lambda d: d['scenarios'][0]['essential_cues'][0].pop('standard'),
            lambda d: d['scenarios'][0].update(essential_cues=[{}] * 33),
        )
        for mutate in bad:
            with self.subTest(mutation=mutate):
                data = audio.example()
                mutate(data)
                with self.assertRaises(ValueError):
                    audio.analyze(data)
        for invalid in [None, [], 'measurements', {}]:
            with self.assertRaises(ValueError):
                audio.analyze(invalid)
