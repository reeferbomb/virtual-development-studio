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

from command_center.lab_artifact import inspect_glb


ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / 'demo/first-batch/assets/supply_crate.glb'


def triangle():
    # Interleaved positions plus three packed uint16 indices. Padding is outside the declared buffer.
    positions = b''.join(struct.pack('<3fI', *point, 0) for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0)))
    binary = positions + struct.pack('<3H', 0, 1, 2)
    doc = {
        'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(binary)}],
        'bufferViews': [{'buffer': 0, 'byteLength': 48, 'byteStride': 16},
                        {'buffer': 0, 'byteOffset': 48, 'byteLength': 6}],
        'accessors': [{'bufferView': 0, 'componentType': 5126, 'type': 'VEC3', 'count': 3,
                       'min': [0, 0, 0], 'max': [1, 1, 0]},
                      {'bufferView': 1, 'componentType': 5123, 'type': 'SCALAR', 'count': 3}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]}],
    }
    return doc, binary


def chunk(kind, body):
    return struct.pack('<I4s', len(body), kind) + body


def container(*chunks):
    contents = b''.join(chunks)
    return struct.pack('<4sII', b'glTF', 2, len(contents) + 12) + contents


def pack(doc, binary):
    data = json.dumps(doc, separators=(',', ':')).encode()
    return container(chunk(b'JSON', data + b' ' * (-len(data) % 4)),
                     chunk(b'BIN\0', binary + b'\0' * (-len(binary) % 4)))


class ArtifactLabTests(unittest.TestCase):
    def inspect_bytes(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'prop.glb'
            path.write_bytes(data)
            report = inspect_glb(path)
            self.assertEqual(report['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(list(path.parent.iterdir()), [path])
            return report

    def test_interleaved_indexed_and_nonindexed_primitives(self):
        doc, binary = triangle()
        doc['meshes'][0]['primitives'].append({'attributes': {'POSITION': 0}})
        report = self.inspect_bytes(pack(doc, binary))
        self.assertEqual(report['status'], 'pass', report)
        measured = report['measurements']
        self.assertEqual((measured['meshes'], measured['primitives'], measured['triangles'],
                          measured['vertices'], measured['buffer_bytes']), (1, 2, 2, 6, 54))
        self.assertTrue(all(c['measured'] <= c['limit'] for c in report['checks']))

    def test_real_crate_and_independent_cli_output(self):
        report = inspect_glb(CRATE)
        self.assertEqual(report['status'], 'pass', report)
        self.assertEqual(report['sha256'], '5c18d05fc15645860b9dedd1b43002af39882fcebb678af5d68d12adad7533f1')
        self.assertEqual({key: report['measurements'][key] for key in
                          ('meshes', 'primitives', 'triangles', 'vertices', 'materials', 'file_bytes')},
                         {'meshes': 18, 'primitives': 18, 'triangles': 792, 'vertices': 1728,
                          'materials': 3, 'file_bytes': 70108})
        result = subprocess.run([sys.executable, '-m', 'command_center.lab_artifact', str(CRATE)],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), report)

    def test_budget_failure_retains_exact_measurement(self):
        doc, binary = triangle()
        doc['materials'] = [{} for _ in range(9)]
        report = self.inspect_bytes(pack(doc, binary))
        self.assertEqual(report['status'], 'fail', report)
        self.assertEqual([(c['id'], c['measured'], c['limit']) for c in report['checks'] if c['status'] == 'fail'],
                         [('materials', 9, 8)])

    def test_rejects_truncated_misaligned_reversed_and_repeated_chunks(self):
        doc, binary = triangle()
        good = pack(doc, binary)
        json_size, = struct.unpack_from('<I', good, 12)
        head, tail = good[12:20 + json_size], good[20 + json_size:]
        bad = [b'', good[:-1], b'xxxx' + good[4:], container(tail, head),
               container(head, head, tail), container(head, tail, b'xx'),
               container(chunk(b'JSON', b'{} '), tail), container(head, chunk(b'BIN\0', b'\0' * 60)),
               container(chunk(b'JSON', b'{"q":1,"q":2}   '), tail)]
        for data in bad:
            with self.subTest(data=data[:20]):
                self.assertEqual(self.inspect_bytes(data)['status'], 'unavailable')

    def test_external_resources_and_unsupported_features_are_never_followed(self):
        for key, value in [('buffers', [{'byteLength': 54, 'uri': '../outside.bin'}]),
                           ('images', [{'uri': 'https://invalid.example/art.png'}]),
                           ('images', [{'uri': 'data:image/png;base64,AA=='}]),
                           ('extensionsRequired', ['KHR_draco_mesh_compression']),
                           ('animations', [{}])]:
            with self.subTest(key=key):
                doc, binary = triangle()
                doc[key] = value
                self.assertEqual(self.inspect_bytes(pack(doc, binary))['status'], 'unavailable')

    def test_binary_data_and_reference_validation(self):
        changes = [
            ('bufferViews', 0, 'byteLength', 56), ('bufferViews', 0, 'byteStride', 8),
            ('bufferViews', 1, 'buffer', False), ('accessors', 0, 'bufferView', -1),
            ('accessors', 0, 'count', True), ('accessors', 0, 'byteOffset', 2),
            ('accessors', 0, 'count', 100000000), ('accessors', 0, 'sparse', {}),
            ('accessors', 0, 'max', [2, 1, 0]), ('accessors', 0, 'type', []),
        ]
        for field, index, name, value in changes:
            with self.subTest(field=field, name=name, value=value):
                doc, binary = triangle()
                doc[field][index][name] = value
                self.assertEqual(self.inspect_bytes(pack(doc, binary))['status'], 'unavailable')
        doc, binary = triangle()
        for broken in (binary[:-2] + b'\x03\0', struct.pack('<f', float('nan')) + binary[4:]):
            self.assertEqual(self.inspect_bytes(pack(doc, broken))['status'], 'unavailable')
        for name, value in [('indices', -1), ('attributes', {'POSITION': 0, 'NORMAL': 1}), ('material', 0),
                            ('mode', 1), ('targets', [{}])]:
            with self.subTest(name=name):
                doc, binary = triangle()
                doc['meshes'][0]['primitives'][0][name] = value
                self.assertEqual(self.inspect_bytes(pack(doc, binary))['status'], 'unavailable')

    def test_finite_values_required_for_referenced_float_attributes(self):
        for name, width in [('NORMAL', 3), ('TANGENT', 4), ('TEXCOORD_0', 2), ('COLOR_0', 4)]:
            with self.subTest(attribute=name):
                doc, binary = triangle()
                offset = (len(binary) + 3) & ~3
                values = struct.pack('<' + 'f' * width, *([0.0] * width)) * 3
                binary += bytes(offset - len(binary)) + values
                doc['buffers'][0]['byteLength'] = len(binary)
                doc['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(values)})
                doc['accessors'].append({'bufferView': 2, 'componentType': 5126, 'type': f'VEC{width}', 'count': 3})
                doc['meshes'][0]['primitives'][0]['attributes'][name] = 2
                doc['meshes'][0]['primitives'] *= 2
                with patch('command_center.lab_artifact.MAX_SAMPLES', 9):
                    self.assertEqual(self.inspect_bytes(pack(doc, binary))['status'], 'pass')
                with patch('command_center.lab_artifact.MAX_SAMPLES', 8):
                    self.assertEqual(self.inspect_bytes(pack(doc, binary))['status'], 'unavailable')
                for invalid in (float('nan'), float('inf'), -float('inf')):
                    bad = binary[:-4] + struct.pack('<f', invalid)
                    self.assertEqual(self.inspect_bytes(pack(doc, bad))['status'], 'unavailable')

    def test_scene_references_and_node_tree(self):
        doc, binary = triangle()
        doc.update(nodes=[{'children': [1]}, {'mesh': 0}], scenes=[{'nodes': [0]}], scene=0)
        self.assertEqual(self.inspect_bytes(pack(doc, binary))['status'], 'pass')
        for field, value in [('scene', 1), ('nodes', [{'mesh': True}]), ('scenes', [{'nodes': [2]}]),
                             ('nodes', [{'children': [1]}, {'children': [0]}]),
                             ('nodes', [{'children': [1, 1]}, {}]), ('scenes', [{'nodes': [1]}]),
                             ('nodes', [{'mesh': 0, 'skin': 0}])]:
            with self.subTest(field=field, value=value):
                invalid = dict(doc, **{field: value})
                self.assertEqual(self.inspect_bytes(pack(invalid, binary))['status'], 'unavailable')

    def test_parser_limits_and_cached_accessor_sampling(self):
        doc, binary = triangle()
        doc['meshes'][0]['primitives'] *= 3
        raw = pack(doc, binary)
        with patch('command_center.lab_artifact.MAX_SAMPLES', 6):
            self.assertEqual(self.inspect_bytes(raw)['status'], 'pass')
        with patch('command_center.lab_artifact.MAX_SAMPLES', 5):
            self.assertEqual(self.inspect_bytes(raw)['status'], 'unavailable')
        with patch('command_center.lab_artifact.MAX_JSON_BYTES', 64):
            self.assertEqual(self.inspect_bytes(raw)['status'], 'unavailable')
        with patch('command_center.lab_artifact.MAX_FILE_BYTES', 64):
            report = inspect_glb(CRATE)
            self.assertEqual((report['status'], report['sha256']), ('unavailable', None))

    def test_cli_reports_distinct_budget_failure_and_invalid_input(self):
        doc, binary = triangle()
        doc['materials'] = [{}] * 9
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.glb'
            for data, status, code in [(pack(doc, binary), 'fail', 1), (b'broken', 'unavailable', 2)]:
                path.write_bytes(data)
                result = subprocess.run([sys.executable, '-m', 'command_center.lab_artifact', str(path)],
                                        cwd=ROOT, capture_output=True, text=True)
                self.assertEqual((result.returncode, json.loads(result.stdout)['status']), (code, status))

    def test_directory_selection_closes_opened_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            fd = os.open(directory, os.O_RDONLY)
            try:
                with patch('command_center.lab_artifact.os.open', return_value=fd):
                    self.assertEqual(inspect_glb(directory)['status'], 'unavailable')
                with self.assertRaises(OSError):
                    os.fstat(fd)
            finally:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def test_missing_symlink_and_fifo_do_not_open_a_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'link.glb').symlink_to(CRATE)
            os.mkfifo(root / 'pipe.glb')
            for path in (root / 'missing.glb', root / 'link.glb', root / 'pipe.glb'):
                with self.subTest(path=path):
                    report = inspect_glb(path)
                    self.assertEqual((report['status'], report['sha256']), ('unavailable', None))


if __name__ == '__main__':
    unittest.main()
