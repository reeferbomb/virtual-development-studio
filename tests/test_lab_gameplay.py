from copy import deepcopy
import unittest

from command_center.lab_gameplay import EXERCISES, assess


def example(track):
    return deepcopy(next(item['example'] for item in EXERCISES if item['id'] == track))


def statuses(track, submission):
    return {row['id']: row['status'] for row in assess(track, submission)}


class GameplayLabTests(unittest.TestCase):
    def test_published_examples_match_rubrics_and_are_replayable(self):
        self.assertEqual([x['id'] for x in EXERCISES],
                         ['game-development', 'quality-assurance', 'build-performance'])
        for item in EXERCISES:
            with self.subTest(track=item['id']):
                original = example(item['id'])
                submission = deepcopy(original)
                results = assess(item['id'], submission)
                self.assertEqual([r['id'] for r in results], [c['id'] for c in item['criteria']])
                self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in results))
                self.assertEqual(assess(item['id'], submission), results)
                self.assertEqual(submission, original)

    def test_inventory_replays_counts_after_erroneous_prediction(self):
        track = 'game-development'
        data = example(track)
        data['steps'][0]['expected_count'] += 1
        result = statuses(track, data)
        self.assertEqual(result, {'transitions': 'fail', 'rejections': 'pass', 'persistence': 'pass'})

    def test_invalid_move_and_unchanged_snapshot(self):
        track = 'game-development'
        steps = example(track)['steps']
        rejected = next(s for s in steps if s['op'] == 'take' and not s['accepted'])
        rejected['expected_count'] = 0
        self.assertEqual(statuses(track, {'steps': steps})['rejections'], 'fail')
        idle = [{'op': 'save', 'expected_count': 0, 'accepted': True},
                {'op': 'load', 'expected_count': 0, 'accepted': True}]
        self.assertEqual(set(statuses(track, {'steps': idle}).values()), {'fail'})
        self.assertEqual(set(statuses(track, {'steps': []}).values()), {'fail'})

    def test_save_overwrite_and_load_before_save(self):
        track = 'game-development'
        ops = [('load', None, False, 0), ('save', None, True, 0), ('take', 3, True, 3),
               ('save', None, True, 3), ('drop', 2, True, 1), ('load', None, True, 3)]
        steps = [dict(op=op, accepted=ok, expected_count=n, **({} if q is None else {'units': q}))
                 for op, q, ok, n in ops]
        self.assertEqual(statuses(track, {'steps': steps})['persistence'], 'pass')
        steps[-1]['expected_count'] = 0
        self.assertEqual(statuses(track, {'steps': steps})['persistence'], 'fail')

    def test_qa_checks_requirement_trace_actuals_and_regression_independently(self):
        track = 'quality-assurance'
        data = example(track)
        data['cases'][0]['requirement'] = 'repeat-light'
        self.assertEqual(statuses(track, data)['traceability'], 'fail')
        data = example(track)
        row = next(row for row in data['cases'] if row['requirement'] == 'checkpoint-light')
        row['actual_rewards'] = row['expected_rewards']
        self.assertEqual(statuses(track, data), {'traceability': 'pass', 'observations': 'fail',
                                                 'regression': 'pass'})
        data = example(track)
        data['regression'].update(steps=['light', 'light'], broken_rewards=1, fixed_rewards=1)
        self.assertEqual(statuses(track, data)['regression'], 'fail')

    def test_qa_replays_extended_regression_from_clean_state(self):
        track = 'quality-assurance'
        data = example(track)
        data['regression'].update(steps=['load', 'light', 'save', 'load', 'light', 'save', 'load', 'light'],
                                  broken_rewards=3, fixed_rewards=1, expected_rewards=1)
        self.assertEqual(statuses(track, data)['regression'], 'pass')
        data['regression']['broken_rewards'] = 2
        self.assertEqual(statuses(track, data)['regression'], 'fail')
        data['cases'] = []
        self.assertEqual(statuses(track, data)['observations'], 'fail')

    def test_performance_comparability_and_metrics(self):
        track = 'build-performance'
        data = example(track)
        data['optimized']['device'] = 'Other device'
        self.assertEqual(statuses(track, data), {'comparability': 'fail', 'summary': 'pass',
                                                 'budgets': 'fail'})
        data = example(track)
        data['summary']['optimized_peak_mib'] += 1
        self.assertEqual(statuses(track, data)['summary'], 'fail')
        data = example(track)
        data['optimized']['samples'].pop()
        self.assertEqual(statuses(track, data)['comparability'], 'fail')

    def test_nearest_rank_excludes_only_the_tail_and_memory_uses_the_peak(self):
        track = 'build-performance'
        data = example(track)
        for stage, ms, mib in [('baseline', 20, 270), ('optimized', 17, 256)]:
            data[stage]['samples'] = [{'frame_ms': ms, 'memory_mib': mib - 1} for _ in range(19)]
            data[stage]['samples'].insert(0, {'frame_ms': 300, 'memory_mib': mib})
            data['summary'][stage + '_p95_ms'] = ms
            data['summary'][stage + '_peak_mib'] = mib
        self.assertEqual(set(statuses(track, data).values()), {'pass'})
        data['optimized']['samples'][1]['frame_ms'] = 18
        self.assertEqual(statuses(track, data)['budgets'], 'fail')
        data['optimized']['samples'][1]['frame_ms'] = 16
        data['optimized']['samples'][4]['memory_mib'] = 257
        self.assertEqual(statuses(track, data)['budgets'], 'fail')

    def test_unimproved_capture_fails_budget_exercise(self):
        track = 'build-performance'
        data = example(track)
        data['baseline'] = deepcopy(data['optimized'])
        self.assertEqual(statuses(track, data)['budgets'], 'fail')

    def test_malformed_data_is_a_value_error(self):
        for track, mutate in [
            ('game-development', lambda d: d.update(extra={})),
            ('game-development', lambda d: d['steps'][0].update(units=True)),
            ('game-development', lambda d: d['steps'][0].update(accepted=1)),
            ('game-development', lambda d: d['steps'][0].update(op=[])),
            ('game-development', lambda d: d.update(steps=d['steps'] * 100)),
            ('quality-assurance', lambda d: d['cases'][0].update(build='unknown')),
            ('quality-assurance', lambda d: d['regression'].update(steps=['light'] * 100)),
            ('quality-assurance', lambda d: d['regression'].update(steps=['light', {}])),
            ('build-performance', lambda d: d['baseline'].update(samples=[])),
            ('build-performance', lambda d: d['optimized'].update(width=1.5)),
            ('build-performance', lambda d: d['optimized'].update(device='a' * 1000)),
            ('build-performance', lambda d: d['optimized']['samples'][0].update(frame_ms=float('nan'))),
            ('build-performance', lambda d: d['optimized']['samples'][0].update(memory_mib=True)),
            ('build-performance', lambda d: d['summary'].update(baseline_p95_ms=float('inf'))),
        ]:
            with self.subTest(track=track, mutation=mutate):
                data = example(track)
                mutate(data)
                with self.assertRaises(ValueError):
                    assess(track, data)
        for invalid in ('invalid', [], None):
            with self.assertRaises(ValueError):
                assess(invalid, {})
