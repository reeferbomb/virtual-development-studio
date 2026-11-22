from copy import deepcopy
import unittest

from command_center import lab_voice_integration as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def results(data):
    return {row['id']: row for row in lab.assess('voice-integration', data)}


def failed(data):
    return {name for name, row in results(data).items() if row['status'] == 'fail'}


def observation(data, event, locale='en-us'):
    return next(row for row in data['runs'][locale]['observations'] if row['event'] == event)


class VoiceIntegrationLabTests(unittest.TestCase):
    def test_example_is_deterministic_and_matches_public_rubric(self):
        data = example()
        checks = results(data)
        self.assertEqual(list(checks), [row['id'] for row in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(row['status'] == 'pass' and row['detail'] for row in checks.values()))
        self.assertEqual(checks, results(data))
        self.assertEqual(data, example())

    def test_barks_use_priority_cooldown_and_stream_readiness(self):
        for event in ('priority', 'cooldown', 'not-ready', 'duplicate', 'preempt'):
            with self.subTest(event=event):
                data = example()
                observation(data, event)['event'] = 'start'
                self.assertIn('schedule', failed(data))
        data = example()
        data['lines'][1]['variants']['en-us']['ready_ms'] = 0
        self.assertTrue({'schedule', 'streaming'} <= failed(data))
        data = example()
        observation(data, 'preempt')['event'] = 'not-ready'
        self.assertIn('streaming', failed(data))
        data = example()
        data['lines'][0]['interrupt'] = 'drop'
        self.assertIn('schedule', failed(data))

    def test_resume_preserves_playhead_and_localized_viseme(self):
        for field, value in (('offset_ms', 0), ('viseme', 'closed'), ('speaker', 'another-speaker'),
                             ('caption', 'Untranslated placeholder.'), ('voice_sha256', '0' * 64),
                             ('lip_sync_sha256', 'e' * 64)):
            with self.subTest(field=field):
                data = example()
                observation(data, 'resume', 'fr-fr')['playing'][field] = value
                self.assertEqual(failed(data), {'playback-sync'})
        data = example()
        en = observation(data, 'resume')
        fr = observation(data, 'resume', 'fr-fr')
        self.assertNotEqual(en['at_ms'], fr['at_ms'])
        self.assertEqual(en['playing']['offset_ms'], fr['playing']['offset_ms'])

    def test_playback_requires_exact_build_and_distinct_pack_assets(self):
        data = example()
        data['runs']['fr-fr']['build_sha256'] = '8' * 64
        self.assertIn('localization', failed(data))
        for field in ('voice_sha256', 'lip_sync_sha256'):
            with self.subTest(field=field):
                data = example()
                variants = data['lines'][0]['variants']
                variants['fr-fr'][field] = variants['en-us'][field]
                self.assertIn('localization', failed(data))

    def test_mix_measures_peak_and_duck_release(self):
        data = example()
        data['mix']['dialogue_gain_db'] = 0
        data['lines'][0]['variants']['en-us']['peak_dbfs'] = 0
        self.assertEqual(failed(data), {'mix'})
        data = example()
        observation(data, 'finish')['ambience_duck_db'] = -8
        self.assertEqual(failed(data), {'mix'})
        data = example()
        data['mix']['duck_db'] = -2
        self.assertIn('mix', failed(data))

    def test_requires_observed_schedule_through_the_last_completion(self):
        data = example()
        data['runs']['en-us']['observations'].pop()
        self.assertIn('schedule', failed(data))

    def test_shape_types_references_and_limits_are_bounded(self):
        for mutate in (
            lambda d: d.update(url='https://example.invalid/voice'),
            lambda d: d.update(locales=['en-us', 'en-us']),
            lambda d: d['lines'][0]['variants'].pop('fr-fr'),
            lambda d: d['lines'][0]['variants']['en-us'].update(caption='\u200b'),
            lambda d: d['lines'][0]['variants']['en-us'].update(duration_ms=True),
            lambda d: d['lines'][0]['variants']['en-us']['visemes'][0].update(at_ms=1),
            lambda d: d['lines'][0]['variants']['en-us']['visemes'][-1].update(at_ms=1400),
            lambda d: d['lines'][0]['variants']['en-us'].update(ready_ms=1),
            lambda d: d['lines'][1].update(interrupt='resume'),
            lambda d: d['lines'][1].update(cooldown_ms=0),
            lambda d: d['lines'][1].update(id=d['lines'][0]['id']),
            lambda d: d['events'][1].update(at_ms=d['events'][0]['at_ms']),
            lambda d: d['events'][0].update(request='unlisted'),
            lambda d: d['events'].extend(d['events'] * 4),
            lambda d: d['runs']['en-us']['observations'][0].update(playing=[]),
        ):
            with self.subTest(mutation=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess('voice-integration', data)
        with self.assertRaises(ValueError):
            lab.assess('unknown', example())


if __name__ == '__main__':
    unittest.main()
