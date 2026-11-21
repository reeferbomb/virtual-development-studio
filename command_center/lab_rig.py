"""Inspect the stored skin and triangle geometry in a single-scene, untextured character GLB."""

import argparse
import json
import math

from .lab_artifact import (MAX_SAMPLES, check_scene_references, geometry, inspect_profile,
                           objects, read_chunks, read_layout, reference, require)

PROFILE = 'skinned-character-glb-v1'
BUDGET = {'file_bytes': 4 * 1024 * 1024, 'triangles': 20_000, 'primitives': 64,
          'materials': 16, 'max_joints_per_skin': 128, 'max_influences': 4}
WEIGHT_TOLERANCE = 0.0001
NOTE = ('Counts skin joint entries per skin and weighted vertices per mesh primitive before instancing. '
        'Checks stored weights, joint palettes, inverse-bind matrices, node hierarchy and triangle geometry. '
        'Animation curves, deformation quality and engine import require separate review.')


def check_transform(node):
    require('matrix' not in node or not any(k in node for k in ('translation', 'rotation', 'scale')),
            'Node matrix conflicts with TRS')
    for key, size in (('matrix', 16), ('translation', 3), ('rotation', 4), ('scale', 3)):
        if key in node:
            values = node[key]
            require(isinstance(values, list) and len(values) == size and
                    all(type(v) in (int, float) and math.isfinite(v) for v in values),
                    f'Invalid node {key}')
    if 'matrix' in node:
        require(node['matrix'][3::4] == [0, 0, 0, 1], 'Invalid affine node matrix')
    if 'rotation' in node:
        require(abs(math.hypot(*node['rotation']) - 1) <= WEIGHT_TOLERANCE, 'Invalid node quaternion')


def scene_intervals(doc, nodes, mesh_count):
    # The common graph checker validates references, cycles and unique parentage.
    graph_nodes = [{k: v for k, v in node.items() if k != 'skin'} for node in nodes]
    check_scene_references(dict(doc, nodes=graph_nodes), mesh_count)
    scenes = objects(doc, 'scenes', required=True)
    require(len(scenes) == 1, 'Rig profile requires one scene')
    # Entry/exit intervals permit constant-time ancestor tests even for deep joint trees.
    root_of, entry, end = {}, {}, {}
    for root in scenes[0].get('nodes', []):
        pending = [(root, False)]
        while pending:
            index, leaving = pending.pop()
            if leaving:
                end[index] = len(entry)
                continue
            entry[index] = len(entry)
            root_of[index] = root
            pending.append((index, True))
            pending.extend((child, False) for child in nodes[index].get('children', []))
    require(len(entry) == len(nodes), 'Rig profile requires all nodes in the scene')
    return root_of, entry, end


def invertible_affine(row):
    if not all(map(math.isfinite, row)) or row[3::4] != (0, 0, 0, 1):
        return False
    # Float32 denominators are powers of two. Scaling each column to integers
    # preserves matrix rank and avoids rounding away a small nonzero determinant.
    linear = []
    for offset in (0, 4, 8):
        ratios = [value.as_integer_ratio() for value in row[offset:offset + 3]]
        scale = max(denominator for _, denominator in ratios)
        linear.extend(numerator * (scale // denominator) for numerator, denominator in ratios)
    a, b, c, d, e, f, g, h, i = linear
    return a * (e * i - f * h) - d * (b * i - c * h) + g * (b * f - c * e) != 0


def skin_sizes(doc, nodes, skins, mesh_count, accessors, binary):
    root_of, entry, end = scene_intervals(doc, nodes, mesh_count)
    seen_matrices = set()
    samples = 0
    sizes = []
    for skin in skins:
        joints = skin.get('joints')
        require(isinstance(joints, list) and joints, 'Skin requires a nonempty joints array')
        for joint in joints:
            reference(joint, nodes, 'skin joint')
        require(len(set(joints)) == len(joints) and all(root_of[j] == root_of[joints[0]] for j in joints),
                'Skin joints must be distinct nodes in a common tree')
        if 'skeleton' in skin:
            skeleton = skin['skeleton']
            reference(skeleton, nodes, 'skeleton')
            require(all(entry[skeleton] <= entry[j] < end[skeleton] for j in joints),
                    'Skeleton must be an ancestor of every joint')
        matrix_id = skin.get('inverseBindMatrices')
        matrix = reference(matrix_id, accessors, 'inverseBindMatrices')
        require(matrix.kind == 'MAT4' and matrix.component == 5126 and matrix.count == len(joints)
                and 'byteStride' not in matrix.view and 'target' not in matrix.view,
                'Expected one packed float inverse-bind MAT4 per joint')
        if matrix_id not in seen_matrices:
            samples += matrix.count
            require(samples <= MAX_SAMPLES, 'Rig sample limit exceeded')
            require(all(invertible_affine(row) for row in matrix.values(binary)),
                    'Expected finite, invertible affine inverse-bind matrices')
            seen_matrices.add(matrix_id)
        sizes.append(len(joints))
    return sizes, samples


def mesh_palettes(nodes, meshes, skins, sizes):
    palettes = [None] * len(meshes)
    bound_skins = set()
    for node in nodes:
        require('camera' not in node, 'Camera nodes are outside the character rig profile')
        check_transform(node)
        require(('mesh' in node) == ('skin' in node), 'Every mesh node must bind a skin')
        if 'skin' in node:
            skin_id = node['skin']
            reference(skin_id, skins, 'node skin')
            bound_skins.add(skin_id)
            mesh_id = node['mesh']  # validated by check_scene_references
            current = palettes[mesh_id]
            palettes[mesh_id] = sizes[skin_id] if current is None else min(current, sizes[skin_id])
    require(all(size is not None for size in palettes) and len(bound_skins) == len(skins),
            'Rig profile requires every mesh and skin to be bound')
    return palettes


def weight_summary(joints, weights, binary):
    for attr in (joints, weights):
        require(attr.kind == 'VEC4' and attr.start % 4 == attr.stride % 4 == 0
                and attr.declaration.get('byteOffset', 0) % 4 == 0
                and attr.view.get('target', 34962) == 34962, 'Invalid skin attribute layout')
    require(joints.component in (5121, 5123) and not joints.declaration.get('normalized'),
            'JOINTS_0 requires unsigned byte or unsigned short indices')
    if weights.component == 5126:
        expected, tolerance = 1, WEIGHT_TOLERANCE
    else:
        require(weights.component in (5121, 5123) and weights.declaration.get('normalized'),
                'WEIGHTS_0 requires floats or normalized unsigned integers')
        expected, tolerance = (255 if weights.component == 5121 else 65535), 0
    max_joint = max_influences = 0
    for ids, values in zip(joints.values(binary), weights.values(binary)):
        require(all(math.isfinite(w) and 0 <= w <= expected for w in values)
                and abs(sum(values) - expected) <= tolerance, 'Invalid skin weights or sum')
        active = [joint for joint, value in zip(ids, values) if value]
        require(len(set(active)) == len(active), 'Duplicate nonzero skin influence')
        max_joint = max(max_joint, *ids)
        max_influences = max(max_influences, len(active))
    return max_joint, max_influences


def skinned_geometry(doc, meshes, palettes, accessors, binary, material_count, samples):
    summaries = {}
    max_influences = 0
    geometry_meshes = []
    for mesh, palette_size in zip(meshes, palettes):
        geometry_primitives = []
        for primitive in objects(mesh, 'primitives', required=True):
            attrs = primitive.get('attributes')
            require(isinstance(attrs, dict), 'Primitive requires vertex attributes')
            position = reference(attrs.get('POSITION'), accessors, 'POSITION')
            joint_id, weight_id = attrs.get('JOINTS_0'), attrs.get('WEIGHTS_0')
            joints = reference(joint_id, accessors, 'JOINTS_0')
            weights = reference(weight_id, accessors, 'WEIGHTS_0')
            require(joints.count == weights.count == position.count, 'Skin and geometry vertex counts differ')
            pair = (joint_id, weight_id)
            if pair not in summaries:
                samples += 2 * joints.count
                require(samples <= MAX_SAMPLES, 'Rig sample limit exceeded')
                summaries[pair] = weight_summary(joints, weights, binary)
            max_joint, influences = summaries[pair]
            require(max_joint < palette_size, 'Joint index outside a bound skin palette')
            max_influences = max(max_influences, influences)
            # Delegate every remaining primitive attribute and index to the static geometry checker.
            remaining = {k: v for k, v in attrs.items() if k not in ('JOINTS_0', 'WEIGHTS_0')}
            geometry_primitives.append(dict(primitive, attributes=remaining))
        geometry_meshes.append(dict(mesh, primitives=geometry_primitives))
    counts = geometry(dict(doc, meshes=geometry_meshes), binary, accessors, material_count)
    return dict(counts, weighted_vertices=counts['vertices'], max_influences=max_influences)


def measure(raw):
    doc, binary = read_chunks(raw)
    require(not any(key in doc for key in ('images', 'textures', 'samplers', 'cameras')),
            'Rig profile requires untextured character geometry')
    materials = objects(doc, 'materials')
    for material in materials:
        pbr = material.get('pbrMetallicRoughness', {})
        require(isinstance(pbr, dict) and not any(k in pbr for k in ('baseColorTexture', 'metallicRoughnessTexture'))
                and not any(k in material for k in ('normalTexture', 'emissiveTexture', 'occlusionTexture')),
                'Rig profile requires untextured materials')
    nodes = objects(doc, 'nodes', required=True)
    meshes = objects(doc, 'meshes', required=True)
    skins = objects(doc, 'skins', required=True)
    accessors, length = read_layout(doc, binary, allow_mat4=True)
    sizes, samples = skin_sizes(doc, nodes, skins, len(meshes), accessors, binary)
    palettes = mesh_palettes(nodes, meshes, skins, sizes)
    counts = skinned_geometry(doc, meshes, palettes, accessors, binary, len(materials), samples)
    return dict(counts, skins=len(skins), joints=sum(sizes), max_joints_per_skin=max(sizes),
                materials=len(materials), file_bytes=len(raw), buffer_bytes=length)


def inspect_rig(path):
    return inspect_profile(path, PROFILE, measure, BUDGET, NOTE)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', metavar='PATH', help='a self-contained skinned character GLB')
    report = inspect_rig(parser.parse_args(argv).path)
    print(json.dumps(report, indent=2, allow_nan=False))
    return {'pass': 0, 'fail': 1, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
