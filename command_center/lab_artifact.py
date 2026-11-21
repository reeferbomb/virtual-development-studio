"""Inspect a local GLB against the Academy's static prop practice budget.

Supports uncompressed glTF 2.0 triangle lists, one embedded buffer, packed or
interleaved vertex data, and untextured materials. Counts mesh definitions once
before scene instancing. Reports do not evaluate appearance or engine behavior.
"""

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
import stat
import struct

from .training_lab import reject_duplicate_keys


MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_JSON_BYTES = 512 * 1024
MAX_SAMPLES = 1_000_000
BUDGET = {'file_bytes': 1024 * 1024, 'triangles': 10_000, 'primitives': 64, 'materials': 8}
PROFILE = 'static-prop-glb-v1'
COMPONENTS = {5120: 'b', 5121: 'B', 5122: 'h', 5123: 'H', 5125: 'I', 5126: 'f'}
SHAPES = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def uint(value, field, minimum=0):
    require(type(value) is int and minimum <= value <= 0xffffffff,
            f'{field} must be an unsigned integer of at least {minimum}')
    return value


def reference(index, rows, field):
    require(uint(index, field) < len(rows), f'{field} reference out of range')
    return rows[index]


def objects(doc, key, required=False):
    rows = doc.get(key, [])
    require(isinstance(rows, list) and (rows or not required) and all(isinstance(r, dict) for r in rows),
            f'{key} must be an array of objects' + (' with at least one entry' if required else ''))
    return rows


def profile_object(pairs):
    obj = reject_duplicate_keys(pairs)
    for field in ('uri', 'extensions', 'extensionsUsed', 'extensionsRequired'):
        require(field not in obj, f'{field} is outside the self-contained core GLB profile')
    return obj


def finite_json(number):
    value = float(number)
    require(math.isfinite(value), 'Nonfinite JSON number')
    return value


def read_chunks(raw):
    require(len(raw) >= 28 and struct.unpack_from('<4sII', raw) == (b'glTF', 2, len(raw)),
            'Invalid GLB 2 header or file length')
    offset = 12
    chunks = []
    for expected in (b'JSON', b'BIN\0'):
        require(offset + 8 <= len(raw), 'Missing GLB chunk header')
        size, kind = struct.unpack_from('<I4s', raw, offset)
        offset += 8
        require(kind == expected and size > 0 and size % 4 == 0 and offset + size <= len(raw),
                'Expected aligned JSON and BIN chunks within the file')
        if kind == b'JSON':
            require(size <= MAX_JSON_BYTES, 'GLB JSON exceeds the parser limit')
        chunks.append(memoryview(raw)[offset:offset + size])
        offset += size
    require(offset == len(raw), 'Unexpected trailing GLB chunk or data')
    doc = json.loads(chunks[0].tobytes().decode('utf-8'), object_pairs_hook=profile_object,
                     parse_float=finite_json, parse_constant=finite_json)
    require(isinstance(doc, dict) and isinstance(doc.get('asset'), dict) and
            doc['asset'].get('version') == '2.0' and doc['asset'].get('minVersion', '2.0') == '2.0',
            'Expected a glTF 2.0 asset')
    return doc, chunks[1]


@dataclass(frozen=True)
class Accessor:
    declaration: dict
    component: int
    kind: str
    count: int
    start: int
    stride: int
    packed: struct.Struct
    view: dict

    def values(self, binary):
        if self.stride == self.packed.size:
            return self.packed.iter_unpack(binary[self.start:self.start + self.count * self.stride])
        return (self.packed.unpack_from(binary, self.start + i * self.stride) for i in range(self.count))


def read_layout(doc, binary, *, allow_mat4=False):
    buffers = objects(doc, 'buffers', required=True)
    require(len(buffers) == 1, 'Expected one embedded buffer')
    length = uint(buffers[0].get('byteLength'), 'buffer byteLength', 1)
    require(0 <= len(binary) - length <= 3 and not any(binary[length:]), 'Invalid BIN length or padding')
    views = objects(doc, 'bufferViews', required=True)
    for view in views:
        require(uint(view.get('buffer'), 'buffer') == 0, 'Buffer view must reference the embedded buffer')
        start = uint(view.get('byteOffset', 0), 'bufferView byteOffset')
        size = uint(view.get('byteLength'), 'bufferView byteLength', 1)
        require(start + size <= length, 'Buffer view exceeds the declared buffer length')
        if 'byteStride' in view:
            stride = uint(view['byteStride'], 'byteStride', 4)
            require(stride % 4 == 0 and stride <= 252, 'Invalid byteStride')
        if 'target' in view:
            require(uint(view['target'], 'bufferView target') in (34962, 34963), 'Invalid buffer view target')

    accessors = []
    for row in objects(doc, 'accessors', required=True):
        require('sparse' not in row, 'Sparse accessors are outside the static prop profile')
        view = reference(row.get('bufferView'), views, 'accessor bufferView')
        component = uint(row.get('componentType'), 'componentType')
        kind = row.get('type')
        require(component in COMPONENTS and isinstance(kind, str), 'Unsupported accessor layout')
        components = 16 if allow_mat4 and kind == 'MAT4' and component == 5126 else SHAPES.get(kind)
        require(components is not None, 'Unsupported accessor layout')
        normalized = row.get('normalized', False)
        require(type(normalized) is bool and (not normalized or component in (5120, 5121, 5122, 5123)),
                'Invalid accessor normalization')
        packed = struct.Struct('<' + COMPONENTS[component] * components)
        alignment = packed.size // components
        count = uint(row.get('count'), 'accessor count', 1)
        offset = uint(row.get('byteOffset', 0), 'accessor byteOffset')
        start = view.get('byteOffset', 0) + offset
        stride = view.get('byteStride', packed.size)
        require(offset % alignment == start % alignment == 0 and stride >= packed.size and
                offset + (count - 1) * stride + packed.size <= view['byteLength'],
                'Misaligned accessor or accessor exceeds its buffer view')
        accessors.append(Accessor(row, component, kind, count, start, stride, packed, view))
    return accessors, length


def inspect_float_attribute(accessor, binary):
    # A VEC3 accessor can be reused as POSITION by a later primitive.
    if accessor.kind != 'VEC3':
        require(all(all(map(math.isfinite, row)) for row in accessor.values(binary)),
                'Nonfinite float vertex attribute')
        return None
    low = [math.inf] * 3
    high = [-math.inf] * 3
    for point in accessor.values(binary):
        require(all(map(math.isfinite, point)), 'Nonfinite float vertex attribute')
        for axis, value in enumerate(point):
            low[axis] = min(low[axis], value)
            high[axis] = max(high[axis], value)
    return low, high


def check_position_bounds(accessor, bounds):
    for key, measured in zip(('min', 'max'), bounds):
        values = accessor.declaration.get(key)
        require(isinstance(values, list) and len(values) == 3 and all(type(v) in (int, float) for v in values),
                f'Expected three POSITION {key} values')
        # glTF JSON extrema use the same float32 precision as the binary POSITION data.
        declared = struct.unpack('<3f', struct.pack('<3f', *values))
        require(declared == tuple(measured),
                f'POSITION {key} disagrees with the stored vertex data')


def check_attribute(name, accessor):
    require(accessor.start % 4 == 0 and accessor.stride % 4 == 0 and
            accessor.declaration.get('byteOffset', 0) % 4 == 0 and accessor.view.get('target', 34962) == 34962,
            'Vertex attribute alignment or buffer view target mismatch')
    if name in ('POSITION', 'NORMAL', 'TANGENT'):
        require(accessor.component == 5126 and accessor.kind == ('VEC4' if name == 'TANGENT' else 'VEC3'),
                f'Invalid {name} accessor')
    else:
        base, _, suffix = name.rpartition('_')
        require(base in ('TEXCOORD', 'COLOR') and suffix.isascii() and suffix.isdecimal(),
                'Unsupported vertex attribute')
        shapes = ('VEC2',) if base == 'TEXCOORD' else ('VEC3', 'VEC4')
        require(accessor.kind in shapes and (accessor.component == 5126 or
                (accessor.component in (5121, 5123) and accessor.declaration.get('normalized'))),
                'Invalid color or texture coordinate accessor')


def geometry(doc, binary, accessors, material_count):
    meshes = objects(doc, 'meshes', required=True)
    counts = {'meshes': len(meshes), 'primitives': 0, 'vertices': 0, 'triangles': 0}
    float_bounds, index_maxima = {}, {}
    remaining = MAX_SAMPLES
    for mesh in meshes:
        require('weights' not in mesh, 'Morph targets are outside the static prop profile')
        for prim in objects(mesh, 'primitives', required=True):
            require(uint(prim.get('mode', 4), 'primitive mode') == 4 and 'targets' not in prim,
                    'Expected static triangle-list primitives')
            if 'material' in prim:
                require(uint(prim['material'], 'material') < material_count, 'Missing primitive material')
            attrs = prim.get('attributes')
            require(isinstance(attrs, dict) and 'POSITION' in attrs, 'Missing POSITION attribute')
            position_id = attrs['POSITION']
            position = reference(position_id, accessors, 'POSITION')
            for name, index in attrs.items():
                attribute = reference(index, accessors, 'attribute')
                check_attribute(name, attribute)
                require(position.count == attribute.count, 'Vertex attribute counts differ')
                if attribute.component == 5126 and index not in float_bounds:
                    remaining -= attribute.count
                    require(remaining >= 0, 'Vertex/index sample limit exceeded')
                    float_bounds[index] = inspect_float_attribute(attribute, binary)
            check_position_bounds(position, float_bounds[position_id])
            elements = position.count
            if 'indices' in prim:
                index_id = prim['indices']
                indices = reference(index_id, accessors, 'indices')
                require(indices.kind == 'SCALAR' and indices.component in (5121, 5123, 5125) and
                        not indices.declaration.get('normalized') and 'byteStride' not in indices.view and
                        indices.view.get('target', 34963) == 34963, 'Invalid index accessor')
                if index_id not in index_maxima:
                    remaining -= indices.count
                    require(remaining >= 0, 'Vertex/index sample limit exceeded')
                    index_maxima[index_id] = max(i for i, in indices.values(binary))
                require(index_maxima[index_id] < min(position.count, 2 ** (8 * indices.packed.size) - 1),
                        'Index out of range or primitive restart index')
                elements = indices.count
            require(elements % 3 == 0, 'Triangle-list element count must be a multiple of three')
            counts['primitives'] += 1
            counts['vertices'] += position.count
            counts['triangles'] += elements // 3
    return counts


def check_scene_references(doc, mesh_count):
    nodes = objects(doc, 'nodes')
    children = set()
    for node in nodes:
        require('skin' not in node and 'weights' not in node, 'Expected static prop nodes')
        if 'mesh' in node:
            require(uint(node['mesh'], 'node mesh') < mesh_count, 'Node mesh reference out of range')
        edges = node.get('children', [])
        require(isinstance(edges, list), 'Node children must be an array')
        for child in edges:
            reference(child, nodes, 'child node')
            require(child not in children, 'Repeated child node or multiple parents')
            children.add(child)

    roots = set(range(len(nodes))) - children
    pending = list(roots)
    visited = 0
    while pending:
        node = nodes[pending.pop()]
        visited += 1
        pending.extend(node.get('children', []))
    require(visited == len(nodes), 'Cycle in scene node hierarchy')

    scenes = objects(doc, 'scenes')
    if 'scene' in doc:
        reference(doc['scene'], scenes, 'default scene')
    for scene in scenes:
        indices = scene.get('nodes', [])
        require(isinstance(indices, list), 'Scene nodes must be an array')
        seen = set()
        for index in indices:
            reference(index, nodes, 'scene node')
            require(index in roots and index not in seen, 'Invalid or repeated scene root')
            seen.add(index)


def measure(raw):
    doc, binary = read_chunks(raw)
    unsupported = ('images', 'textures', 'samplers', 'animations', 'skins')
    require(not any(key in doc for key in unsupported), 'Profile requires static geometry and untextured materials')
    materials = objects(doc, 'materials')
    for material in materials:
        pbr = material.get('pbrMetallicRoughness', {})
        require(isinstance(pbr, dict) and not any(key in pbr for key in ('baseColorTexture', 'metallicRoughnessTexture'))
                and not any(key in material for key in ('normalTexture', 'emissiveTexture', 'occlusionTexture')),
                'Profile requires untextured materials')
    accessors, length = read_layout(doc, binary)
    counts = geometry(doc, binary, accessors, len(materials))
    check_scene_references(doc, counts['meshes'])
    return dict(counts, materials=len(materials), file_bytes=len(raw), buffer_bytes=length)


def read_glb_bytes(path):
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), 'Expected a regular GLB file')
        require(info.st_size <= MAX_FILE_BYTES, 'GLB exceeds the file inspection limit')
        with os.fdopen(fd, 'rb', closefd=False) as source:
            raw = source.read(MAX_FILE_BYTES + 1)
        require(len(raw) <= MAX_FILE_BYTES, 'GLB exceeds the file inspection limit')
    finally:
        os.close(fd)
    return raw


def inspect_profile(path, profile, measure_fn, budget, note):
    """Read only the chosen regular file and return a digest of the exact inspected bytes."""
    report = {'profile': profile, 'status': 'unavailable', 'sha256': None,
              'measurements': {}, 'checks': []}
    try:
        raw = read_glb_bytes(path)
        report['sha256'] = hashlib.sha256(raw).hexdigest()
        measurements = measure_fn(raw)
    except (OSError, ValueError, OverflowError, struct.error, RecursionError) as exc:
        report['note'] = str(exc)
        return report
    checks = [{'id': name, 'measured': measurements[name], 'limit': limit,
               'status': 'pass' if measurements[name] <= limit else 'fail'}
              for name, limit in budget.items()]
    report.update(status='pass' if all(c['status'] == 'pass' for c in checks) else 'fail',
                  checks=checks, measurements=measurements, note=note)
    return report


def inspect_glb(path):
    return inspect_profile(path, PROFILE, measure, BUDGET,
                           'Counts triangle lists and position entries per mesh primitive before node instancing. '
                           'Measures stored bytes and declared material count. Visual quality, scene behavior and '
                           'engine performance require separate review.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', metavar='PATH', help='a self-contained static prop GLB')
    report = inspect_glb(parser.parse_args(argv).path)
    print(json.dumps(report, indent=2, allow_nan=False))
    return {'pass': 0, 'fail': 1, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
