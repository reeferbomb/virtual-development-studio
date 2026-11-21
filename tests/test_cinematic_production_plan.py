from copy import deepcopy
import json
import unittest

from cinematic.production.plan import compile_plan
from command_center import lab_cutscenes


def inputs():
    plan = deepcopy(lab_cutscenes.EXERCISES[0]['example'])
    plan['blocking'][0]['clip'] = 'aim'
    plan['blocking'][1]['clip'] = 'walk'
    bindings = {
        'cameras': {
            'dock_wide': {'position': [1, 2.5, 8], 'look_at': [0, 1, 0], 'fov': 60},
            'mira_close': {'position': [2, 2, 1], 'look_at': [1, 1.5, 0], 'fov': 48},
        },
        'actors': {
            'keeper': {'position': [0, 0, 0], 'rotation_y': 30},
            'mira': {'position': [1, 0, 0], 'rotation_y': -90},
        },
    }
    return plan, bindings


class ProductionPlanTests(unittest.TestCase):
    def test_output_is_json_and_preserves_inputs_as_independent_data(self):
        plan, bindings = inputs()
        expected = deepcopy({'schema_version': 1, 'plan': plan, 'bindings': bindings})
        compiled = compile_plan(plan, bindings)
        self.assertEqual(json.loads(json.dumps(compiled, allow_nan=False)), expected)
        self.assertEqual(compiled, compile_plan(plan, bindings))
        plan['blocking'].clear()
        bindings['cameras']['dock_wide']['position'][0] = 99
        self.assertEqual(compiled, expected)

    def test_requires_existing_rubric_and_exact_submission_schema(self):
        plan, bindings = inputs()
        plan['exits']['skip']['next_state'] = 'wrong'
        plan['shots'][0]['end_frame'] -= 1
        with self.assertRaisesRegex(ValueError, 'shot-coverage.*story-state'):
            compile_plan(plan, bindings)
        plan, bindings = inputs()
        plan['blocking'][0]['script'] = 'res://custom.gd'
        with self.assertRaises(ValueError):
            compile_plan(plan, bindings)

    def test_only_bundled_lowercase_clip_ids_are_supported(self):
        plan, bindings = inputs()
        for clip in ('idle', 'walk', 'run', 'aim', 'crouch', 'reload'):
            with self.subTest(clip=clip):
                plan['blocking'][0]['clip'] = clip
                self.assertEqual(compile_plan(plan, bindings)['plan']['blocking'][0]['clip'], clip)
        for clip in ('run_script', 'Aim', 'res://anim.tres', '', None):
            with self.subTest(clip=clip):
                plan['blocking'][0]['clip'] = clip
                with self.assertRaises(ValueError):
                    compile_plan(plan, bindings)

    def test_binding_groups_ids_and_fields_are_exact(self):
        for change in (
            lambda b: b.update(assets={}),
            lambda b: b.pop('actors'),
            lambda b: b['cameras'].pop('mira_close'),
            lambda b: b['actors'].update(extra=b['actors']['keeper']),
            lambda b: b['actors'].update(extra=b['actors'].pop('mira')),
            lambda b: b['cameras']['dock_wide'].pop('fov'),
            lambda b: b['actors']['mira'].update(script='res://override.gd'),
            lambda b: b['cameras'].update(dock_wide=[]),
            lambda b: b.update(actors=[]),
        ):
            plan, bindings = inputs()
            change(bindings)
            with self.subTest(bindings=bindings), self.assertRaises(ValueError):
                compile_plan(plan, bindings)

    def test_gameplay_is_reserved_for_the_player_camera(self):
        plan, bindings = inputs()
        plan['cameras'].append('gameplay')
        bindings['cameras']['gameplay'] = bindings['cameras']['dock_wide']
        with self.assertRaisesRegex(ValueError, 'gameplay is reserved'):
            compile_plan(plan, bindings)

    def test_finite_bounds_and_valid_camera_orientation(self):
        plan, bindings = inputs()
        camera = bindings['cameras']['dock_wide']
        actor = bindings['actors']['keeper']
        camera.update(position=[-1000, 1000, 0], look_at=[-1000, 1000, 0.1], fov=179)
        actor.update(position=[1000, -1000, 0], rotation_y=-360)
        self.assertEqual(compile_plan(plan, bindings)['bindings'], bindings)
        for field, values in (
            ('position', ([], (0, 0, 1), [0, 1, 2, 3], [True, 0, 1], [1001, 1, 1])),
            ('look_at', ([-1000, 1000, 0], [-1000, 0, 0], [-1000, 0, 0.01], [0, float('inf'), 0])),
            ('fov', (0, 180, True, '90', float('nan'))),
            ('rotation_y', (361, -361, False, '180', float('-inf'))),
        ):
            for value in values:
                invalid = deepcopy(bindings)
                row = invalid['actors']['keeper'] if field == 'rotation_y' else invalid['cameras']['dock_wide']
                row[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    compile_plan(plan, invalid)

    def test_dialogue_uses_one_channel_even_when_speakers_and_order_differ(self):
        plan, bindings = inputs()
        lines, captions = plan['dialogue'], plan['subtitles']
        lines[0]['end_frame'] = captions[0]['end_frame'] = lines[1]['start_frame']
        lines.reverse()
        self.assertEqual(compile_plan(plan, bindings)['plan'], plan)
        lines[1]['end_frame'] += 1
        captions[0]['end_frame'] += 1
        with self.assertRaisesRegex(ValueError, 'Overlapping dialogue'):
            compile_plan(plan, bindings)

    def test_blocking_overlaps_are_checked_per_actor_and_touching_is_allowed(self):
        plan, bindings = inputs()
        extra = dict(plan['blocking'][0], start_frame=48, end_frame=80, clip='idle')
        plan['blocking'].insert(0, extra)
        self.assertEqual(compile_plan(plan, bindings)['plan'], plan)
        extra['start_frame'] -= 1
        with self.assertRaisesRegex(ValueError, 'Overlapping blocking for keeper'):
            compile_plan(plan, bindings)

    def test_production_budgets_are_inclusive(self):
        plan, bindings = inputs()
        plan.update(fps=60, frame_count=7200, duration_ms=120000)
        plan['shots'][-1]['end_frame'] = plan['frame_count']
        for group, limit in [('actors', 8), ('cameras', 16)]:
            while len(plan[group]) < limit:
                name = f'extra_{len(plan[group])}'
                bindings[group][name] = deepcopy(bindings[group][plan[group][0]])
                plan[group].append(name)
        self.assertEqual(compile_plan(plan, bindings)['plan'], plan)
        for group in ('actors', 'cameras'):
            invalid, extra_bindings = deepcopy((plan, bindings))
            invalid[group].append('one_more')
            extra_bindings[group]['one_more'] = extra_bindings[group][invalid[group][0]]
            with self.subTest(group=group), self.assertRaisesRegex(ValueError, '8 actors and 16 cameras'):
                compile_plan(invalid, extra_bindings)
        plan.update(fps=120, frame_count=7201, duration_ms=60008)
        plan['shots'][-1]['end_frame'] = 7201
        with self.assertRaisesRegex(ValueError, '7200 frames'):
            compile_plan(plan, bindings)

    def test_slow_frame_rate_has_an_independent_runtime_limit(self):
        plan, bindings = inputs()
        plan.update(fps=1, frame_count=120, duration_ms=120000)
        plan['shots'][-1]['end_frame'] = 120
        self.assertEqual(compile_plan(plan, bindings)['plan'], plan)
        plan.update(frame_count=121, duration_ms=121000)
        plan['shots'][-1]['end_frame'] = 121
        with self.assertRaisesRegex(ValueError, '120 seconds'):
            compile_plan(plan, bindings)
