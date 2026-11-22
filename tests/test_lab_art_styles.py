from copy import deepcopy
import unittest

from command_center import lab_art_styles as lab


def example():
    return deepcopy(lab.EXERCISES[0]['example'])


def failed(data):
    return {r['id'] for r in lab.assess('art-styles', data) if r['status'] == 'fail'}


class ArtStylesTests(unittest.TestCase):
    def test_example_uses_measured_costs_and_matches_the_rubric(self):
        data = example()
        original = deepcopy(data)
        result = lab.assess('art-styles', data)
        self.assertEqual([r['id'] for r in result], [c['id'] for c in lab.EXERCISES[0]['criteria']])
        self.assertTrue(all(r['status'] == 'pass' and r['detail'] for r in result))
        self.assertIn('6 of 7', result[3]['detail'])
        self.assertIn('[11210, 5750]', result[5]['detail'])
        self.assertEqual(result, lab.assess('art-styles', data))
        self.assertEqual(original, data)

    def test_swatch_role_identity_and_color_aliases(self):
        data = example()
        kit = data['handheld']['kit']
        kit['truss']['swatch'], kit['wall']['swatch'] = kit['wall']['swatch'], kit['truss']['swatch']
        self.assertEqual(failed(data), {'palette'})
        data = example()
        data['palette']['oxide'] = {k: v.lower() for k, v in data['palette']['slate'].items()}
        self.assertEqual(failed(data), {'palette'})
        data = example()
        for tier in ('full', 'handheld'):
            data[tier]['kit']['wall']['swatch'] = 'oxide'
        self.assertEqual(failed(data), {'palette'})

    def test_material_bands_and_roughness_separation_are_independent_of_cost(self):
        data = example()
        data['handheld']['kit']['truss']['bands'] = 2
        self.assertEqual(failed(data), {'materials'})
        data = example()
        data['handheld']['kit']['signal']['roughness'] = 38
        self.assertFalse(failed(data))
        data['handheld']['kit']['signal']['roughness'] = 39
        self.assertEqual(failed(data), {'materials'})
        for tier in ('full', 'handheld'):
            data[tier]['kit']['signal']['roughness'] = 55
            data[tier]['kit']['wall']['roughness'] = 80
        self.assertFalse(failed(data))  # Exactly 25 points.
        data['full']['kit']['wall']['roughness'] -= 1
        self.assertEqual(failed(data), {'materials'})

    def test_framing_border_centroid_and_four_connected_signal(self):
        for grid in (
            ['......@@..', '......@@..', '..........', '.....#....', '..........', '..........'],
            ['..........', '..@@......', '..@@......', '.....#....', '..........', '..........'],
            ['..........', '........##', '..........', '..........', '......@@..', '......@@..'],
            ['..........', '.....@@...', '.......@@.', '.....#....', '..........', '..........'],
            ['..........', '......@...', '......@...', '.....#....', '..........', '..........'],
            ['..........'] * 6,
        ):
            with self.subTest(grid=grid):
                data = example()
                for tier in ('full', 'handheld'):
                    data[tier]['thumbnail'] = list(grid)
                self.assertIn('composition', failed(data))

    def test_iou_uses_union_with_added_and_removed_cells_and_matching_frames(self):
        data = example()
        a = ['..........', '......@@..', '......@@..', '.....#....', '..........', '..........']
        b = a.copy()
        b[2] = '.....@@@..'
        b[1] = '......@...'
        data['full']['thumbnail'],data['handheld']['thumbnail'] = a,b
        self.assertEqual(failed(data), {'silhouette'})  # Three overlapping cells divided by five.
        b[1] = a[1]
        self.assertFalse(failed(data))
        data['handheld']['thumbnail'] = [row + '.' for row in b]
        self.assertEqual(failed(data), {'silhouette'})
        # Four against three would pass IoU at the exact 75% boundary, independently of minimum area.
        data['handheld']['thumbnail'] = [a[0], '......@...', *a[2:]]
        self.assertEqual(failed(data), {'composition'})

    def test_contrast_samples_only_actual_neighbors_in_both_lights(self):
        data = example()
        data['palette']['oxide']['dusk'] = data['palette']['ochre']['dusk']
        self.assertEqual(failed(data), {'lighting'})
        for tier in ('full', 'handheld'):
            grid = data[tier]['thumbnail']
            grid[:] = [row.replace('#', '.') for row in grid]
            grid[-1] = '##########'
        self.assertFalse(failed(data))  # No signal pixel touches the truss.
        data['palette']['slate']['day'] = data['palette']['ochre']['day']
        self.assertEqual(failed(data), {'lighting'})

    def test_budget_enforces_reductions_and_same_number_of_instances(self):
        data = example()
        small = data['handheld']
        small['kit']['signal']['triangles'] += 250
        small['triangles'] += 250
        self.assertFalse(failed(data))  # Exactly both device limits.
        small['kit']['signal']['triangles'] += 1
        small['triangles'] += 1
        self.assertEqual(failed(data), {'device-budget'})
        data = example()
        data['handheld']['kit']['truss']['copies'] -= 1
        data['handheld']['triangles'] -= 310
        self.assertEqual(failed(data), {'device-budget'})
        data = example()
        data['full']['atlas'] = data['handheld']['atlas'].copy()
        data['full']['atlas_bytes'] = data['handheld']['atlas_bytes']
        self.assertEqual(failed(data), {'device-budget'})
        data = example()
        data['handheld']['atlas'] = [257, 256]
        data['handheld']['atlas_bytes'] = 257 * 256 * 4
        self.assertEqual(failed(data), {'device-budget'})

    def test_reconciles_every_prediction_and_shared_rectangular_atlas(self):
        for tier in ('full', 'handheld'):
            for field in ('triangles', 'atlas_bytes'):
                with self.subTest(tier=tier, field=field):
                    data = example()
                    data[tier][field] -= 1
                    self.assertEqual(failed(data), {'cost-predictions'})
        data = example()
        data['handheld'].update(atlas=[128, 256], atlas_bytes=131072)
        self.assertFalse(failed(data))

    def test_malformed_or_unbounded_inputs(self):
        for change in (
            lambda d: d.update(bands=True), lambda d: d.update(palette=[]),
            lambda d: d['palette']['slate'].update(dusk='#ABCDE'),
            lambda d: d['palette']['slate'].update(extra=1),
            lambda d: d['full']['kit']['wall'].update(swatch='unknown'),
            lambda d: d['full']['kit']['wall'].update(copies=0),
            lambda d: d['full']['kit']['wall'].update(roughness=100.5),
            lambda d: d['full']['kit'].pop('signal'),
            lambda d: d['full'].update(thumbnail=[]), lambda d: d['full'].update(thumbnail=[{}] * 6),
            lambda d: d['full']['thumbnail'].append('123456'),
            lambda d: d['full']['thumbnail'].append('.........'),
            lambda d: d['full'].update(atlas=[4097, 1]), lambda d: d['full'].update(atlas_bytes=-1),
            lambda d: d.update(unrelated=True),
        ):
            with self.subTest(change=change):
                data = example()
                change(data)
                with self.assertRaises(ValueError):
                    lab.assess('art-styles', data)
        for key, data in [('other', {}), ('art-styles', None)]:
            with self.assertRaises(ValueError):
                lab.assess(key, data)
