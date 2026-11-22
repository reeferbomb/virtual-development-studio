from copy import deepcopy
import unittest

from command_center import lab_reference_traversal as traversal


def example():
    return deepcopy(traversal.EXERCISES[0]['example'])


def failed(data):
    return {row['id'] for row in traversal.assess('reference-traversal', data) if row['status'] == 'fail'}


class TraversalReferenceTests(unittest.TestCase):
    def test_example_matches_rubric_without_mutating_course(self):
        course = example()
        before = deepcopy(course)
        rows = traversal.assess('reference-traversal', course)
        self.assertEqual([r['id'] for r in rows], [c['id'] for c in traversal.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in rows))
        self.assertEqual(traversal.assess('reference-traversal', course), rows)
        self.assertEqual(course, before)

    def test_speed_carries_over_and_both_landing_endpoints_count(self):
        for landing in ([10, 11], [9, 10], [10, 10]):
            with self.subTest(landing=landing):
                course = example()
                course['edges'][3]['landing'] = landing
                self.assertFalse(failed(course))
        for landing in ([11, 12], [8, 9]):
            with self.subTest(landing=landing):
                course = example()
                course['edges'][3]['landing'] = landing
                self.assertIn('landings', failed(course))

    def test_launch_clamps_when_accelerating_and_braking(self):
        course = example()
        course['edges'][2].update(ground=4, landing=[15, 17])
        course['edges'][3]['landing'] = [16, 16]
        course['edges'][4]['landing'] = [1, 17]
        course['runs']['swift']['ticks'] = 11
        self.assertFalse(failed(course))
        course['edges'][1].update(accel=-2)
        self.assertFalse(failed(course))

    def test_independent_time_and_margin_predictions(self):
        for run in ('steady', 'swift'):
            for field in ('ticks', 'margin'):
                with self.subTest(run=run, field=field):
                    course = example()
                    course['runs'][run][field] += 1
                    self.assertEqual(failed(course), {'predictions'})

    def test_route_timing_advantage_must_cost_real_tolerance(self):
        course = example()
        course['edges'][3]['landing'] = [9, 11]
        course['runs']['swift']['margin'] = 1
        self.assertEqual(failed(course), {'route-tradeoff'})
        course = example()
        course['runs']['swift'] = deepcopy(course['runs']['steady'])
        self.assertEqual(failed(course), {'route-tradeoff'})

    def test_correct_target_cannot_replace_missing_tool_or_wrong_location(self):
        for defect in ('premature', 'wrong', 'spurious', 'skip-room'):
            with self.subTest(defect=defect):
                course = example()
                if defect == 'premature':
                    course['edges'][0]['target'] = 'early_socket'
                    course['runs']['steady']['steps'][0]['focus'] = 'early_socket'
                elif defect == 'wrong':
                    course['runs']['steady']['steps'][-1]['focus'] = 'secondary_socket'
                elif defect == 'spurious':
                    course['runs']['swift']['steps'][0]['focus'] = 'pressure_socket'
                else:
                    del course['runs']['swift']['steps'][1]
                self.assertTrue({'landings', 'tool-gate', 'predictions'} <= failed(course))

    def test_side_channel_search_distinguishes_room_and_speed_after_a_cycle(self):
        course = example()
        course['edges'].extend([
            traversal._edge('exit_ledge', 'wheelhouse', 'wind_clock', 0, 0, 1, [5, 5]),
            traversal._edge('service_bridge', 'gauge_bench', 'wheelhouse', 0, 0, 1, [6, 6]),
        ])
        # The direct shortcut needs speed 5. The return bridge cannot initially be landed on.
        self.assertFalse(failed(course))
        course['edges'][-1]['landing'] = [5, 5]
        self.assertEqual(failed(course), {'tool-gate'})

    def test_bad_landmarks_and_disconnected_or_overlong_routes(self):
        for changes in ({'start': 'absent'}, {'tool_room': 'wheelhouse'}, {'goal': 'unknown'}):
            course = example()
            course.update(changes)
            self.assertIn('course', failed(course))
        course = example()
        course['runs']['swift']['steps'].append({'edge': 'survey_steps', 'focus': None})
        self.assertIn('landings', failed(course))
        course['runs']['swift']['steps'] = course['runs']['swift']['steps'][:1]
        self.assertIn('landings', failed(course))

    def test_invalid_input_rejected_before_simulation(self):
        for mutate in (lambda c: c['edges'][0].update(id='draft_chute'),
                       lambda c: c['edges'][0].update(ground=True),
                       lambda c: c['edges'][0].update(air=0),
                       lambda c: c['edges'][0].update(accel=2.5),
                       lambda c: c['edges'][0].update(landing=[18, 9]),
                       lambda c: c['edges'][0].update(target=[]),
                       lambda c: c.update(edges=c['edges'] * 7),
                       lambda c: c['runs']['swift']['steps'].append({'edge': 'sail_gap', 'focus': None}),
                       lambda c: c['runs']['swift']['steps'][0].update(edge='missing'),
                       lambda c: c['runs']['swift']['steps'][0].update(note='free text')):
            with self.subTest(mutate=mutate):
                course = example()
                mutate(course)
                with self.assertRaises(ValueError):
                    traversal.assess('reference-traversal', course)
        with self.assertRaises(ValueError):
            traversal.assess('unknown', example())


if __name__ == '__main__':
    unittest.main()
