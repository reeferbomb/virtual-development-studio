from copy import deepcopy
import json
import unittest

from command_center.intelligence_balance import analyze, example


def fixture(left, right, **constraints):
    builds = ['glass', 'cork']
    scenario = {'id': 'mosaic', 'trials': len(left), **constraints}
    rows = []
    for build, results in zip(builds, (left, right), strict=True):
        for i, result in enumerate(results, 1):
            won = type(result) is int
            rows.append(dict(build=build, scenario='mosaic', trial=i,
                             outcome='win' if won else result, win_ms=result if won else None))
    return dict(schema_version=1, source='production', scenarios=[scenario], builds=builds, rows=rows)


def statuses(report):
    return {check['id']: check['status'] for check in report['checks']}


class IntelligenceBalanceTests(unittest.TestCase):
    def test_example_is_fresh_has_tradeoffs_and_is_order_independent(self):
        data = example()
        original = deepcopy(data)
        report = analyze(data)
        self.assertEqual(original, data)
        self.assertEqual(set(report), {'schema_version', 'kind', 'status', 'checks', 'metrics', 'advisory'})
        self.assertEqual((report['schema_version'], report['kind'], report['status']), (1, 'balance', 'pass'))
        self.assertEqual(set(statuses(report).values()), {'pass'})
        self.assertTrue(all(set(c) == {'id', 'label', 'status', 'detail'} for c in report['checks']))
        self.assertEqual(report['metrics']['compared_pairs'], 3)
        self.assertEqual(report['metrics']['observed_rows'], 18)
        self.assertEqual(json.loads(json.dumps(report, allow_nan=False)), report)
        for key in ('builds', 'scenarios', 'rows'):
            data[key].reverse()
        self.assertEqual(analyze(data), report)
        self.assertEqual(example(), original)

    def test_mixed_outcomes_use_win_time_only_and_pair_equal_conditions(self):
        data = fixture([100, 'loss', 600], [100, 150, 'timeout'])
        report = analyze(data)
        self.assertEqual(report['status'], 'pass')
        pair, = report['metrics']['pair_results']
        self.assertEqual((pair['left_better'], pair['right_better'], pair['tied'], pair['dominant']), (1, 1, 1, None))
        cell = next(c for c in report['metrics']['cells'] if c['build'] == 'glass')
        self.assertEqual((cell['wins'], cell['losses'], cell['timeouts'], cell['median_win_ms']), (2, 1, 0, 350))

    def test_no_strict_advantage_when_every_trial_ties(self):
        report = analyze(fixture([110, 'timeout', 220], [110, 'loss', 220]))
        self.assertEqual(report['status'], 'pass')
        self.assertEqual(report['metrics']['pair_results'][0]['tied'], 3)

    def test_dominance_is_advisory_and_faster_measured_wins_matter(self):
        report = analyze(fixture([70, 75, 'timeout'], [70, 95, 'loss']))
        self.assertEqual(statuses(report), {'coverage': 'pass', 'viability': 'pass', 'dominance': 'warn'})
        self.assertEqual(report['status'], 'warn')
        self.assertEqual(report['metrics']['pair_results'][0]['dominant'], 'glass')

    def test_no_qualifying_wins_fail_even_when_the_raw_wins_are_fast_relative_to_peers(self):
        report = analyze(fixture([1001, 1010, 1200], ['loss', 'timeout', 'loss'], max_win_ms=1000))
        self.assertEqual(report['status'], 'fail')
        cells = report['metrics']['cells']
        self.assertEqual([c['viability'] for c in cells], ['below-target', 'below-target'])
        self.assertIsNone(cells[0]['median_win_ms'])
        self.assertEqual(cells[1]['wins'], 3)
        self.assertEqual(cells[1]['qualifying_wins'], 0)
        self.assertEqual(report['metrics']['pair_results'][0]['dominant'], 'glass')

    def test_explicit_percentage_rounds_up_and_time_limit_is_inclusive(self):
        report = analyze(fixture([550, 551, 'loss'], [550, 550, 551], max_win_ms=550, min_win_percent=66))
        self.assertEqual([c['required_wins'] for c in report['metrics']['cells']], [2, 2])
        self.assertEqual([c['viability'] for c in report['metrics']['cells']], ['meets-target', 'below-target'])
        report = analyze(fixture([1, 2, 'loss'], [1, 2, 3], min_win_percent=67))
        self.assertEqual([c['required_wins'] for c in report['metrics']['cells']], [3, 3])

    def test_empty_matrix_and_short_complete_plan_warn_without_finding_unviability_or_dominance(self):
        for data in [dict(example(), rows=[]), fixture(['loss', 'loss'], [1, 1])]:
            with self.subTest(data=data):
                report = analyze(data)
                self.assertEqual(report['status'], 'warn')
                self.assertEqual(set(statuses(report).values()), {'warn'})
                self.assertEqual(report['metrics']['pair_results'], [])
                self.assertTrue(all(c['viability'] == 'unassessed' for c in report['metrics']['cells']))

    def test_absent_cell_suppresses_only_pairs_involving_that_build(self):
        data = example()
        data['rows'] = [r for r in data['rows'] if not (r['build'] == 'anchor' and r['scenario'] == 'relay-ring')]
        report = analyze(data)
        self.assertEqual(report['status'], 'warn')
        self.assertEqual(report['metrics']['compared_pairs'], 1)
        incomplete, = [c for c in report['metrics']['cells'] if c['viability'] == 'unassessed']
        self.assertEqual(incomplete['missing_trials'], [1, 2, 3])
        self.assertEqual(incomplete['observed_trials'], 0)

    def test_missing_ordinal_is_reported_and_cannot_be_replaced_with_a_duplicate(self):
        data = fixture([4, 5, 2], [4, 6, 1])
        data['rows'].pop(1)
        incomplete, = [c for c in analyze(data)['metrics']['cells'] if c['viability'] == 'unassessed']
        self.assertEqual(incomplete['missing_trials'], [2])
        data['rows'].append(dict(data['rows'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            analyze(data)

    def test_second_scenario_reverses_advantage_and_blocks_global_dominance(self):
        data = fixture([10, 10, 10], [20, 20, 20])
        more = fixture([100, 100, 100], [70, 70, 70])
        data['scenarios'].append(dict(more['scenarios'][0], id='basin'))
        data['rows'].extend(dict(r, scenario='basin') for r in more['rows'])
        self.assertEqual(analyze(data)['status'], 'pass')

    def test_invalid_schema_ids_and_numbers_fail_with_value_error(self):
        edits = [
            lambda d: d.update(schema_version=True),
            lambda d: d.update(source='personal'),
            lambda d: d.update(player_id='person'),
            lambda d: d.update(rows=()),
            lambda d: d.update(builds=['only']),
            lambda d: d['builds'].append('glass'),
            lambda d: d['builds'].append('bad/id'),
            lambda d: d.update(scenarios=[None]),
            lambda d: d['scenarios'].append(dict(d['scenarios'][0])),
            lambda d: d['scenarios'][0].update(trials=33),
            lambda d: d['scenarios'][0].update(max_win_ms=float('nan')),
            lambda d: d['scenarios'][0].update(min_win_percent=0),
            lambda d: d['scenarios'][0].update(player='someone'),
            lambda d: d['rows'][0].update(build=[]),
            lambda d: d['rows'][0].update(scenario='elsewhere'),
            lambda d: d['rows'][0].update(trial=4),
            lambda d: d['rows'][0].update(win_ms=3_600_001),
            lambda d: d['rows'][0].update(win_ms=float('inf')),
            lambda d: d['rows'][0].update(win_ms=True),
            lambda d: d['rows'][0].update(win_ms=None),
            lambda d: d['rows'][0].update(outcome='timeout', win_ms=300),
            lambda d: d['rows'][0].update(outcome='aborted'),
            lambda d: d['rows'][0].update(player='unwanted'),
            lambda d: d['rows'][0].pop('outcome'),
        ]
        for edit in edits:
            with self.subTest(edit=edit):
                data = fixture([1, 2, 3], [1, 2, 3])
                edit(data)
                with self.assertRaises(ValueError):
                    analyze(data)
        with self.assertRaises(ValueError):
            analyze(None)
