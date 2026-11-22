from copy import deepcopy
import json
import unittest

from command_center.intelligence_frame import analyze, example


def scenario(frames, **budget):
    row = {'name': 'North concourse', 'target_fps': 60, 'frame_times_us': frames}
    if budget:
        row['budget'] = budget
    return row


def single(frames, **budget):
    return analyze({'scenarios': [scenario(frames, **budget)]})


def only(report):
    return report['metrics']['scenarios'][0]


class FrameIntelligenceTests(unittest.TestCase):
    def test_example_schema_repeatability_and_advisory_limits(self):
        data = example()
        original = deepcopy(data)
        report = analyze(data)
        self.assertEqual(data, original)
        self.assertEqual(report, analyze(original))
        self.assertEqual(set(report), {'schema_version', 'kind', 'status', 'checks', 'metrics', 'advisory'})
        self.assertEqual((report['schema_version'], report['kind'], report['status']), (1, 'frame', 'warn'))
        self.assertEqual(len(report['checks']), len({check['id'] for check in report['checks']}))
        for check in report['checks']:
            self.assertEqual(set(check), {'id', 'label', 'status', 'detail'})
            self.assertIn(check['status'], ('pass', 'warn', 'fail'))
            self.assertTrue(check['detail'] and check['label'])
        self.assertIn('hardware', report['advisory'])
        self.assertIn('cause', report['advisory'])
        self.assertIn('release', report['advisory'])
        self.assertEqual(report, json.loads(json.dumps(report, allow_nan=False)))
        data['scenarios'].clear()
        self.assertEqual(example(), original)

    def test_nearest_ranks_inclusive_thresholds_and_earliest_worst_index(self):
        frames = [16_000] * 95 + [17_000] * 4 + [22_000]
        report = single(frames, max_p95_us=16_000, max_p99_us=17_000, max_frame_us=22_000,
                        max_late_bps=500, max_late_run=5)
        metrics = only(report)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual((metrics['target_period_us'], metrics['p95_us'], metrics['p99_us'], metrics['max_us']),
                         (16667, 16000, 17000, 22000))
        self.assertEqual(metrics['worst_frame_index'], 99)
        self.assertEqual(metrics['late_bps'], 500)
        self.assertEqual(metrics['observed_time_us'], sum(frames))
        self.assertEqual(only(single([31_000, 15_000, 31_000]))['worst_frame_index'], 0)

    def test_each_optional_budget_fails_independently_on_breach(self):
        frames = [16_000] * 95 + [17_000] * 4 + [22_000]
        for budget, failed_lane in [({'max_p95_us': 15999}, 'pacing'), ({'max_p99_us': 16999}, 'pacing'),
                                    ({'max_frame_us': 21999}, 'pacing'), ({'max_late_bps': 499}, 'stutter'),
                                    ({'max_late_run': 4}, 'stutter')]:
            with self.subTest(budget=budget):
                report = single(frames, **budget)
                self.assertEqual(report['status'], 'fail')
                self.assertEqual({c['id'] for c in report['checks'] if c['status'] == 'fail'},
                                 {f'frame-1-{failed_lane}'})

    def test_shared_frame_target_uses_rounded_period_and_ceiling_share(self):
        report = single([16_667, 16_668, 16_667], min_samples=3, max_p95_us=16668,
                        max_late_bps=3334, max_late_run=1)
        metrics = only(report)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual((metrics['late_frames'], metrics['late_bps'], metrics['longest_late_run']), (1, 3334, 1))
        self.assertEqual(metrics['stutter_runs'], [])
        self.assertEqual(single([16_667, 16_668, 16_667], max_late_bps=3333)['status'], 'fail')

    def test_indexed_runs_are_ordered_bounded_and_include_trailing_cluster(self):
        frames = [16_668, 18_000, 15_000] * 6 + [16_670, 17_000, 19_000]
        metrics = only(single(frames, max_p95_us=19000))
        self.assertEqual((metrics['stutter_run_count'], len(metrics['stutter_runs']), metrics['omitted_runs']), (7, 5, 2))
        self.assertEqual(metrics['stutter_runs'][0],
                         {'start_index': 18, 'end_exclusive': 21, 'frames': 3, 'max_us': 19000})
        self.assertEqual([r['start_index'] for r in metrics['stutter_runs'][1:]], [0, 3, 6, 9])

    def test_single_hitch_survives_percentiles_and_can_have_an_explicit_limit(self):
        frames = [15_000] * 100 + [60_000]
        report = single(frames)
        self.assertEqual(report['status'], 'warn')
        self.assertEqual((only(report)['p99_us'], only(report)['max_us']), (15000, 60000))
        self.assertEqual(only(report)['stutter_run_count'], 0)
        self.assertEqual(single(frames, max_frame_us=60_000)['status'], 'pass')
        self.assertEqual(single(frames, max_frame_us=59_999)['status'], 'fail')

    def test_short_and_empty_captures_never_mask_a_real_budget_violation(self):
        report = single([])
        self.assertEqual(report['status'], 'warn')
        for name in ('p95_us', 'p99_us', 'max_us', 'late_bps', 'worst_frame_index', 'longest_late_run'):
            self.assertIsNone(only(report)[name])
        short = single([10_000])
        self.assertEqual(short['status'], 'warn')
        self.assertEqual(only(short)['p99_us'], 10_000)
        self.assertEqual(single([10_000], min_samples=1)['status'], 'pass')
        insufficient_failure = single([70_000])
        self.assertEqual(insufficient_failure['status'], 'fail')
        self.assertTrue(any(c['id'].endswith('coverage') and c['status'] == 'warn'
                            for c in insufficient_failure['checks']))

    def test_distinct_scenarios_keep_separate_denominators_targets_and_runs(self):
        first = scenario([15_000] * 99 + [20_000])
        second = scenario([20_000] + [24_000] * 99)
        second.update(name='Glass roof', target_fps=40)
        report = analyze({'scenarios': [first, second]})
        self.assertEqual(report['metrics']['sample_count'], 200)
        self.assertEqual(report['metrics']['scenario_count'], 2)
        self.assertEqual(report['status'], 'pass')
        self.assertEqual([r['late_frames'] for r in report['metrics']['scenarios']], [1, 0])
        self.assertEqual([r['stutter_run_count'] for r in report['metrics']['scenarios']], [0, 0])
        second['target_fps'] = 120
        self.assertEqual(analyze({'scenarios': [first, second]})['status'], 'fail')

    def test_strict_schema_rejects_invalid_frames_names_limits_and_extra_fields(self):
        for bad in (None, [], {}, {'scenarios': []}, {'scenarios': [None]},
                    {'scenarios': [scenario([])], 'kind': 'frame'}):
            with self.subTest(data=bad), self.assertRaises(ValueError):
                analyze(bad)
        for field, value in [('name', None), ('name', ' '), ('name', 'Two\nlines'), ('name', 'a' * 65),
                             ('target_fps', True), ('target_fps', 0), ('target_fps', 59.94),
                             ('frame_times_us', '16000'), ('frame_times_us', [0]), ('frame_times_us', [None]),
                             ('frame_times_us', [True]), ('frame_times_us', [float('nan')]), ('frame_times_us', [10_000_001]),
                             ('budget', None), ('budget', {'min_samples': False}), ('budget', {'max_late_bps': 10001}),
                             ('budget', {'new_rule': 7}), ('unexpected', 'field')]:
            with self.subTest(field=field, value=value):
                row = scenario([16000])
                row[field] = value
                with self.assertRaises(ValueError):
                    analyze({'scenarios': [row]})
        with self.assertRaises(ValueError):
            analyze({'scenarios': [scenario([]), dict(scenario([]), name='NORTH CONCOURSE')]})

    def test_size_limits_reject_oversized_requests(self):
        with self.assertRaises(ValueError):
            single([15_000] * 4097)
        with self.assertRaises(ValueError):
            analyze({'scenarios': [dict(scenario([]), name=str(i)) for i in range(17)]})
        with self.assertRaises(ValueError):
            analyze({'scenarios': [dict(scenario([15_000] * n), name=str(i)) for i, n in enumerate((4096, 4096, 1))]})
        at_limit = analyze({'scenarios': [dict(scenario([15_000] * 4096), name=str(i)) for i in range(2)]})
        self.assertEqual(at_limit['metrics']['sample_count'], 8192)
        self.assertEqual(at_limit['status'], 'pass')


if __name__ == '__main__':
    unittest.main()
