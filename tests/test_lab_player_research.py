from copy import deepcopy
import unittest

from command_center import lab_player_research as research


def example():
    return deepcopy(research.EXERCISES[0]['example'])


def failed(data):
    return {row['id'] for row in research.assess('player-research', data) if row['status'] == 'fail'}


class PlayerResearchLabTests(unittest.TestCase):
    def test_criteria_match_replayable_synthetic_example(self):
        data = example()
        original = deepcopy(data)
        rows = research.assess('player-research', data)
        self.assertEqual([row['id'] for row in rows], [c['id'] for c in research.EXERCISES[0]['criteria']])
        self.assertTrue(all(row['status'] == 'pass' and row['detail'] for row in rows))
        data['sessions'].reverse()
        self.assertEqual(research.assess('player-research', data), rows)
        data['sessions'].reverse()
        self.assertEqual(data, original)

    def test_observation_and_response_have_distinct_denominators(self):
        data = example()
        data['summary']['all']['enjoyed'] = [3, 8]
        self.assertEqual(failed(data), {'self-report'})
        data = example()
        # The player stopped after reporting enjoyment. Inferring boredom from the exit is incorrect.
        data['summary']['familiar']['bored'][0] += 1
        self.assertEqual(failed(data), {'self-report'})
        data = example()
        data['summary']['new']['stops'] = [2, 3]
        self.assertEqual(failed(data), {'observations'})

    def test_nonresponse_differs_from_answering_none(self):
        data = example()
        data['sessions'][3]['feelings'] = None
        self.assertEqual(failed(data), {'self-report', 'uncertainty'})
        for group in ('all', 'new'):
            for feeling in ('enjoyed', 'bored', 'frustrated'):
                data['summary'][group][feeling][1] -= 1
            data['summary'][group]['boredom_bounds'][1] += 1
        self.assertFalse(failed(data))

    def test_zero_response_and_replay_denominators_mean_unknown(self):
        data = example()
        for row in data['sessions']:
            row.update(feelings=None, replay='unobserved')
        for group, count in [('all', 8), ('new', 4), ('familiar', 4)]:
            for metric in ('enjoyed', 'bored', 'frustrated', 'returns'):
                data['summary'][group][metric] = [0, 0]
            data['summary'][group]['boredom_bounds'] = [0, count, count]
        self.assertFalse(failed(data))
        data['summary']['all']['returns'] = [0, 8]
        self.assertEqual(failed(data), {'voluntary-return'})
        data['summary']['all']['boredom_bounds'] = [0, 0, 8]
        self.assertEqual(failed(data), {'uncertainty', 'voluntary-return'})

    def test_only_observed_unpressured_replay_choices_count(self):
        for replay in ('required', 'rewarded', 'not-offered', 'unobserved'):
            with self.subTest(replay=replay):
                data = example()
                data['sessions'][1]['replay'] = replay
                self.assertEqual(failed(data), {'voluntary-return'})
                data['summary']['new']['returns'] = [0, 1]
                data['summary']['all']['returns'] = [1, 3]
                self.assertFalse(failed(data))

    def test_pooled_estimates_do_not_replace_cohort_metrics(self):
        data = example()
        for group in ('new', 'familiar'):
            data['summary'][group]['bored'] = [1, 3]
            data['summary'][group]['boredom_bounds'] = [1, 2, 4]
        self.assertEqual(failed(data), {'self-report', 'uncertainty'})

    def test_citing_a_mismatched_outcome_or_overclaiming_fails(self):
        for changes in ({'code': 48}, {'code': 2}, {'code': 2, 'observed_outcome': 'finished'},
                        {'scope': 'proven-cause'}, {'scope': 'all-players'}):
            with self.subTest(changes=changes):
                data = example()
                data['interpretation'].update(changes)
                self.assertEqual(failed(data), {'interpretation'})
        data = example()
        analyses = data['interpretation']['hypotheses']
        analyses[1] = deepcopy(analyses[0])
        self.assertEqual(failed(data), {'interpretation'})
        analyses[1].update(cause='external-interruption')
        self.assertEqual(failed(data), {'interpretation'})
        analyses[1].update(probe='ask-about-context')
        self.assertFalse(failed(data))

    def test_safeguards_cannot_be_replaced_with_correct_arithmetic(self):
        for key in example()['protocol']:
            with self.subTest(key=key):
                data = example()
                data['protocol'][key] = False
                self.assertEqual(failed(data), {'safeguards'})

    def test_closed_schema_accepts_only_bounded_synthetic_codes(self):
        mutations = (
            lambda d: d.update(source='human'),
            lambda d: d['sessions'][0].update(contact='personal-data'),
            lambda d: d['sessions'][0].update(code='player-name'),
            lambda d: d['sessions'][0].update(code=True),
            lambda d: d['sessions'][0].update(code=2),
            lambda d: d['sessions'][0].update(cohort='other'),
            lambda d: d['sessions'][0].update(replay=True),
            lambda d: d['sessions'][0].update(feelings=['bored', 'bored']),
            lambda d: d['sessions'][0].update(feelings=['free text']),
            lambda d: d['sessions'][0].update(feelings=[{}]),
            lambda d: d.update(sessions=d['sessions'] * 7),
            lambda d: d['protocol'].update(informed_opt_in=1),
            lambda d: d['interpretation'].update(code=-1),
            lambda d: d['interpretation'].update(notes='transcript'),
            lambda d: d['summary']['new'].update(stops=[True, 4]),
            lambda d: d['summary']['all'].update(returns=[1.0, 2]),
            lambda d: d['summary']['all'].update(boredom_bounds=[0, 1]),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    research.assess('player-research', data)
        with self.assertRaises(ValueError):
            research.assess('unknown', example())


if __name__ == '__main__':
    unittest.main()
