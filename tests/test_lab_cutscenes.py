from copy import deepcopy
import unittest

from command_center import lab_cutscenes


def example():
    return deepcopy(lab_cutscenes.EXERCISES[0]['example'])


def failed(data):
    return {row['id'] for row in lab_cutscenes.assess('cutscenes', data) if row['status'] == 'fail'}


class CutsceneLabTests(unittest.TestCase):
    def test_example_is_replayable_and_matches_published_criteria(self):
        data = example()
        original = deepcopy(data)
        results = lab_cutscenes.assess('cutscenes', data)
        self.assertEqual([r['id'] for r in results], [c['id'] for c in lab_cutscenes.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in results))
        self.assertEqual(lab_cutscenes.assess('cutscenes', data), results)
        self.assertEqual(data, original)

    def test_duration_matches_frame_rate_to_nearest_millisecond(self):
        data = example()
        data.update(fps=24, frame_count=145, duration_ms=6042)
        data['shots'][-1]['end_frame'] = 145
        self.assertEqual(failed(data), set())
        data['duration_ms'] = 6041
        self.assertEqual(failed(data), {'timebase'})

    def test_cuts_must_cover_every_frame_once_in_editorial_order(self):
        for defect in ('gap', 'overlap', 'start', 'end', 'empty', 'reversed', 'single', 'one_camera'):
            with self.subTest(defect=defect):
                data = example()
                shots = data['shots']
                if defect in ('gap', 'overlap'):
                    shots[1]['start_frame'] += 1 if defect == 'gap' else -1
                elif defect == 'start':
                    shots[0]['start_frame'] += 1
                elif defect == 'end':
                    shots[-1]['end_frame'] -= 1
                elif defect == 'empty':
                    shots[1]['end_frame'] = shots[1]['start_frame']
                elif defect == 'reversed':
                    shots.reverse()
                elif defect == 'single':
                    shots[0]['end_frame'] = data['frame_count']
                    del shots[1:]
                else:
                    for shot in shots:
                        shot['camera'] = shots[0]['camera']
                self.assertIn('shot-coverage', failed(data))

    def test_checks_actor_speaker_and_camera_references(self):
        for lane, field in [('shots', 'camera'), ('blocking', 'actor'), ('dialogue', 'speaker')]:
            with self.subTest(lane=lane, field=field):
                data = example()
                data[lane][0][field] = 'unbound'
                self.assertIn('bindings', failed(data))
        data = example()
        data['blocking'].clear()
        self.assertIn('bindings', failed(data))

    def test_speaker_needs_a_blocking_clip_active_on_the_line_start(self):
        data = example()
        line = data['dialogue'][0]
        blocking = next(cue for cue in data['blocking'] if cue['actor'] == line['speaker'])
        blocking['end_frame'] = line['start_frame']
        self.assertEqual(failed(data), {'bindings'})
        blocking['end_frame'] += 1
        self.assertEqual(failed(data), set())

    def test_half_millisecond_ties_round_up(self):
        data = example()
        data.update(fps=16, frame_count=145, duration_ms=9063)
        data['shots'][-1]['end_frame'] = 145
        self.assertEqual(failed(data), set())
        data['duration_ms'] -= 1
        self.assertEqual(failed(data), {'timebase'})

    def test_bounds_are_half_open_and_include_every_cue_lane(self):
        for lane in ('shots', 'blocking', 'dialogue', 'subtitles'):
            for defect in ('negative', 'zero', 'beyond_end'):
                with self.subTest(lane=lane, defect=defect):
                    data = example()
                    cue = data[lane][0]
                    if defect == 'negative':
                        cue['start_frame'] = -1
                    elif defect == 'zero':
                        cue['end_frame'] = cue['start_frame']
                    else:
                        cue['end_frame'] = data['frame_count'] + 1
                    self.assertIn('cue-bounds', failed(data))

    def test_captions_pair_by_line_id_text_and_exact_frame_window(self):
        data = example()
        data['subtitles'].reverse()
        self.assertEqual(failed(data), set())
        for defect in ('extra', 'missing', 'wrong_id', 'duplicate_line', 'text', 'timing', 'none'):
            with self.subTest(defect=defect):
                data = example()
                captions = data['subtitles']
                if defect == 'extra':
                    captions.append(deepcopy(captions[0]))
                elif defect == 'missing':
                    captions.pop()
                elif defect == 'wrong_id':
                    captions[0]['line'] = 'unknown'
                elif defect == 'duplicate_line':
                    data['dialogue'][1]['line'] = data['dialogue'][0]['line']
                elif defect == 'text':
                    captions[0]['text'] = 'Different line.'
                elif defect == 'timing':
                    captions[0]['end_frame'] -= 1
                else:
                    data['dialogue'].clear()
                    captions.clear()
                self.assertIn('subtitle-sync', failed(data))

    def test_exit_cleanup_and_story_state_are_independent(self):
        for path in ('complete', 'skip', 'interrupt'):
            for resource in ('camera', 'input', 'voice', 'subtitles'):
                with self.subTest(path=path, resource=resource):
                    data = example()
                    data['exits'][path]['restore'].remove(resource)
                    self.assertEqual(failed(data), {'restoration'})
            data = example()
            data['exits'][path]['next_state'] = 'wrong_state'
            self.assertEqual(failed(data), {'story-state'})
        data = example()
        data['trigger']['advances_to'] = data['trigger']['requires']
        for result in data['exits'].values():
            result['next_state'] = data['trigger']['requires']
        self.assertEqual(failed(data), {'story-state'})

    def test_invalid_shapes_types_and_lengths_raise_value_error(self):
        for mutate in (
            lambda d: d.update(fps=True),
            lambda d: d.update(duration_ms=float('nan')),
            lambda d: d.update(frame_count='144'),
            lambda d: d['shots'][0].update(start_frame=0.5),
            lambda d: d['shots'][0].update(unexpected=0),
            lambda d: d.update(shots=d['shots'] * 65),
            lambda d: d['actors'].append([]),
            lambda d: d['cameras'].append(d['cameras'][0]),
            lambda d: d['trigger'].update(event=''),
            lambda d: d['dialogue'][0].update(text='  '),
            lambda d: d['subtitles'][0].update(text='x' * 241),
            lambda d: d['dialogue'][0].update(text='\u200b\u200c'),
            lambda d: d['exits'].pop('interrupt'),
            lambda d: d['exits']['skip'].update(restore=['run_script']),
        ):
            with self.subTest(mutation=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab_cutscenes.assess('cutscenes', data)
        for key, value in [('no-such-exercise', {}), ('cutscenes', None), ('cutscenes', [])]:
            with self.assertRaises(ValueError):
                lab_cutscenes.assess(key, value)
