from copy import deepcopy
import unittest

from command_center import lab_voice_direction as voice


def example():
    return deepcopy(voice.EXERCISES[0]['example'])


def failed(data):
    return {row['id'] for row in voice.assess('voice-direction', data) if row['status'] == 'fail'}


class VoiceDirectionTests(unittest.TestCase):
    def test_example_matches_criteria_and_is_deterministic(self):
        data = example()
        before = deepcopy(data)
        rows = voice.assess('voice-direction', data)
        self.assertEqual([r['id'] for r in rows], [c['id'] for c in voice.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in rows))
        self.assertEqual(voice.assess('voice-direction', data), rows)
        self.assertEqual(data, before)

    def test_all_roles_must_be_used_with_original_script_terms(self):
        for mutate in (lambda d: d['cast'][2].update(role='npc'),
                       lambda d: d['lines'][1].update(speaker='missing'),
                       lambda d: d['lines'][0].update(term='arrow'),
                       lambda d: d['lines'][0].update(term='yarrow')):
            with self.subTest(mutate=mutate):
                data = example()
                mutate(data)
                self.assertIn('casting-briefs', failed(data))

    def test_each_take_fault_is_recomputed_even_if_an_editor_marks_it_clean(self):
        changes = [('clearance', {'consent': 'withdrawn'}), ('clearance', {'style': 'unauthorized-imitation'}),
                   ('casting', {'performer': 'actor-z'}), ('delivery', {'delivery': 'confide'}),
                   ('script', {'transcript': 'Yarrow Pier is dark.'}), ('pronunciation', {'reading': 'yer-ROW'}),
                   ('clipping', {'clipped_samples': 1}), ('timing', {'out_ms': 2401})]
        for fault, change in changes:
            with self.subTest(fault=fault, change=change):
                data = example()
                line = data['lines'][0]
                take = line['takes'][1]
                take.update(change)
                conflicts = failed(data)
                self.assertTrue({'take-diagnostics', 'edit-selection'} <= conflicts)
                self.assertEqual('use-permission' in conflicts, fault == 'clearance')
                take['faults'] = [fault]
                line.update(selected=None, caption=None)
                self.assertFalse(failed(data))

    def test_hold_is_required_without_a_usable_take_and_a_pickup_can_resolve_it(self):
        data = example()
        line = data['lines'][1]
        self.assertIsNone(line['selected'])
        take = deepcopy(line['takes'][0])
        take.update(id='fog-b', clipped_samples=0, faults=[])
        line['takes'].append(take)
        self.assertEqual(failed(data), {'edit-selection'})
        line.update(selected='fog-b', caption={'speaker': line['speaker'], 'text': line['text'],
                                               'start_ms': 4160, 'end_ms': 6820})
        self.assertFalse(failed(data))

    def test_diagnosis_requires_every_actual_fault_without_speculative_ones(self):
        data = example()
        take = data['lines'][0]['takes'][0]
        take['faults'].reverse()
        self.assertFalse(failed(data))
        take['faults'].append('casting')
        self.assertEqual(failed(data), {'take-diagnostics'})
        take['faults'] = []
        self.assertEqual(failed(data), {'take-diagnostics'})

    def test_unlicensed_imitation_or_audition_cannot_be_waved_through(self):
        for change in ({'style': 'unauthorized-imitation'}, {'consent': 'audition-only'},
                       {'consent': 'unconfirmed'}, {'consent': 'withdrawn'}):
            with self.subTest(change=change):
                data = example()
                take = data['lines'][2]['takes'][1]
                take.update(change, faults=['clearance'])
                self.assertEqual(failed(data), {'edit-selection', 'use-permission'})

    def test_timing_uses_speech_end_and_matches_exact_absolute_caption(self):
        data = example()
        line = data['lines'][0]
        take = line['takes'][1]
        take.update(in_ms=0, out_ms=2400, clip_ms=4500)
        line['caption'].update(start_ms=1000, end_ms=3400)
        self.assertFalse(failed(data))
        for change in ({'end_ms': 3399}, {'start_ms': 0}, {'speaker': 'narrator'}, {'text': 'Yarrow is lit.'}):
            with self.subTest(change=change):
                variant = deepcopy(data)
                variant['lines'][0]['caption'].update(change)
                self.assertEqual(failed(variant), {'caption-conform'})
        for change in ({'out_ms': 2401}, {'out_ms': 0}, {'out_ms': 100, 'in_ms': 102}, {'clip_ms': 2399}):
            with self.subTest(change=change):
                variant = deepcopy(data)
                variant['lines'][0]['takes'][1].update(change)
                self.assertIn('edit-selection', failed(variant))

    def test_invalid_references_and_held_lines_cannot_publish_captions(self):
        data = example()
        data['lines'][1]['caption'] = deepcopy(data['lines'][0]['caption'])
        self.assertEqual(failed(data), {'caption-conform'})
        data = example()
        data['lines'][0].update(selected='absent', caption=None)
        self.assertEqual(failed(data), {'caption-conform', 'edit-selection', 'use-permission'})

    def test_clean_alternates_are_allowed_but_all_clean_or_all_held_is_incomplete(self):
        data = example()
        line = data['lines'][0]
        alternate = deepcopy(line['takes'][1])
        alternate['id'] = 'another-read'
        line['takes'].append(alternate)
        line['selected'] = alternate['id']
        self.assertFalse(failed(data))
        data['lines'][0]['takes'].pop(0)
        data['lines'][1]['takes'][0].update(clipped_samples=0, faults=[])
        data['lines'][2]['takes'].pop(0)
        self.assertIn('take-diagnostics', failed(data))
        data = example()
        for line in data['lines']:
            line.update(selected=None, caption=None)
        self.assertEqual(failed(data), {'edit-selection'})

    def test_strict_schema_rejects_unbounded_or_malformed_records(self):
        cases = (lambda d: d.update(source='actual-recording'), lambda d: d.update(cast=d['cast'] * 3),
                 lambda d: d['cast'][0].update(brief='\u200b'),
                 lambda d: d['cast'][0].update(id=d['cast'][1]['id']),
                 lambda d: d['lines'][0].update(start_ms=True),
                 lambda d: d['lines'][0].update(slot_ms=0),
                 lambda d: d['lines'][0].update(context='x' * 241),
                 lambda d: d['lines'][0].update(takes=[]),
                 lambda d: d['lines'][0]['takes'][1].update(id='deck-a'),
                 lambda d: d['lines'][0]['takes'][0].update(faults=['timing', 'timing']),
                 lambda d: d['lines'][0]['takes'][0].update(in_ms=1.5),
                 lambda d: d['lines'][0]['takes'][0].update(clip_ms=60001),
                 lambda d: d['lines'][0]['takes'][0].update(extra='private note'),
                 lambda d: d['lines'][0]['caption'].update(start_ms=-1),
                 lambda d: d['lines'][0].update(selected={}))
        for mutate in cases:
            with self.subTest(mutate=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    voice.assess('voice-direction', data)
        with self.assertRaises(ValueError):
            voice.assess('other', example())


if __name__ == '__main__':
    unittest.main()
