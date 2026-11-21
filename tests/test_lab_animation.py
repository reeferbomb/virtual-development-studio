import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from command_center import lab_animation


ROOT = Path(__file__).resolve().parents[1]
MANNEQUIN = ROOT / 'demo/first-batch/assets/training_mannequin.glb'
ACTOR = ROOT / 'cinematic/demo/nightfall_patrol/assets/animated_actor.glb'
COURIER = ROOT / 'vertical/demo/character/courier.glb'


def make_clip(path='translation', interpolation='LINEAR', times=(0.0, 1.0), values=None):
    width = 4 if path == 'rotation' else 3
    if values is None:
        value = (0, 0, 0, 1) if width == 4 else (0, 0, 0)
        values = [value] * len(times)
    input_bytes = struct.pack('<' + 'f' * len(times), *times)
    output_bytes = b''.join(struct.pack('<' + 'f' * width, *value) for value in values)
    binary = input_bytes + output_bytes
    return {
        'asset': {'version': '2.0'}, 'nodes': [{}], 'buffers': [{'byteLength': len(binary)}],
        'bufferViews': [{'buffer': 0, 'byteLength': len(input_bytes)},
                        {'buffer': 0, 'byteOffset': len(input_bytes), 'byteLength': len(output_bytes)}],
        'accessors': [{'bufferView': 0, 'count': len(times), 'componentType': 5126, 'type': 'SCALAR',
                       'min': [min(times)], 'max': [max(times)]},
                      {'bufferView': 1, 'count': len(values), 'componentType': 5126, 'type': f'VEC{width}'}],
        'animations': [{'name': 'Pose', 'channels': [{'sampler': 0, 'target': {'node': 0, 'path': path}}],
                        'samplers': [{'input': 0, 'output': 1, 'interpolation': interpolation}]}],
    }, binary


def pack(doc, binary):
    header = json.dumps(doc, allow_nan=False).encode()
    chunks = b''
    for key, data, padding in [(b'JSON', header, b' '), (b'BIN\0', binary, b'\0')]:
        data += padding * (-len(data) % 4)
        chunks += struct.pack('<I4s', len(data), key) + data
    return struct.pack('<4sII', b'glTF', 2, len(chunks) + 12) + chunks


class AnimationLabTests(unittest.TestCase):
    def inspect(self, doc, binary, expected):
        raw = pack(doc, binary)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'animation.glb'
            path.write_bytes(raw)
            report = lab_animation.inspect_animation(path)
            self.assertEqual(report['status'], expected, report)
            self.assertEqual(report['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(list(path.parent.iterdir()), [path])
        if expected == 'unavailable':
            self.assertEqual((report['measurements'], report['checks']), ({}, []))
        return report

    def test_target_sampler_and_accessor_references_and_layout(self):
        changes = [
            (('nodes',), []), (('animations',), []), (('animations', 0, 'channels'), []),
            (('animations', 0, 'channels', 0, 'target'), None),
            (('animations', 0, 'channels', 0, 'target', 'path'), 'weights'),
            (('animations', 0, 'channels', 0, 'target', 'path'), []),
            (('animations', 0, 'channels', 0, 'target', 'node'), False),
            (('animations', 0, 'channels', 0, 'target', 'node'), 5),
            (('nodes', 0, 'matrix'), [0] * 16), (('nodes', 0, 'scale'), [0, 1]),
            (('animations', 0, 'channels', 0, 'sampler'), -1),
            (('animations', 0, 'samplers', 0, 'input'), '0'),
            (('animations', 0, 'samplers', 0, 'output'), 2),
            (('animations', 0, 'samplers', 0, 'interpolation'), 'CATMULLROMSPLINE'),
            (('animations', 0, 'samplers', 0, 'interpolation'), {}),
            (('accessors', 0, 'componentType'), 5125), (('accessors', 1, 'type'), 'VEC2'),
            (('accessors', 1, 'componentType'), 5122), (('accessors', 1, 'count'), 1),
            (('accessors', 0, 'min'), [-1]), (('accessors', 0, 'max'), [True]),
            (('bufferViews', 0, 'target'), 34962), (('bufferViews', 1, 'byteStride'), 12),
            (('buffers', 0, 'uri'), '../asset.bin'),
        ]
        for keys, value in changes:
            with self.subTest(keys=keys, value=value):
                doc, binary = make_clip()
                row = doc
                for key in keys[:-1]:
                    row = row[key]
                row[keys[-1]] = value
                self.inspect(doc, binary, 'unavailable')

    def test_broken_timestamps_and_output_bytes(self):
        doc, binary = make_clip()
        for times in [(0, 0), (1, 0), (-1, 1), (0, float('inf')), (float('nan'), 1)]:
            with self.subTest(times=times):
                self.inspect(doc, struct.pack('<ff', *times) + binary[8:], 'unavailable')
        for path in ('translation', 'rotation', 'scale'):
            with self.subTest(path=path):
                doc, binary = make_clip(path)
                self.inspect(doc, binary[:-4] + struct.pack('<f', float('nan')), 'unavailable')
        doc, binary = make_clip('rotation', values=[(0, 0, 0, 1), (0, 0, 1, 1)])
        self.inspect(doc, binary, 'unavailable')

    def test_duplicate_targets_and_cached_outputs_still_validate_each_use(self):
        doc, binary = make_clip()
        clip = doc['animations'][0]
        clip['channels'] *= 2
        self.inspect(doc, binary, 'unavailable')
        clip['channels'][1] = {'sampler': 0, 'target': {'node': 0, 'path': 'rotation'}}
        self.inspect(doc, binary, 'unavailable')

    def test_cubic_quaternion_tangents_and_value_slots(self):
        tangent, identity = (0, 0, 0, 0), (0, 0, 0, 1)
        values = [tangent, identity, tangent] * 2
        doc, binary = make_clip('rotation', 'CUBICSPLINE', values=values)
        self.inspect(doc, binary, 'pass')
        # A second sampler reads the same VEC4 rows as ordinary rotation keys.
        # It must validate all values, including the prior cubic tangent slots.
        other = copy.deepcopy(doc['animations'][0])
        input_time = struct.pack('<6f', *range(6))
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(input_time)})
        doc['accessors'].append({'bufferView': 2, 'componentType': 5126, 'count': 6,
                                 'type': 'SCALAR', 'min': [0], 'max': [5]})
        doc['buffers'][0]['byteLength'] += len(input_time)
        other['samplers'][0].update(input=2, interpolation='STEP')
        doc['animations'].append(other)
        self.inspect(doc, binary + input_time, 'unavailable')

        for bad_values in (values[:-1], [tangent, tangent, tangent] * 2,
                           [(float('inf'), 0, 0, 0), identity, tangent] * 2):
            with self.subTest(values=bad_values):
                self.inspect(*make_clip('rotation', 'CUBICSPLINE', values=bad_values), 'unavailable')
        self.inspect(*make_clip('rotation', 'CUBICSPLINE', times=(0,), values=values[:3]), 'unavailable')

    def test_reused_sampler_accounting_and_default_interpolation(self):
        doc, binary = make_clip(times=(1.5, 4.0))
        clip = doc['animations'][0]
        del clip['samplers'][0]['interpolation']
        clip['channels'].append({'sampler': 0, 'target': {'node': 0, 'path': 'scale'}})
        doc['animations'].append(copy.deepcopy(clip))
        with patch.object(lab_animation, 'MAX_SAMPLES', 4):
            report = self.inspect(doc, binary, 'pass')
        with patch.object(lab_animation, 'MAX_SAMPLES', 3):
            self.inspect(doc, binary, 'unavailable')
        m = report['measurements']
        self.assertEqual((m['clips'], m['channels'], m['samplers'], m['keyframes']), (2, 4, 2, 8))
        self.assertEqual(m['longest_clip_seconds'], 2.5)
        self.assertEqual([(c['start_seconds'], c['end_seconds'], c['duration_seconds'], c['keyframes'])
                          for c in m['clip_details']], [(1.5, 4, 2.5, 4)] * 2)

    def test_real_corpus_exact_measured_channel_keys(self):
        for path, clips, channels, keys in [(MANNEQUIN, 1, 48, 284), (ACTOR, 6, 288, 1722),
                                            (COURIER, 8, 456, 16416)]:
            with self.subTest(path=path):
                report = lab_animation.inspect_animation(path)
                self.assertEqual(report['status'], 'pass', report)
                self.assertEqual(report['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
                measured = report['measurements']
                self.assertEqual((measured['clips'], measured['channels'], measured['keyframes']),
                                 (clips, channels, keys))
                self.assertEqual(sum(c['keyframes'] for c in measured['clip_details']), keys)
                self.assertAlmostEqual(measured['longest_clip_seconds'], 2.0, places=5)

    def test_missing_links_and_fifo_never_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'link').symlink_to(MANNEQUIN)
            os.mkfifo(root / 'pipe')
            for path in [root / 'missing', root / 'link', root / 'pipe', root]:
                report = lab_animation.inspect_animation(path)
                self.assertEqual((report['status'], report['sha256']), ('unavailable', None))

    def test_budget_failure_is_measured_and_cli_exits_match(self):
        doc, binary = make_clip(times=(0, 301))
        report = self.inspect(doc, binary, 'fail')
        self.assertEqual([c for c in report['checks'] if c['status'] == 'fail'],
                         [{'id': 'longest_clip_seconds', 'measured': 301.0, 'limit': 300, 'status': 'fail'}])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'clip.glb'
            for raw, status, code in [(pack(*make_clip()), 'pass', 0), (pack(doc, binary), 'fail', 1),
                                      (b'broken', 'unavailable', 2)]:
                path.write_bytes(raw)
                result = subprocess.run([sys.executable, '-m', 'command_center.lab_animation', str(path)],
                                        cwd=ROOT, capture_output=True, text=True, timeout=8)
                self.assertEqual((result.returncode, json.loads(result.stdout)['status']), (code, status))


if __name__ == '__main__':
    unittest.main()
