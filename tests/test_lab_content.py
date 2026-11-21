import copy
import unittest

from command_center.lab_content import EXERCISES, assess


def sample(exercise_id):
    return copy.deepcopy(next(row['example'] for row in EXERCISES if row['id'] == exercise_id))


def results(exercise_id, submission):
    return {row['id']: row for row in assess(exercise_id, submission)}


class LabContentTests(unittest.TestCase):
    def test_catalog_examples_match_ordered_criteria_and_are_repeatable(self):
        self.assertEqual([row['id'] for row in EXERCISES], ['modeling', 'textures', 'animation'])
        for exercise in EXERCISES:
            with self.subTest(exercise=exercise['id']):
                self.assertEqual(set(exercise), {'id', 'title', 'brief', 'criteria', 'example'})
                before = copy.deepcopy(exercise)
                scores = assess(exercise['id'], exercise['example'])
                ids = [criterion['id'] for criterion in exercise['criteria']]
                self.assertEqual(len(set(ids)), len(ids))
                self.assertEqual([row['id'] for row in scores], ids)
                self.assertTrue(all(set(row) == {'id', 'status', 'detail'} for row in scores))
                self.assertTrue(all(row['status'] == 'pass' and row['detail'] for row in scores))
                self.assertEqual(assess(exercise['id'], exercise['example']), scores)
                self.assertEqual(exercise, before)

    def test_modeling_computes_boundary_degeneracy_and_winding(self):
        mesh = sample('modeling')
        mesh['lod0']['triangles'].pop()
        open_result = results('modeling', mesh)['topology']
        self.assertEqual(open_result['status'], 'fail')
        self.assertIn('3 boundary', open_result['detail'])
        mesh = sample('modeling')
        mesh['lod0']['triangles'][0].reverse()
        self.assertEqual(results('modeling', mesh)['topology']['status'], 'fail')
        mesh = sample('modeling')
        mesh['lod0']['triangles'].append(mesh['lod0']['triangles'][0][:])
        self.assertEqual(results('modeling', mesh)['topology']['status'], 'fail')
        mesh = sample('modeling')
        a, b, c = mesh['lod0']['triangles'][0]
        va, vb = mesh['lod0']['vertices'][a], mesh['lod0']['vertices'][b]
        mesh['lod0']['vertices'][c] = [(x + y) / 2 for x, y in zip(va, vb)]
        self.assertEqual(results('modeling', mesh)['geometry']['status'], 'fail')

    def test_modeling_checks_bounds_and_counts_submitted_lod_triangles(self):
        mesh = sample('modeling')
        mesh['lod1'] = copy.deepcopy(mesh['lod0'])
        scores = results('modeling', mesh)
        self.assertEqual(scores['lod-budget']['status'], 'fail')
        self.assertEqual(scores['topology']['status'], 'pass')
        mesh = sample('modeling')
        for p in mesh['lod1']['vertices']:
            p[1] += 0.5
        self.assertEqual(results('modeling', mesh)['bounds']['status'], 'fail')
        # Unreferenced extremal vertices cannot make a small prop meet dimensions.
        mesh = sample('modeling')
        verts = mesh['lod0']['vertices']
        mesh['lod0']['vertices'] = [[v / 2 for v in p] for p in verts] + verts
        scores = results('modeling', mesh)
        self.assertEqual(scores['bounds']['status'], 'fail')
        self.assertEqual(scores['topology']['status'], 'fail')

    def test_modeling_rejects_pinched_vertex_with_paired_edges(self):
        mesh = sample('modeling')
        # Join two differently sized tetrahedra at vertex zero only.
        tet = mesh['lod1']
        tet['vertices'] += [[2 * x for x in p] for p in tet['vertices'][1:]]
        tet['triangles'] += [[i + 3 if i else 0 for i in t] for t in tet['triangles'][:]]
        row = results('modeling', mesh)['topology']
        self.assertEqual(row['status'], 'fail')
        self.assertIn('1 disconnected vertex fan', row['detail'])

    def test_texture_uvs_material_roles_color_spaces_and_dimensions(self):
        material = sample('textures')
        material['uvs'][0] = [1.25, 0.0]
        self.assertEqual(results('textures', material)['uv-bounds']['status'], 'fail')
        material['uvs'] = [[0.1, 0], [0.2, 0], [0.3, 0], [0.4, 0]]
        self.assertEqual(results('textures', material)['uv-area']['status'], 'fail')
        material['maps'][0]['space'] = 'linear'
        material['maps'][1]['width'] = 700
        scores = results('textures', material)
        self.assertEqual(scores['map-metadata']['status'], 'fail')
        self.assertEqual(scores['resolution']['status'], 'fail')
        material = sample('textures')
        material['maps'] = [material['maps'][0]] * 3
        self.assertEqual(results('textures', material)['map-metadata']['status'], 'fail')
        material = sample('textures')
        material['maps'][1]['channels'] = 1
        self.assertEqual(results('textures', material)['map-metadata']['status'], 'fail')

    def test_texture_memory_sums_all_mip_dimensions_and_channels(self):
        material = sample('textures')
        for image in material['maps']:
            image.update(width=1024, height=1024, channels=3)
        scores = results('textures', material)
        self.assertEqual(scores['resolution']['status'], 'pass')
        self.assertEqual(scores['memory']['status'], 'fail')
        self.assertIn('12582909 bytes', scores['memory']['detail'])
        material['maps'] = [dict(role='normal', space='linear', width=3, height=5, channels=3)]
        # (3x5 + 1x2 + 1x1) pixels at three bytes per pixel.
        self.assertIn('54 bytes', results('textures', material)['memory']['detail'])

    def test_rig_reports_cycles_multiple_roots_dangling_parents_and_tracks(self):
        clip = sample('animation')
        clip['joints'][1]['parent'] = clip['joints'][2]['name']
        clip['joints'][2]['parent'] = clip['joints'][1]['name']
        self.assertEqual(results('animation', clip)['hierarchy']['status'], 'fail')
        for parent in ('unknown', None):
            clip = sample('animation')
            clip['joints'][1]['parent'] = parent
            self.assertEqual(results('animation', clip)['hierarchy']['status'], 'fail')
        clip = sample('animation')
        clip['tracks'][0]['joint'] = 'orphan'
        scores = results('animation', clip)
        self.assertEqual(scores['coverage']['status'], 'fail')
        self.assertEqual(scores['root-motion']['status'], 'fail')

    def test_animation_checks_interior_samples_order_loop_and_local_motion(self):
        clip = sample('animation')
        clip['tracks'][0]['keys'][1]['translation'] = [0.03, 0, 0]
        self.assertEqual(results('animation', clip)['root-motion']['status'], 'fail')
        track = clip['tracks'][1]['keys']
        track[-1]['translation'] = [0, 0.04, 0]
        self.assertEqual(results('animation', clip)['loop']['status'], 'fail')
        track[1]['translation'] = [0, 3, 0]
        self.assertEqual(results('animation', clip)['motion']['status'], 'fail')
        for time in (track[0]['time_s'], -0.1, clip['duration_s'] + 0.1):
            track[1]['time_s'] = time
            self.assertEqual(results('animation', clip)['timing']['status'], 'fail')
        clip = sample('animation')
        for track in clip['tracks']:
            for key in track['keys']:
                key['translation'] = [0, 0, 0]
        self.assertEqual(results('animation', clip)['motion']['status'], 'fail')

    def test_alternate_assets_meet_the_measured_limits(self):
        mesh = sample('modeling')
        # A consistently wound cube gives a different, valid 12-to-4 triangle submission.
        mesh['lod0'] = {
            'vertices': [[x, y, z] for z in (-0.5, 0.5) for y in (-0.5, 0.5) for x in (-0.5, 0.5)],
            'triangles': [[0, 2, 1], [1, 2, 3], [4, 5, 6], [5, 7, 6],
                          [0, 1, 4], [1, 5, 4], [2, 6, 3], [3, 6, 7],
                          [0, 4, 2], [2, 4, 6], [1, 3, 5], [3, 7, 5]],
        }
        material = sample('textures')
        material['maps'].reverse()
        for image in material['maps']:
            image.update(width=128, height=128, channels=3)
        material['triangles'] = [[0, 2, 1]]  # Clockwise UV triangles can be intentional.
        clip = sample('animation')
        clip['joints'].reverse()
        for key in clip['tracks'][0]['keys']:
            key['translation'][2] = 0.02
        for track in clip['tracks'][1:]:
            track['keys'][1]['time_s'] = 0.01
            track['keys'][1]['translation'] = [0.02, 0, 0]
            track['keys'][2]['translation'] = [0.01, 0, 0]
        clip['tracks'].reverse()
        for name, data in [('modeling', mesh), ('textures', material), ('animation', clip)]:
            with self.subTest(exercise=name):
                failures = [row['detail'] for row in assess(name, data) if row['status'] == 'fail']
                self.assertEqual(failures, [])

    def test_malformed_schema_is_rejected_with_value_error(self):
        invalid = []
        for key in ['modeling', 'textures', 'animation']:
            invalid += [(key, []), (key, {'file': '/tmp/mesh'}), (key, {**sample(key), 'extra': 1})]
        for vec in ([True, 0, 0], [1e309, 0, 0], [float('nan'), 0, 0],
                    [10 ** 1000, 0, 0], ['0', 0, 0], [2, 3]):
            mesh = sample('modeling')
            mesh['lod0']['vertices'][0] = vec
            invalid.append(('modeling', mesh))
        for index in (-1, 900, False, 1.0):
            mesh = sample('modeling')
            mesh['lod0']['triangles'][0][0] = index
            invalid.append(('modeling', mesh))
        material = sample('textures')
        material['maps'][0]['space'] = 'something'
        invalid.append(('textures', material))
        for bad_keys in ([], [{}] * 129):
            clip = sample('animation')
            clip['tracks'][0]['keys'] = bad_keys
            invalid.append(('animation', clip))
        clip = sample('animation')
        clip['joints'][0]['name'] = 'a' * 1000
        invalid.append(('animation', clip))
        material = sample('textures')
        material['uvs'] *= 300
        invalid.append(('textures', material))
        invalid.extend([('unrecognized', {}), (None, {}), ([], {})])
        for key, submission in invalid:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    assess(key, submission)
