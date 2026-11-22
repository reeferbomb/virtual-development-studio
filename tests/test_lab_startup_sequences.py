from copy import deepcopy
import unittest

from command_center import lab_startup_sequences as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def results(data):
    return {row['id']: row for row in lab.assess('startup-sequences', data)}


def failed(data):
    return {key for key, value in results(data).items() if value['status'] == 'fail'}


def step(data, case, op, occurrence=0):
    return [row for row in data['cases'][case]['steps'] if row['op'] == op][occurrence]


class StartupSequencesTests(unittest.TestCase):
    def test_teaching_trace_is_replayable_and_matches_criteria(self):
        data = example()
        checks = results(data)
        self.assertEqual(lab.TRACK['id'], 'startup-sequences')
        self.assertEqual(list(checks), [row['id'] for row in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(row['status'] == 'pass' and row['detail'] for row in checks.values()))
        self.assertEqual(checks, results(data))
        self.assertEqual(data, example())

    def test_notice_minimum_is_enforced_before_logo_skip(self):
        data = example()
        first = step(data, 'first-run', 'advance')
        self.assertFalse(first['expected']['accepted'])
        first['expected'].update(accepted=True, screen='logos')
        self.assertIn('legal-and-skip', failed(data))
        data = example()
        data['notice_min_ms'] += 1
        self.assertIn('legal-and-skip', failed(data))
        data = example()
        step(data, 'first-run', 'skip')['expected'].update(screen='title', accepted=True)
        self.assertIn('legal-and-skip', failed(data))

    def test_first_launch_requires_setup_and_returning_settings_persist(self):
        data = example()
        step(data, 'first-run', 'ready')['expected']['screen'] = 'notice'
        self.assertIn('startup-path', failed(data))
        data = example()
        data['cases']['returning']['preferences'] = None
        self.assertIn('startup-path', failed(data))

    def test_save_selection_checks_digest_version_and_checkpoint(self):
        data = example()
        data['cases']['returning']['primary']['sha256'] = '0' * 64
        self.assertIn('save-selection', failed(data))
        data = example()
        data['cases']['returning']['primary'] = lab._save('unlisted')
        self.assertIn('save-selection', failed(data))
        data = example()
        data['cases']['damaged']['primary'] = lab._save('gallery')
        self.assertIn('save-selection', failed(data))

    def test_retry_rejects_stale_success_and_does_not_reset_on_bad_progress(self):
        data = example()
        stale = step(data, 'first-run', 'loaded')
        self.assertFalse(stale['expected']['accepted'])
        stale['expected'].update(accepted=True, screen='playing')
        self.assertIn('load-recovery', failed(data))
        data = example()
        step(data, 'first-run', 'progress', 1)['percent'] = 5
        step(data, 'first-run', 'progress', 1)['expected']['accepted'] = True
        self.assertIn('load-recovery', failed(data))

    def test_checkpoint_and_suspend_preserve_distinct_positions(self):
        for operation in ('suspend', 'restore', 'resume', 'checkpoint'):
            with self.subTest(operation=operation):
                data = example()
                step(data, 'first-run', operation)['expected']['position'] = 'gallery'
                self.assertIn('playback-return', failed(data))

    def test_restart_cannot_replace_gameplay_until_confirmed_and_loaded(self):
        data = example()
        step(data, 'first-run', 'restart')['expected'].update(screen='loading', ticket=4)
        self.assertIn('playback-return', failed(data))
        data = example()
        step(data, 'first-run', 'confirm')['expected'].update(position='station', checkpoint='station')
        self.assertIn('playback-return', failed(data))

    def test_fixed_timing_budgets_ignore_time_spent_reading(self):
        data = example()
        for row in data['cases']['returning']['steps'][1:]:
            row['at_ms'] += 2000
        self.assertEqual(failed(data), set())
        data = example()
        for row in data['cases']['returning']['steps']:
            row['at_ms'] += 1600
        self.assertEqual(failed(data), {'timing'})
        data = example()
        step(data, 'returning', 'loaded')['at_ms'] += 3500
        self.assertEqual(failed(data), {'timing'})

    def test_shapes_are_bounded_and_reject_unknown_actions(self):
        for mutate in (
            lambda d: d.update(notice_min_ms=True),
            lambda d: d['cases'].pop('damaged'),
            lambda d: d['cases']['first-run'].update(preferences='invented'),
            lambda d: step(d, 'first-run', 'ready').update(at_ms=120_001),
            lambda d: step(d, 'first-run', 'configure').update(at_ms=0),
            lambda d: step(d, 'first-run', 'progress').update(percent=100),
            lambda d: step(d, 'first-run', 'loaded').update(ticket=True),
            lambda d: step(d, 'first-run', 'ready').update(op='run-script'),
            lambda d: step(d, 'first-run', 'ready')['expected'].update(progress=False),
            lambda d: d['cases']['returning']['primary'].update(sha256='invalid'),
        ):
            with self.subTest(mutation=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess('startup-sequences', data)
        with self.assertRaises(ValueError):
            lab.assess('unknown', example())


if __name__ == '__main__':
    unittest.main()
