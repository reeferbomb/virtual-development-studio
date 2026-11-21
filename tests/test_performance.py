import copy
import json
import math
import unittest
from datetime import datetime, timedelta, timezone

from command_center.performance import profile_jobs
from command_center.provenance import spec_digest


PROJECT = {'id': 'training', 'spec': {'seed': 17}}
DIGEST = spec_digest(PROJECT['spec'])
ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def job(number, build=3, verify=1, **overrides):
    stamp = ORIGIN + timedelta(minutes=number)
    commands = [{'stage': stage, 'duration_seconds': duration, 'exit_code': 0, 'timed_out': False}
                for stage, duration in [('build', build), ('verify', verify)]]
    return {'id': f'job-{number}', 'project_id': PROJECT['id'], 'spec_sha256': DIGEST, 'status': 'passed',
            'verified': True, 'created_at': stamp.isoformat(), 'started_at': (stamp + timedelta(seconds=2)).isoformat(),
            'commands': commands, **overrides}


class PerformanceTests(unittest.TestCase):
    def test_empty_and_current_identity_filter(self):
        records = [None, {}, job(0, project_id='elsewhere'), job(1, spec_sha256=spec_digest({'seed': 18})),
                   job(2, project_id=None), job(3, id=[]), job(4, status=[]), job(5, status='unknown')]
        result = profile_jobs(PROJECT, iter(records))
        self.assertEqual(result, {'project_id': 'training', 'spec_sha256': DIGEST, 'scope': 'current_spec',
                                  'counts': dict(total=0, queued=0, running=0, failed=0, canceled=0, passed=0),
                                  'samples': [], 'summary': dict(median_build_seconds=None, median_verify_seconds=None,
                                      median_total_seconds=None, latest_total_seconds=None, baseline_total_seconds=None,
                                      regression_percent=None), 'regression': None})
        self.assertNotEqual(profile_jobs(dict(PROJECT, spec={}), [])['spec_sha256'], DIGEST)

    def test_summary_uses_complete_verified_pairs_and_excludes_queue_from_total(self):
        records = [job(1), job(2, 2, 2), job(3, 5, 0), job(4, 250, 900, status='failed'),
                   job(5, 250, 901, verified=1), job(6, 250, None), job(7, 1, 500, status='running'),
                   job(8, commands=[], status='queued', started_at=None),
                   job(9, commands=[], status='canceled', started_at=None)]
        result = profile_jobs(PROJECT, records[::-1])
        self.assertEqual(result['counts'], dict(total=9, queued=1, running=1, failed=1, canceled=1, passed=5))
        self.assertEqual(result['summary'], dict(median_build_seconds=3, median_verify_seconds=1,
                                                 median_total_seconds=4, latest_total_seconds=5,
                                                 baseline_total_seconds=4, regression_percent=25))
        self.assertIs(result['regression'], True)
        self.assertEqual(result['samples'][-1], dict(job_id='job-1', status='passed', created_at=records[0]['created_at'],
                         queue_seconds=2, build_seconds=3, verify_seconds=1, total_seconds=4))
        self.assertIsNone(result['samples'][0]['queue_seconds'])
        self.assertIsNone(result['samples'][0]['total_seconds'])
        self.assertEqual(result['samples'][3]['build_seconds'], 250)
        self.assertIsNone(result['samples'][3]['total_seconds'])

    def test_comparisons_require_two_prior_distinct_runs_and_both_thresholds(self):
        for totals, baseline, percent, flag in [
                ([3], None, None, None), ([3, 4], None, None, None),
                ([0, 0, 3], 0, None, None), ([2, 2, 2.5], 2, 25, False),
                ([20, 20, 21], 20, 5, False), ([3, 5, 5], 4, 25, True),
                ([4.4, 4.4, 5.5], 4.4, 25, True),
                ([4, 4, 2], 4, -50, False), ([5, 5, 5], 5, 0, False)]:
            with self.subTest(totals=totals):
                records = [job(i, t, 0) for i, t in enumerate(totals)]
                result = profile_jobs(PROJECT, records + [records[-1]])
                self.assertEqual(result['counts']['total'], len(records))
                self.assertEqual(result['summary']['baseline_total_seconds'], baseline)
                self.assertEqual(result['summary']['regression_percent'], percent)
                self.assertIs(result['regression'], flag)

    def test_requires_saved_project_and_collection_of_jobs(self):
        for project, jobs in [(None, []), ({'id': None, 'spec': {}}, []), ({'id': 'x'}, []),
                              (PROJECT, None), (PROJECT, {}), (PROJECT, '[]')]:
            with self.subTest(project=project, jobs=jobs), self.assertRaises(ValueError):
                profile_jobs(project, jobs)

    def test_uses_absolute_time_and_leaves_unknown_times_unavailable(self):
        jobs = [job(1, created_at='2026-04-20T09:00:00+03:00', started_at='2026-04-20T06:00:05Z'),
                job(2, created_at='2026-04-20T06:05:00Z', started_at='2026-04-20T06:04:59Z'),
                job(3, created_at='invalid'), job(4, created_at='0001-01-01T00:00:00+23:59'),
                job(5, created_at='2026-04-20T12:00:00'), job(6, created_at=None)]
        result = profile_jobs(PROJECT, jobs)
        rows = result['samples']
        self.assertEqual([r['job_id'] for r in rows[:2]], ['job-2', 'job-1'])
        self.assertEqual([r['queue_seconds'] for r in rows[:2]], [None, 5])
        self.assertTrue(all(r['queue_seconds'] is None and r['created_at'] is None for r in rows[2:]))
        self.assertIsNone(result['summary']['baseline_total_seconds'])
        self.assertEqual(result['summary']['latest_total_seconds'], 4)
        self.assertIsNone(profile_jobs(PROJECT, jobs[2:])['summary']['latest_total_seconds'])

    def test_bad_durations_ambiguous_or_contradictory_commands(self):
        invalid = [-2, math.nan, math.inf, -math.inf, '1.5', False, {}, 10 ** 400]
        for value in invalid:
            with self.subTest(value=value):
                result = profile_jobs(PROJECT, [job(1, value, 1)])
                self.assertIsNone(result['samples'][0]['build_seconds'])
                self.assertIsNone(result['samples'][0]['total_seconds'])
                self.assertIsNone(result['summary']['latest_total_seconds'])
                json.dumps(result, allow_nan=False)
        build, verify = job(1)['commands']
        for commands in [None, 'bad', [None, {'stage': []}], [build, build, verify], [build],
                         [build, dict(verify, exit_code=1)], [build, dict(verify, exit_code=False)],
                         [build, dict(verify, timed_out=True)]]:
            with self.subTest(commands=commands):
                result = profile_jobs(PROJECT, [job(1, commands=commands)])
                self.assertIsNone(result['summary']['latest_total_seconds'])
        legacy = [{'stage': 'build', 'duration_seconds': 0}, {'stage': 'verify', 'duration_seconds': 0}]
        self.assertEqual(profile_jobs(PROJECT, [job(1, commands=legacy)])['summary']['latest_total_seconds'], 0)

    def test_derived_values_remain_finite_and_json_safe(self):
        result = profile_jobs(PROJECT, [job(1, 1e308, 1e308)])
        self.assertIsNone(result['samples'][0]['total_seconds'])
        result = profile_jobs(PROJECT, [job(1, 1e308, 0), job(2, 1e308, 0)])
        self.assertEqual(result['summary']['median_total_seconds'], 1e308)
        result = profile_jobs(PROJECT, [job(1, 1e-308, 0), job(2, 1e-308, 0), job(3, 1e308, 0)])
        self.assertIsNone(result['summary']['regression_percent'])
        json.dumps(result, allow_nan=False)

    def test_sample_cap_does_not_limit_current_history_counts_or_baseline(self):
        records = [job(i, 8, 2) for i in range(55)] + [job(i, commands=[], status='failed') for i in range(55, 110)]
        original = copy.deepcopy(records)
        result = profile_jobs(PROJECT, records)
        self.assertEqual(records, original)
        self.assertEqual(result['counts']['total'], 110)
        self.assertEqual([s['job_id'] for s in result['samples']], [f'job-{i}' for i in range(109, 59, -1)])
        self.assertEqual(result['summary']['baseline_total_seconds'], 10)
        self.assertIs(result['regression'], False)


if __name__ == '__main__':
    unittest.main()
