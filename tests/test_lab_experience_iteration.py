from copy import deepcopy
import unittest

from command_center import lab_experience_iteration as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def results(data):
    return {row['id']: row for row in lab.assess('experience-iteration', data)}


def failed(data):
    return {key for key, row in results(data).items() if row['status'] == 'fail'}


class ExperienceIterationLabTests(unittest.TestCase):
    def test_teaching_example_is_deterministic_and_matches_public_rubric(self):
        data = example()
        self.assertEqual(lab.TRACK['id'], 'experience-iteration')
        checks = results(data)
        self.assertEqual(list(checks), [row['id'] for row in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(row['status'] == 'pass' and row['detail'] for row in checks.values()))
        self.assertEqual(checks, results(data))
        self.assertEqual(data, example())

    def test_capture_provenance_requires_every_context_and_exact_build(self):
        for field in ('build_sha256', 'device_sha256', 'scene_sha256', 'workload_sha256', 'settings_sha256'):
            with self.subTest(field=field):
                data = example()
                data['tiers']['minimum']['iteration'][field] = '0' * 64
                checks = results(data)
                self.assertEqual(checks['evidence-match']['status'], 'fail')
                self.assertIn(field, checks['evidence-match']['detail'])
                for key in ('frame-pacing', 'input-response', 'regression-budgets', 'playtest-iteration'):
                    self.assertEqual(checks[key]['status'], 'fail')
                    self.assertIn('matched', checks[key]['detail'])

    def test_capture_pair_rejects_reuse_and_different_sample_counts(self):
        for mutate in (
            lambda d: d['tiers']['minimum']['iteration'].update(
                capture_sha256=d['tiers']['recommended']['baseline']['capture_sha256']),
            lambda d: d['builds'].update(iteration=d['builds']['baseline']),
            lambda d: d['tiers']['minimum']['iteration']['frame_intervals_us'].append(20_000),
            lambda d: d['tiers']['minimum']['iteration']['input_feedback_us'].append(20_000),
        ):
            with self.subTest(mutation=mutate):
                data = example()
                mutate(data)
                self.assertIn('evidence-match', failed(data))

    def test_profiles_cover_distinct_hardware_and_presets_and_fit_display(self):
        data = example()
        data['tiers']['minimum']['display_hz'] = 24
        self.assertIn('tier-coverage', failed(data))
        for field in ('device_sha256', 'preset', 'settings_sha256'):
            with self.subTest(field=field):
                data = example()
                data['tiers']['minimum'][field] = data['tiers']['recommended'][field]
                self.assertIn('tier-coverage', failed(data))

    def test_frame_pacing_catches_tail_spikes_that_an_average_can_hide(self):
        data = example()
        frames = data['tiers']['minimum']['iteration']['frame_intervals_us']
        frames[-1] = 100_000
        self.assertLess(sum(frames) / len(frames), 33_334)
        self.assertTrue({'frame-pacing', 'regression-budgets'} <= failed(data))
        data = example()
        tier = data['tiers']['recommended']
        target_us = 16_667
        tier['baseline']['frame_intervals_us'] = [target_us] * 60
        tier['iteration']['frame_intervals_us'] = [target_us] * 60
        self.assertNotIn('frame-pacing', failed(data))
        tier['budgets']['late_frames_bps'] = 0
        tier['iteration']['frame_intervals_us'][-1] += 1
        check = results(data)['frame-pacing']
        self.assertEqual(check['status'], 'fail')
        self.assertIn('167', check['detail'])

    def test_controls_track_missed_inputs_and_p95_latency(self):
        data = example()
        tier = data['tiers']['recommended']
        tier['iteration']['input_feedback_us'][-1] = None
        check = results(data)['input-response']
        self.assertEqual(check['status'], 'fail')
        self.assertIn('1 missed', check['detail'])
        data = example()
        inputs = data['tiers']['recommended']['iteration']['input_feedback_us']
        inputs[-2:] = [150_000, 160_000]
        check = results(data)['input-response']
        self.assertEqual(check['status'], 'fail')
        self.assertIn('150000', check['detail'])

    def test_passing_absolute_budget_can_still_regress(self):
        data = example()
        tier = data['tiers']['recommended']
        worst = max(tier['baseline']['frame_intervals_us'])
        tier['iteration']['frame_intervals_us'][-1] = worst + tier['regressions']['worst_frame_us']
        self.assertNotIn('regression-budgets', failed(data))
        tier['iteration']['frame_intervals_us'][-1] += 1
        self.assertEqual(failed(data), {'regression-budgets'})

    def test_playtest_change_needs_exact_pair_and_improvement(self):
        data = example()
        data['playtest']['baseline_capture_sha256'] = data['tiers']['recommended']['baseline']['capture_sha256']
        self.assertEqual(failed(data), {'playtest-iteration'})
        data = example()
        match = data['tiers']['minimum']
        before = match['baseline']['input_feedback_us'][0]
        minimum = data['playtest']['minimum_improvement']
        match['iteration']['input_feedback_us'] = [before - minimum] * 20
        self.assertEqual(failed(data), set())
        match['iteration']['input_feedback_us'] = [before - minimum + 1] * 20
        self.assertEqual(failed(data), {'playtest-iteration'})

    def test_shapes_values_and_the_synthetic_scope_are_strict(self):
        for mutate in (
            lambda d: d.update(evidence='device'),
            lambda d: d.update(fun_verdict='approved'),
            lambda d: d.update(tiers=[]),
            lambda d: d['tiers'].pop('minimum'),
            lambda d: d['scenario'].update(scene_sha256='A' * 64),
            lambda d: d['tiers']['minimum'].update(target_fps=True),
            lambda d: d['tiers']['minimum']['regressions'].update(frame_p95_us=100_000),
            lambda d: d['tiers']['minimum']['iteration'].update(frame_intervals_us=[1] * 59),
            lambda d: d['tiers']['minimum']['iteration'].update(frame_intervals_us=[1] * 1025),
            lambda d: d['tiers']['minimum']['iteration']['frame_intervals_us'].__setitem__(0, 1.5),
            lambda d: d['tiers']['minimum']['iteration']['input_feedback_us'].__setitem__(0, True),
            lambda d: d['playtest'].update(metric=[]),
            lambda d: d['playtest'].update(metric='late_frames_bps', minimum_improvement=10_001),
            lambda d: d['playtest'].update(observation='\u200b\u200c'),
            lambda d: d['playtest'].update(human_retest='a' * 481),
        ):
            with self.subTest(mutation=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess('experience-iteration', data)
        with self.assertRaises(ValueError):
            lab.assess('unknown-exercise', example())


if __name__ == '__main__':
    unittest.main()
