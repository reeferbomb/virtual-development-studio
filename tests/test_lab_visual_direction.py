from copy import deepcopy
import unittest

from command_center import lab_visual_direction as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def failed(submission):
    return {check['id'] for check in lab.assess('visual-direction', submission) if check['status'] == 'fail'}


class VisualDirectionLabTests(unittest.TestCase):
    def test_review_can_pass_with_an_explicit_open_retake(self):
        data = example()
        original = deepcopy(data)
        result = lab.assess('visual-direction', data)
        self.assertEqual([r['id'] for r in result], [r['id'] for r in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in result))
        self.assertIn('detail/open_seams measured 1, target 0–0', result[-1]['detail'])
        self.assertEqual(lab.assess('visual-direction', data), result)
        self.assertEqual(data, original)

    def test_references_must_resolve_to_distinct_sources(self):
        for defect in ('unknown', 'one_source_used', 'repeated_id', 'repeated_digest', 'none'):
            with self.subTest(defect=defect):
                data = example()
                refs = data['references']
                if defect == 'unknown':
                    data['targets']['luma_delta']['reference'] = 'lost_study'
                elif defect == 'one_source_used':
                    for target in data['targets'].values():
                        target['reference'] = refs[0]['id']
                elif defect == 'repeated_id':
                    refs[1]['id'] = refs[0]['id']
                elif defect == 'repeated_digest':
                    refs[1]['sha256'] = refs[0]['sha256']
                else:
                    refs.clear()
                self.assertEqual(failed(data), {'reference-links'})

    def test_matrix_requires_each_view_and_measurement_in_place(self):
        for i, metric in enumerate(('luma_delta', 'door_height_cm', 'roughness_gap_pct', 'foot_drift_mm')):
            with self.subTest(metric=metric):
                data = example()
                value = data['captures'][i]['observations'].pop(metric)
                data['captures'][(i + 1) % 4]['observations'][metric] = value
                self.assertEqual(failed(data), {'observations'})
        data = example()
        data['captures'].pop(0)
        self.assertEqual(failed(data), {'shot-matrix', 'observations'})
        data = example()
        extra = deepcopy(data['captures'][0])
        extra['artifact_sha256'] = '5' * 64
        data['captures'].append(extra)
        self.assertEqual(failed(data), {'shot-matrix'})
        data = example()
        data['captures'].reverse()
        self.assertFalse(failed(data))

    def test_capture_identities_distinguish_build_reference_and_artifacts(self):
        for defect in ('wrong_build', 'copied_capture', 'copied_reference', 'package_as_frame'):
            with self.subTest(defect=defect):
                data = example()
                shot = data['captures'][0]
                if defect == 'wrong_build':
                    shot['build_sha256'] = 'd' * 64
                elif defect == 'copied_capture':
                    shot['artifact_sha256'] = data['captures'][1]['artifact_sha256']
                elif defect == 'copied_reference':
                    shot['artifact_sha256'] = data['references'][0]['sha256']
                else:
                    shot['artifact_sha256'] = data['candidate_sha256']
                self.assertEqual(failed(data), {'capture-identity'})

    def test_delivery_size_and_temporal_evidence_match_brief(self):
        for index, field, value in ((0, 'width', 640), (1, 'height', 360), (2, 'fps', 30),
                                    (2, 'frames', 2), (3, 'frames', 29), (3, 'fps', 24)):
            with self.subTest(index=index, field=field):
                data = example()
                data['captures'][index][field] = value
                self.assertEqual(failed(data), {'delivery-settings'})
        data = example()
        data['brief']['fps'] = 1
        data['captures'][3].update(frames=1, fps=1)
        self.assertEqual(failed(data), {'delivery-settings'})
        data['captures'][3]['frames'] = 2
        self.assertFalse(failed(data))

    def test_findings_use_brief_specific_inclusive_bands_and_measured_view(self):
        data = example()
        shot = data['captures'][0]
        for edge in ('min', 'max'):
            shot['observations']['luma_delta'] = data['targets']['luma_delta'][edge]
            self.assertFalse(failed(data))
        shot['observations']['luma_delta'] += 1
        self.assertEqual(failed(data), {'retakes'})
        row = dict(view='detail', metric='luma_delta', owner='lighting', action='Reduce the key light one stop.')
        data['retakes'].append(row)
        self.assertEqual(failed(data), {'retakes'})
        row['view'] = 'establishing'
        self.assertFalse(failed(data))
        data['targets']['luma_delta']['max'] += 1
        self.assertEqual(failed(data), {'retakes'})
        data['retakes'].pop()
        self.assertFalse(failed(data))

    def test_retake_assignments_cannot_be_missing_duplicated_or_orphaned(self):
        for defect in ('missing', 'duplicate', 'in_band', 'unmeasured'):
            with self.subTest(defect=defect):
                data = example()
                if defect == 'missing':
                    data['retakes'].clear()
                elif defect == 'duplicate':
                    data['retakes'] *= 2
                elif defect == 'in_band':
                    data['captures'][2]['observations']['open_seams'] = 0
                else:
                    data['retakes'][0]['view'] = 'gameplay'
                self.assertEqual(failed(data), {'retakes'})
        data = example()
        data['captures'][2]['observations']['open_seams'] = 0
        data['retakes'].clear()
        self.assertFalse(failed(data))

    def test_malformed_or_unbounded_data_is_rejected(self):
        mutations = (
            lambda d: d['brief'].update(genre='\u200b', platform=' '),
            lambda d: d['brief'].update(width=True),
            lambda d: d['brief'].update(fps=0),
            lambda d: d['references'][0].update(sha256='0' * 63),
            lambda d: d['references'][0].update(source='x' * 241),
            lambda d: d['targets'].pop('open_seams'),
            lambda d: d['targets']['door_height_cm'].update(max=1001),
            lambda d: d['targets']['luma_delta'].update(min=80, max=5),
            lambda d: d['captures'][0].update(view='cover_art'),
            lambda d: d['captures'][0].update(frames=0),
            lambda d: d['captures'][0].update(observations=[]),
            lambda d: d['captures'][0]['observations'].update(beauty=95),
            lambda d: d['captures'][0]['observations'].update(luma_delta=float('nan')),
            lambda d: d['captures'][0]['observations'].update(luma_delta=True),
            lambda d: d['retakes'][0].update(owner=[]),
            lambda d: d['retakes'][0].update(action=''),
            lambda d: d.update(captures=d['captures'] * 3),
            lambda d: d.update(unexpected=True),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = example()
                mutate(data)
                with self.assertRaises(ValueError):
                    lab.assess('visual-direction', data)
        for key, submission in [('elsewhere', {}), ('visual-direction', None)]:
            with self.assertRaises(ValueError):
                lab.assess(key, submission)
