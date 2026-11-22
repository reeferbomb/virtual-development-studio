from copy import deepcopy
import unittest

from command_center import lab_environmental_story as story


def sample():
    return deepcopy(story.EXERCISES[0]['example'])


def assess(data):
    return story.assess('environmental-storytelling', data)


def failures(data):
    return {row['id'] for row in assess(data) if row['status'] == 'fail'}


class EnvironmentalStoryTests(unittest.TestCase):
    def test_example_passes_the_published_criteria_without_mutation(self):
        data = sample()
        before = deepcopy(data)
        result = assess(data)
        self.assertEqual([r['id'] for r in result], [c['id'] for c in story.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in result))
        self.assertEqual(assess(data), result)
        self.assertEqual(data, before)

    def test_unsubmitted_shortcut_bypasses_evidence_and_is_named(self):
        data = sample()
        data['rooms'][0]['exits'].append('footbridge')
        self.assertEqual(failures(data), {'core-inference'})
        core = next(r for r in assess(data) if r['id'] == 'core-inference')
        self.assertIn('mud_yard → footbridge', core['detail'])

    def test_notes_and_direct_statements_cannot_substitute_for_inference(self):
        for update in ({'kind': 'note'}, {'before': 'hail_fell', 'after': 'roof_patched'}):
            data = sample()
            data['rooms'][3]['clue'].update(update)
            with self.subTest(update=update):
                self.assertEqual(failures(data), {'core-inference'})
        data = sample()
        data['rooms'][2]['clue']['kind'] = 'note'
        self.assertEqual(failures(data), {'chronology'})

    def test_full_history_cannot_be_pooled_across_incompatible_walks(self):
        data = sample()
        data['rooms'][3]['clue'] = data['rooms'][2]['clue']
        data['rooms'][2]['clue'] = None
        self.assertEqual(failures(data), {'chronology', 'core-inference'})
        # An actual detour can collect the last clue before the middle one.
        data['rooms'][3]['exits'].append('tool_bay')
        self.assertEqual(failures(data), {'core-inference'})

    def test_alternate_paths_can_use_different_intermediate_events(self):
        def room(name, exits, pair=None):
            clue = dict(kind='wear', observation='A groove runs across the older mark.',
                        before=pair[0], after=pair[1]) if pair else None
            return dict(id=name, exits=exits, clue=clue)

        data = {
            'history': ['rain', 'shift', 'haul', 'seal'], 'core': ['rain', 'seal'],
            'entry': 'gate', 'exit': 'dock',
            'rooms': [room('gate', ['a', 'c']), room('a', ['b'], ('rain', 'shift')),
                      room('b', ['dock'], ('shift', 'seal')), room('c', ['d'], ('rain', 'haul')),
                      room('d', ['dock'], ('haul', 'seal')), room('dock', [])],
            'routes': [['gate', 'a', 'b', 'dock'], ['gate', 'c', 'd', 'dock']],
        }
        self.assertEqual(failures(data), {'chronology'})

    def test_reversed_or_reflexive_clues_and_reversed_core(self):
        for before, after in [('orchids_returned', 'roof_patched'), ('roof_patched', 'roof_patched')]:
            data = sample()
            data['rooms'][2]['clue'].update(before=before, after=after)
            self.assertEqual(failures(data), {'chronology', 'core-inference'})
        data = sample()
        data['rooms'][2]['clue'].update(kind='note', before='orchids_returned', after='roof_patched')
        self.assertEqual(failures(data), {'chronology'})
        data = sample()
        data['core'].reverse()
        self.assertEqual(failures(data), {'core-inference'})

    def test_dead_end_and_disconnected_room_do_not_count_as_explorable(self):
        for link in (True, False):
            data = sample()
            data['rooms'].append({'id': 'cellar', 'exits': ['cellar'], 'clue': None})
            if link:
                data['rooms'][1]['exits'].append('cellar')
            self.assertEqual(failures(data), {'exploration'})
        data = sample()
        for room in data['rooms']:
            room['exits'] = [n for n in room['exits'] if n != data['exit']]
        self.assertEqual(failures(data), {'core-inference', 'exploration', 'alternate-routes', 'chronology'})

    def test_demonstrated_routes_must_be_legal_and_each_own_a_distinct_room(self):
        for route in (['mud_yard', 'tool_bay', 'footbridge'], ['mud_yard', 'orchid_bench', 'footbridge'],
                      ['mud_yard', 'missing', 'footbridge']):
            data = sample()
            data['routes'][1] = route
            self.assertEqual(failures(data), {'alternate-routes'})

    def test_invalid_shapes_and_references_raise_value_error(self):
        for change in (
            lambda p: p.update(extra=[]),
            lambda p: p.update(history=['x'] * 6),
            lambda p: p.update(core=['hail_fell', 'hail_fell']),
            lambda p: p.update(core=['hail_fell', 'missing']),
            lambda p: p.update(entry=p['exit']),
            lambda p: p.update(rooms=p['rooms'] * 4),
            lambda p: p['rooms'].append(deepcopy(p['rooms'][0])),
            lambda p: p['rooms'][0]['exits'].append('glazing_bay'),
            lambda p: p['rooms'][0]['exits'].append('missing'),
            lambda p: p['rooms'][0]['clue'].update(kind=[]),
            lambda p: p['rooms'][0]['clue'].update(before='missing'),
            lambda p: p['rooms'][0]['clue'].update(observation='  '),
            lambda p: p['rooms'][-1].update(clue=p['rooms'][0]['clue']),
            lambda p: p['rooms'][-1]['exits'].append('mud_yard'),
            lambda p: p['routes'][0].insert(1, 'mud_yard'),
        ):
            data = sample()
            change(data)
            with self.subTest(mutation=change), self.assertRaises(ValueError):
                assess(data)
        for exercise, data in [('unknown', sample()), ('environmental-storytelling', None)]:
            with self.assertRaises(ValueError):
                story.assess(exercise, data)
