import copy
import json
import unittest

from command_center.lab_design import EXERCISES, assess


def example(exercise):
    return copy.deepcopy(next(row['example'] for row in EXERCISES if row['id'] == exercise))


def checks(exercise, artifact):
    return {row['id']: row['status'] for row in assess(exercise, artifact)}


def beat(name, targets=(), requires=(), grants=()):
    return {'id': name, 'line': 'Enter ' + name, 'requires': list(requires),
            'grants': list(grants), 'choices': [{'label': 'Go to ' + t, 'to': t} for t in targets]}


class DesignLabTests(unittest.TestCase):
    def test_examples_are_deterministic_json_and_pass_every_advertised_criterion(self):
        self.assertEqual({r['id'] for r in EXERCISES}, {'storytelling', 'level-design', 'game-design'})
        for row in EXERCISES:
            with self.subTest(exercise=row['id']):
                artifact = json.loads(json.dumps(row['example']))
                results = assess(row['id'], artifact)
                self.assertEqual(results, assess(row['id'], artifact))
                self.assertEqual(artifact, row['example'])
                self.assertEqual([r['id'] for r in results], [c['id'] for c in row['criteria']])
                for check in results:
                    self.assertEqual(set(check), {'id', 'status', 'detail'})
                    self.assertEqual(check['status'], 'pass', check['detail'])
                    self.assertTrue(check['detail'].strip())

    def test_gameplay_requires_payment_before_collection(self):
        artifact = example('game-design')
        artifact['rounds'][0] = {'cost': 7, 'salvage': 8}
        result = checks('game-design', artifact)
        self.assertEqual(result['standard'], 'pass')
        self.assertEqual(result['lean'], 'fail')
        artifact['rounds'][0]['cost'] = 9
        self.assertEqual(checks('game-design', artifact)['standard'], 'fail')

    def test_gameplay_gains_and_losses_are_measured(self):
        artifact = {'rounds': [{'cost': 1, 'salvage': 8}] * 5}
        result = checks('game-design', artifact)
        self.assertEqual(result['standard'], 'fail')  # Runaway resource growth.
        self.assertEqual(result['stranded'], 'fail')
        self.assertEqual(result['pacing'], 'fail')

    def test_continuity_checks_every_path_to_a_shared_scene(self):
        artifact = {'start': 'start', 'nodes': [
            beat('start', ['rescue', 'ignore']), beat('rescue', ['reunion'], grants=['safe']),
            beat('ignore', ['reunion']), beat('reunion', requires=['safe'])]}
        result = checks('storytelling', artifact)
        self.assertEqual(result['continuity'], 'fail')
        self.assertEqual(result['reachability'], 'pass')  # Reunion is legal on the rescue path.
        self.assertEqual(result['resolution'], 'fail')  # Ignoring strands the player.
        self.assertEqual(result['agency'], 'fail')
        artifact['nodes'][2]['grants'] = ['safe']
        self.assertEqual(checks('storytelling', artifact)['continuity'], 'pass')

    def test_story_detects_unreachable_scenes_and_dangling_choices(self):
        artifact = example('storytelling')
        artifact['nodes'].append(beat('unused', ['typo']))
        self.assertEqual(checks('storytelling', artifact)['reachability'], 'fail')
        artifact['nodes'] = [beat('start', ['typo'])]
        artifact['start'] = 'start'
        self.assertEqual(checks('storytelling', artifact)['reachability'], 'fail')
        artifact['start'] = 'missing'
        self.assertTrue(all(v == 'fail' for v in checks('storytelling', artifact).values()))

    def test_optional_loop_terminates_and_trapped_loop_fails_resolution(self):
        graph = {'start': 'start', 'nodes': [
            beat('start', ['loop', 'ending']), beat('loop', ['loop', 'second']), beat('ending'), beat('second')]}
        self.assertEqual(checks('storytelling', graph)['resolution'], 'pass')
        graph['nodes'][1] = beat('loop', ['loop'])
        self.assertEqual(checks('storytelling', graph)['resolution'], 'fail')

    def test_two_endings_visible_after_same_merge_are_not_two_distinct_consequences(self):
        # Both alternatives at 'start' converge; only the later switch has agency.
        graph = {'start': 'start', 'nodes': [
            beat('start', ['a', 'b']), beat('a', ['switch']), beat('b', ['switch']),
            beat('switch', ['x', 'y']), beat('x'), beat('y')]}
        self.assertEqual(checks('storytelling', graph)['agency'], 'pass')
        graph['nodes'][3] = beat('switch', ['x'])
        self.assertEqual(checks('storytelling', graph)['agency'], 'fail')

    def test_pair_of_paths_sharing_a_bottleneck_fails_independence(self):
        artifact = {'grid': ['###########', '#...#.....#', '#S....###G#', '#...#.....#', '###########']}
        result = checks('level-design', artifact)
        self.assertEqual(result['reachability'], 'pass')
        self.assertEqual(result['alternate-routes'], 'fail')

    def test_adjacent_endpoints_require_a_real_second_route(self):
        self.assertEqual(checks('level-design', {'grid': ['###', '#SG', '###']})['alternate-routes'], 'fail')
        self.assertEqual(checks('level-design', {'grid': ['#..', '#SG', '###']})['alternate-routes'], 'pass')

    def test_level_detects_unreachable_space_and_tight_cover(self):
        blocked = {'grid': ['########', '#S...#G#', '########']}
        self.assertEqual(checks('level-design', blocked)['reachability'], 'fail')
        self.assertEqual(checks('level-design', blocked)['spacing'], 'fail')
        close = {'grid': ['###########', '#...CC....#', '#S#######G#', '#.........#', '###########']}
        result = checks('level-design', close)
        self.assertEqual(result['alternate-routes'], 'pass')
        self.assertEqual(result['cover'], 'fail')

    def test_malformed_or_unbounded_submissions_raise_value_error(self):
        invalid = [
            ('missing', {}), ('game-design', []), ('game-design', {'rounds': []}),
            ('game-design', {'rounds': [{'cost': True, 'salvage': 1}] * 5}),
            ('game-design', {'rounds': [{'cost': 4, 'salvage': 21}] * 5}),
            ('game-design', {'rounds': [{'cost': 2, 'salvage': 4, 'score': 99}] * 5}),
            ('storytelling', {'start': 's', 'nodes': [beat('s'), beat('s')]}),
            ('storytelling', {'start': 's', 'nodes': [beat('s', grants=['f'+str(i) for i in range(9)])]}),
            ('storytelling', {'start': 's', 'nodes': [{'id': 's'}]}),
            ('storytelling', {'start': 's', 'nodes': [beat('s', ['bad-target!'])]}),
            ('level-design', {'grid': ['S..', '..G', '##']}),
            ('level-design', {'grid': ['S?G', '...', '###']}),
            ('level-design', {'grid': ['SSG', '...', '###']}),
            ('level-design', {'grid': ['S.G'] * 25}),
        ]
        for exercise, artifact in invalid:
            with self.subTest(exercise=exercise, artifact=artifact):
                with self.assertRaises(ValueError):
                    assess(exercise, artifact)
