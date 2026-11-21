import copy
import json
import unittest


EXERCISE = 'production-pipeline'


class ProductionLabTests(unittest.TestCase):
    def setUp(self):
        from command_center import lab_production

        self.lab = lab_production
        self.exercise, = self.lab.EXERCISES
        self.submission = copy.deepcopy(self.exercise['example'])
        self.tasks = {task['id']: task for task in self.submission['tasks']}

    def checks(self):
        return {row['id']: row for row in self.lab.assess(EXERCISE, self.submission)}

    def test_teaching_example_matches_the_track_and_passes_every_criterion(self):
        self.assertEqual(self.exercise['id'], EXERCISE)
        self.assertEqual(self.lab.TRACK['id'], EXERCISE)
        self.assertEqual(self.lab.TRACK['roles'], ['architecture', 'content', 'build_operations', 'verification'])
        self.submission = json.loads(json.dumps(self.submission))
        checks = self.lab.assess(EXERCISE, self.submission)
        self.assertEqual(checks, self.lab.assess(EXERCISE, self.submission))
        self.assertEqual(self.submission, self.exercise['example'])
        self.assertEqual([check['id'] for check in checks], [row['id'] for row in self.exercise['criteria']])
        for check in checks:
            self.assertEqual(set(check), {'id', 'status', 'detail'})
            self.assertEqual(check['status'], 'pass', check['detail'])
            self.assertTrue(check['detail'].strip())

    def test_required_stage_dependencies_are_checked_transitively(self):
        self.tasks['prepare-content']['depends_on'] = ['vertical-slice']
        self.tasks['integrate-content']['depends_on'] = ['prepare-content']
        self.assertEqual(self.checks()['dependencies']['status'], 'pass')
        self.tasks['integrate-content']['depends_on'] = ['vertical-slice']
        self.assertEqual(self.checks()['dependencies']['status'], 'fail')

    def test_missing_dependencies_and_cycles_block_schedule_and_forecast(self):
        for dependency in ('missing-task', 'handoff'):
            with self.subTest(dependency=dependency):
                self.tasks['prototype']['depends_on'] = [dependency]
                checks = self.checks()
                for criterion in ('dependencies', 'schedule', 'forecast'):
                    self.assertEqual(checks[criterion]['status'], 'fail')

    def test_artifacts_are_bound_to_the_expected_stage_and_role(self):
        self.tasks['integrate-content']['artifact'] = self.tasks['prepare-content']['artifact']
        self.assertEqual(self.checks()['artifacts']['status'], 'fail')
        self.tasks['integrate-content']['artifact'] = 'integrated-scene'
        self.tasks['integrate-content']['role'] = 'architecture'
        self.assertEqual(self.checks()['artifacts']['status'], 'fail')

    def test_schedule_checks_dependency_finish_instead_of_only_task_order(self):
        self.tasks['vertical-slice']['start'] = 3
        checks = self.checks()
        self.assertEqual(checks['dependencies']['status'], 'pass')
        self.assertEqual(checks['schedule']['status'], 'fail')
        self.assertIn('vertical-slice', checks['schedule']['detail'])

    def test_same_role_overlap_fails_and_adjacent_work_can_share_the_role(self):
        extra = {'id': 'inspect-lock', 'role': 'build_operations', 'duration': 1, 'start': 7,
                 'depends_on': ['prototype'], 'artifact': 'lock-review'}
        self.submission['tasks'].append(extra)
        self.tasks['handoff']['depends_on'].append('inspect-lock')
        checks = self.checks()
        self.assertEqual(checks['dependencies']['status'], 'pass')
        self.assertEqual(checks['schedule']['status'], 'fail')
        self.assertIn('build_operations', checks['schedule']['detail'])
        extra['start'] = 6
        self.assertEqual(self.checks()['schedule']['status'], 'pass')

    def test_forecast_computes_the_weighted_path_and_scheduled_finish(self):
        self.tasks['prepare-content']['duration'] = 4
        for task, start in [('integrate-content', 6), ('package', 8), ('review', 10), ('rollback-drill', 10)]:
            self.tasks[task]['start'] = start
        checks = self.checks()
        self.assertEqual(checks['schedule']['status'], 'pass')
        self.assertEqual(checks['forecast']['status'], 'fail')
        self.assertIn('prepare-content', checks['forecast']['detail'])
        self.assertIn('13 steps', checks['forecast']['detail'])
        self.submission['forecast']['critical_path_steps'] = 13
        self.assertEqual(self.checks()['forecast']['status'], 'pass')
        self.tasks['handoff']['start'] = 13
        self.assertEqual(self.checks()['forecast']['status'], 'fail')

    def test_milestone_uses_finish_and_a_fixed_deadline(self):
        self.tasks['handoff']['start'] = 14
        self.submission['forecast']['handoff_step'] = 15
        checks = self.checks()
        self.assertEqual(checks['schedule']['status'], 'pass')
        self.assertEqual(checks['forecast']['status'], 'pass')
        self.assertEqual(checks['milestones']['status'], 'fail')
        self.assertIn('handoff', checks['milestones']['detail'])
        self.assertIn('15', checks['milestones']['detail'])

    def test_reproducibility_requires_distinct_runs_and_identical_inputs_and_output(self):
        first, second = self.submission['builds']
        changes = {'workspace': first['workspace'], 'revision': 'f' * 40, 'toolchain': 'godot-4.5.0',
                   'lock_sha256': 'f' * 64, 'package_sha256': 'f' * 64}
        for key, value in changes.items():
            with self.subTest(key=key):
                original = second[key]
                second[key] = value
                self.assertEqual(self.checks()['reproducibility']['status'], 'fail')
                second[key] = original

    def test_acceptance_review_rejects_failed_or_missing_scenarios(self):
        scenarios = self.submission['review']['scenarios']
        scenarios[0]['exit_codes'].append(1)
        checks = self.checks()
        self.assertEqual(checks['verification']['status'], 'fail')
        self.assertIn(scenarios[0]['id'], checks['verification']['detail'])
        scenarios[0]['exit_codes'].pop()
        scenarios.pop()
        self.assertEqual(self.checks()['verification']['status'], 'fail')

    def test_acceptance_review_requires_exact_candidate_and_an_independent_role(self):
        review = self.submission['review']
        package = review['package_sha256']
        review['package_sha256'] = 'f' * 64
        self.assertEqual(self.checks()['verification']['status'], 'fail')
        review['package_sha256'] = package
        review['role'] = 'build_operations'
        self.tasks['review']['role'] = 'build_operations'
        self.assertEqual(self.checks()['verification']['status'], 'fail')

    def test_rollback_restores_a_distinct_known_good_package_and_runs_smoke(self):
        rollback = self.submission['rollback']
        for key, value in {'candidate_sha256': 'f' * 64, 'restored_sha256': 'f' * 64, 'smoke_exit_code': 1}.items():
            with self.subTest(key=key):
                original = rollback[key]
                rollback[key] = value
                self.assertEqual(self.checks()['rollback']['status'], 'fail')
                rollback[key] = original
        rollback['previous_sha256'] = rollback['restored_sha256'] = 'f' * 64
        self.assertEqual(self.checks()['rollback']['status'], 'fail')
        rollback['previous_sha256'] = rollback['restored_sha256'] = rollback['candidate_sha256']
        self.assertEqual(self.checks()['rollback']['status'], 'fail')

    def test_malformed_and_unbounded_inputs_raise_value_error(self):
        malformed = [[], {}, dict(self.submission, status='pass'), dict(self.submission, tasks=[]),
                     dict(self.submission, tasks=self.submission['tasks'] * 2)]
        first, *rest = self.submission['tasks']
        for key, value in [('duration', True), ('duration', 9), ('start', -1), ('depends_on', ['a', 'a']),
                           ('role', []), ('artifact', 'path/to/file'), ('id', rest[0]['id'])]:
            malformed.append(dict(self.submission, tasks=[dict(first, **{key: value}), *rest]))
        for key, value in [('revision', 'main'), ('package_sha256', 'A' * 64), ('workspace', {})]:
            first_build, second_build = self.submission['builds']
            malformed.append(dict(self.submission, builds=[dict(first_build, **{key: value}), second_build]))
        for value in malformed:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.lab.assess(EXERCISE, value)
        with self.assertRaises(ValueError):
            self.lab.assess('unknown', self.submission)
