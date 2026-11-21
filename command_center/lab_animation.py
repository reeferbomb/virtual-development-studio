"""Inspect animation tracks in a self-contained GLB 2.0 without running an engine.

The profile supports dense FLOAT translation, rotation and scale channels on
nodes using TRS, including STEP, LINEAR and CUBICSPLINE interpolation.
"""

import argparse
import json
import math
import struct

from .lab_artifact import MAX_FILE_BYTES, inspect_profile, objects, read_chunks, read_layout, reference, require


PROFILE = 'animation-glb-v1'
BUDGET = {'file_bytes': 2 * 1024 * 1024, 'clips': 32, 'channels': 1024,
          'keyframes': 100_000, 'longest_clip_seconds': 300}
MAX_SAMPLES = 1_000_000
QUATERNION_TOLERANCE = 0.0005
NOTE = ('Counts keys per channel, including channels sharing a sampler. Durations measure the span '
        'between the earliest and latest stored keys in each clip. This profile checks FLOAT '
        'translation, rotation and scale tracks. Motion quality, skin deformation, loop continuity '
        'and runtime playback require separate review.')


def unit_quaternion(value):
    return abs(math.hypot(*value) - 1.0) <= QUATERNION_TOLERANCE


def check_time_bound(accessor, field, measured):
    declared = accessor.declaration.get(field)
    require(isinstance(declared, list) and len(declared) == 1 and type(declared[0]) in (int, float),
            f'Expected a scalar animation input {field}')
    # Blender, for example, writes the JSON number at double precision.
    (rounded,) = struct.unpack('<f', struct.pack('<f', declared[0]))
    require(rounded == measured, f'Animation input {field} disagrees with the stored key times')


class AnimationAccessors:
    """Bound binary scans across clips, even when many samplers alias an accessor."""

    def __init__(self, accessors, binary):
        self.accessors = accessors
        self.binary = binary
        self.remaining = MAX_SAMPLES
        self.times = {}
        self.outputs = set()

    def reserve(self, count):
        self.remaining -= count
        require(self.remaining >= 0, 'Animation sample inspection limit exceeded')

    def key_time_range(self, index):
        accessor = reference(index, self.accessors, 'animation input accessor')
        if index not in self.times:
            require(accessor.component == 5126 and accessor.kind == 'SCALAR',
                    'Animation key times require a FLOAT SCALAR accessor')
            require('byteStride' not in accessor.view and 'target' not in accessor.view,
                    'Animation input must use a tightly packed animation buffer view')
            self.reserve(accessor.count)
            first = None
            previous = -1.0
            for (time,) in accessor.values(self.binary):
                require(math.isfinite(time) and time >= 0 and time > previous,
                        'Animation key times must be finite, nonnegative and strictly increasing')
                if first is None:
                    first = time
                previous = time
            check_time_bound(accessor, 'min', first)
            check_time_bound(accessor, 'max', previous)
            self.times[index] = (accessor.count, first, previous)
        return self.times[index]

    def output_kind(self, index, keys, cubic):
        accessor = reference(index, self.accessors, 'animation output accessor')
        require(accessor.component == 5126 and accessor.kind in ('VEC3', 'VEC4'),
                'Animation outputs require FLOAT VEC3 or VEC4 values')
        require('byteStride' not in accessor.view and 'target' not in accessor.view,
                'Animation output must use a tightly packed animation buffer view')
        require(accessor.count == keys * (3 if cubic else 1),
                'Animation output count disagrees with key times and interpolation')
        rotation = accessor.kind == 'VEC4'
        cache_key = (index, rotation and cubic)
        if cache_key not in self.outputs:
            self.reserve(accessor.count)
            for i, value in enumerate(accessor.values(self.binary)):
                require(all(map(math.isfinite, value)), 'Nonfinite animation output value or tangent')
                if rotation and (not cubic or i % 3 == 1):
                    require(unit_quaternion(value), 'Rotation keys must contain unit quaternions')
            self.outputs.add(cache_key)
        return accessor.kind

    def sampler(self, row):
        interpolation = row.get('interpolation', 'LINEAR')
        require(interpolation in ('LINEAR', 'STEP', 'CUBICSPLINE'), 'Unsupported animation interpolation')
        keys, start, end = self.key_time_range(row.get('input'))
        cubic = interpolation == 'CUBICSPLINE'
        require(not cubic or keys >= 2, 'CUBICSPLINE needs at least two keys')
        kind = self.output_kind(row.get('output'), keys, cubic)
        return keys, start, end, kind


def check_target_node(node):
    require('matrix' not in node, 'An animated node must use TRS transforms')
    for field, width in [('translation', 3), ('rotation', 4), ('scale', 3)]:
        if field in node:
            value = node[field]
            require(isinstance(value, list) and len(value) == width and
                    all(type(x) in (int, float) and math.isfinite(x) for x in value),
                    f'Invalid animated node {field} transform')
            if field == 'rotation':
                require(unit_quaternion(value), 'Animated node rest rotation must be a unit quaternion')


def measure_clip(clip, reader, nodes, checked_nodes):
    if 'name' in clip:
        require(isinstance(clip['name'], str), 'Animation name must be a string')
    samplers = [reader.sampler(row) for row in objects(clip, 'samplers', required=True)]
    channels = objects(clip, 'channels', required=True)
    targets = set()
    keyframes = 0
    start, end = math.inf, 0.0
    for channel in channels:
        keys, first, last, kind = reference(channel.get('sampler'), samplers, 'animation channel sampler')
        target = channel.get('target')
        require(isinstance(target, dict), 'Animation channel target must be an object')
        node_id = target.get('node')
        node = reference(node_id, nodes, 'animation target node')
        path = target.get('path')
        require(path in ('translation', 'scale', 'rotation'), 'Only node TRS channels are supported')
        require(kind == ('VEC4' if path == 'rotation' else 'VEC3'), 'Output shape disagrees with target path')
        require((node_id, path) not in targets, 'Repeated animation target node and path in a clip')
        targets.add((node_id, path))
        if node_id not in checked_nodes:
            check_target_node(node)
            checked_nodes.add(node_id)
        keyframes += keys
        start = min(start, first)
        end = max(end, last)
    return {'name': clip.get('name'), 'channels': len(channels), 'samplers': len(samplers),
            'keyframes': keyframes, 'start_seconds': start, 'end_seconds': end,
            'duration_seconds': end - start}


def measure(raw):
    require(len(raw) <= MAX_FILE_BYTES, 'GLB exceeds the file inspection limit')
    doc, binary = read_chunks(raw)
    accessors, length = read_layout(doc, binary, allow_mat4=True)
    reader = AnimationAccessors(accessors, binary)
    nodes = objects(doc, 'nodes', required=True)
    checked_nodes = set()
    details = [measure_clip(clip, reader, nodes, checked_nodes) for clip in objects(doc, 'animations', required=True)]
    return {'file_bytes': len(raw), 'buffer_bytes': length, 'clips': len(details),
            'channels': sum(c['channels'] for c in details), 'samplers': sum(c['samplers'] for c in details),
            'keyframes': sum(c['keyframes'] for c in details),
            'longest_clip_seconds': max(c['duration_seconds'] for c in details), 'clip_details': details}


def inspect_animation(path):
    return inspect_profile(path, PROFILE, measure, BUDGET, NOTE)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', metavar='PATH', help='a self-contained animated GLB')
    report = inspect_animation(parser.parse_args(argv).path)
    print(json.dumps(report, indent=2, allow_nan=False))
    return {'pass': 0, 'fail': 1, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
