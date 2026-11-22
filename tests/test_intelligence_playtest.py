from copy import deepcopy
import json
import unittest

from command_center.intelligence_playtest import analyze, example


def data_with(rows, minimum=10, threshold=15):
    return {'schema_version': 1, 'minimum_per_arm': minimum, 'review_delta_pp': threshold, 'rows': rows}


def arm(variant, started=20, completed=12, cohort='all'):
    return {'variant': variant, 'scenario': 'navigation', 'cohort': cohort, 'window_minutes': 10,
            'started': started, 'completed': completed, 'abandoned': 0, 'retried': 0, 'confusion': 0,
            'replay_offered': started, 'replay_chosen': started, 'replay_declined': 0}


def pair(result):
    return result['metrics']['comparisons'][0]


class PlaytestIntelligenceTests(unittest.TestCase):
    def test_contract_serializable_repeatable_and_detached_from_caller_data(self):
        data = example()
        original = deepcopy(data)
        result = analyze(data)
        self.assertEqual(data, original)
        self.assertEqual(result, analyze(data))
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(set(result), {'schema_version', 'kind', 'status', 'checks', 'metrics', 'advisory'})
        self.assertEqual((result['schema_version'], result['kind']), (1, 'playtest'))
        self.assertTrue(all(set(check) == {'id', 'label', 'status', 'detail'} for check in result['checks']))
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        data['rows'].reverse()
        self.assertEqual(result, analyze(data))
        pair(result)['baseline']['completed'] = 999
        self.assertEqual(example(), original)
        self.assertEqual(data['rows'], list(reversed(original['rows'])))

    def test_outcomes_use_explicit_denominators_and_nonexclusive_signals(self):
        left, right = arm('baseline'), arm('candidate', 30, 21)
        left.update(abandoned=3, retried=11, confusion=8)
        right.update(abandoned=5, retried=17, confusion=10)
        result = analyze(data_with([left, right]))
        self.assertEqual(result['status'], 'pass')
        group = pair(result)
        self.assertEqual(group['baseline']['other_outcome'], 5)
        self.assertEqual(group['candidate']['other_outcome'], 4)
        self.assertEqual(group['measures']['completion']['delta_pp'], 10)
        self.assertEqual(group['measures']['retry']['candidate'],
                         {'count': 17, 'denominator': 30, 'percent': 56.6667})
        self.assertEqual(group['measures']['abandonment']['delta_pp'], 1.6667)

    def test_adverse_direction_and_inclusive_threshold_from_unrounded_values(self):
        left, right = arm('baseline', 20, 14), arm('candidate', 20, 11)
        right.update(abandoned=3, confusion=3)
        result = analyze(data_with([left, right]))
        self.assertEqual(result['status'], 'fail')
        flags = {f['measure']: f['delta_pp'] for f in result['metrics']['review_flags']}
        self.assertEqual(flags, {'completion': -15, 'abandonment': 15, 'confusion': 15})
        result = analyze(data_with([arm('baseline', 99991, 54996), arm('candidate', 99989, 44996)], threshold=10))
        metric = pair(result)['measures']['completion']
        self.assertEqual(metric['delta_pp'], -10)  # -9.999999980996... before display rounding.
        self.assertFalse(metric['adverse_threshold_crossed'])
        self.assertEqual(result['status'], 'pass')

    def test_unmatched_cohort_scenario_window_never_generates_a_difference(self):
        left, right = arm('baseline'), arm('candidate')
        for key, value in [('scenario', 'puzzle'), ('cohort', 'first-time'), ('window_minutes', 11)]:
            with self.subTest(key=key):
                result = analyze(data_with([left, dict(right, **{key: value})]))
                self.assertEqual(result['status'], 'warn')
                groups = result['metrics']['comparisons']
                self.assertEqual(len(groups), 1 if key == 'window_minutes' else 2)
                for group in groups:
                    self.assertFalse(group['matched'])
                    expected = 'different_windows' if key == 'window_minutes' else 'missing_variant'
                    self.assertEqual(group['match_issue'], expected)
                    for observation in group['measures'].values():
                        self.assertEqual(observation['reason'], expected)
                        self.assertIsNone(observation['delta_pp'])

    def test_empty_zero_and_small_denominators_are_explicitly_insufficient(self):
        self.assertEqual(analyze(data_with([]))['status'], 'warn')
        for n in (0, 9):
            result = analyze(data_with([arm('baseline', n, n), arm('candidate', 60, 0)]))
            self.assertEqual(result['status'], 'warn')
            self.assertEqual(result['metrics']['review_flags'], [])
            measure = pair(result)['measures']['completion']
            self.assertEqual(measure['evidence'], 'insufficient')
            self.assertEqual(measure['reason'], 'insufficient_denominator')
            self.assertIsNone(measure['delta_pp'])
            self.assertEqual(measure['baseline']['percent'], 100 if n else None)

    def test_replay_denominator_is_recorded_voluntary_decisions_and_missing_is_preserved(self):
        left, right = arm('baseline', 50, 15), arm('candidate', 50, 18)
        left.update(replay_offered=20, replay_chosen=6, replay_declined=4)
        right.update(replay_offered=18, replay_chosen=5, replay_declined=10)
        result = analyze(data_with([left, right]))
        group = pair(result)
        self.assertEqual((group['baseline']['replay_unanswered'], group['candidate']['replay_unanswered']), (10, 3))
        observation = group['measures']['replay_choice']
        self.assertEqual(observation['baseline'], {'count': 6, 'denominator': 10, 'percent': 60})
        self.assertEqual(observation['delta_pp'], -26.6667)
        self.assertIsNone(observation['adverse_threshold_crossed'])
        self.assertEqual(result['status'], 'warn')
        left['replay_declined'] = 3
        result = analyze(data_with([left, right]))
        self.assertEqual(pair(result)['measures']['replay_choice']['reason'], 'insufficient_denominator')
        self.assertEqual(pair(result)['measures']['completion']['evidence'], 'descriptive')

    def test_optional_replay_distinguishes_not_recorded_from_no_offers(self):
        left, right = arm('baseline'), arm('candidate')
        for key in ('replay_offered', 'replay_chosen', 'replay_declined'):
            left[key] = None
            right[key] = 0
        group = pair(analyze(data_with([left, right])))
        self.assertIsNone(group['baseline']['replay_answered'])
        self.assertEqual(group['candidate']['replay_answered'], 0)
        replay = group['measures']['replay_choice']
        self.assertEqual(replay['reason'], 'replay_unobserved')
        self.assertIsNone(replay['baseline'])
        self.assertEqual(replay['candidate'], {'count': 0, 'denominator': 0, 'percent': None})

    def test_more_retries_or_less_optional_replay_never_independently_fails(self):
        left, right = arm('baseline'), arm('candidate')
        right.update(retried=20, replay_chosen=0, replay_declined=20)
        result = analyze(data_with([left, right]))
        self.assertEqual(result['status'], 'pass')
        observations = pair(result)['measures']
        self.assertEqual(observations['retry']['delta_pp'], 100)
        self.assertEqual(observations['replay_choice']['delta_pp'], -100)
        self.assertEqual(result['metrics']['review_flags'], [])

    def test_different_composition_is_not_pooled_and_missing_arm_does_not_erase_valid_evidence(self):
        rows = [arm('baseline', 20, 10, 'first-time'), arm('candidate', 100, 60, 'first-time'),
                arm('baseline', 100, 90, 'returning'), arm('candidate', 20, 20, 'returning')]
        result = analyze(data_with(rows))
        self.assertEqual([g['measures']['completion']['delta_pp'] for g in result['metrics']['comparisons']], [10, 10])
        self.assertEqual(result['status'], 'pass')
        rows.append(dict(arm('candidate'), scenario='puzzle'))
        rows[1]['completed'] = 10
        result = analyze(data_with(rows))
        self.assertEqual(result['status'], 'fail')
        self.assertEqual([f['cohort'] for f in result['metrics']['review_flags']], ['first-time'])

    def test_invalid_types_shapes_and_counts_are_rejected(self):
        for mutate in (
            lambda d: d.update(schema_version=True), lambda d: d.update(schema_version=2),
            lambda d: d.update(rows=d['rows'] * 19), lambda d: d.update(rows={}), lambda d: d.update(note='hello'),
            lambda d: d.update(minimum_per_arm=1), lambda d: d.update(review_delta_pp=0),
            lambda d: d.update(review_delta_pp=1.5), lambda d: d['rows'].append(deepcopy(d['rows'][0])),
            lambda d: d['rows'][0].update(participant_id='x'), lambda d: d['rows'][0].update(scenario='custom name'),
            lambda d: d['rows'][0].update(variant='control'), lambda d: d['rows'][0].update(cohort=[]),
            lambda d: d['rows'][0].update(retried=-1), lambda d: d['rows'][0].update(confusion=21),
            lambda d: d['rows'][0].update(completed=True), lambda d: d['rows'][0].update(window_minutes=0),
            lambda d: d['rows'][0].update(started=100001), lambda d: d['rows'][0].update(abandoned=9),
            lambda d: d['rows'][0].update(replay_offered=19), lambda d: d['rows'][0].update(replay_declined=1),
            lambda d: d['rows'][0].update(replay_chosen=None), lambda d: d['rows'][0].pop('confusion'),
        ):
            with self.subTest(mutation=mutate):
                data = data_with([arm('baseline'), arm('candidate')])
                mutate(data)
                with self.assertRaises(ValueError):
                    analyze(data)
        for malformed in (None, [], {}, True):
            with self.assertRaises(ValueError):
                analyze(malformed)


if __name__ == '__main__':
    unittest.main()
