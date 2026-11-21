"""Verify the same shipped bytes across independent asset-evidence profiles."""

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from command_center.artifact_pipeline import inspect_pipeline
from command_center.lab_animation import inspect_animation
from command_center.lab_rig import inspect_rig
from command_center.lab_texture import inspect_texture


ROOT = Path(__file__).resolve().parents[1]
MANNEQUIN = ROOT / 'demo/first-batch/assets/training_mannequin.glb'
CHARACTERS = (
    (MANNEQUIN, 'b32e7a8aca9b9abc80a7f4690c7e7cf49da446581dcc116c0056f5335f10598b', 16, 1, 48, 284),
    (ROOT / 'cinematic/demo/nightfall_patrol/assets/animated_actor.glb',
     '156b7594b1f3b9aa07ba5344c371cef2c4e2d0406ae603fb39094d51333c3817', 16, 6, 288, 1722),
    (ROOT / 'vertical/demo/character/courier.glb',
     'e9d234e95bf2fd5c0ea1967694182207bb1445ba9cb47128c3eb18dac6561451', 19, 8, 456, 16416),
)


def mannequin_parts():
    data = MANNEQUIN.read_bytes()
    json_bytes, = struct.unpack_from('<I', data, 12)
    doc = json.loads(data[20:20 + json_bytes])
    binary = bytearray(data[28 + json_bytes:])
    return doc, binary


def glb(doc, binary):
    data = json.dumps(doc, separators=(',', ':')).encode()
    data += b' ' * (-len(data) % 4)
    chunks = struct.pack('<I4s', len(data), b'JSON') + data
    chunks += struct.pack('<I4s', len(binary), b'BIN\0') + binary
    return struct.pack('<4sII', b'glTF', 2, 12 + len(chunks)) + chunks


def accessor_start(doc, index):
    accessor = doc['accessors'][index]
    view = doc['bufferViews'][accessor['bufferView']]
    return view.get('byteOffset', 0) + accessor.get('byteOffset', 0)


def png(width=1, height=1, rows=b'\x00\x20\x40\x60\xff'):
    def chunk(kind, contents):
        crc = zlib.crc32(kind + contents)
        return struct.pack('>I', len(contents)) + kind + contents + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


class ArtifactProfileIntegrityTests(unittest.TestCase):
    def inspect_fixture(self, inspectors, name, payload, expected):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / name
            path.write_bytes(payload)
            for inspect in inspectors:
                with self.subTest(inspector=inspect.__name__):
                    report = inspect(path)
                    self.assertEqual(report['status'], expected, report)
                    self.assertEqual(report['sha256'], hashlib.sha256(payload).hexdigest())
                    json.dumps(report, allow_nan=False)
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_distinct_shipped_character_exports(self):
        for path, digest, joints, clips, channels, keys in CHARACTERS:
            with self.subTest(asset=path.name):
                rig, animation = inspect_rig(path), inspect_animation(path)
                for report in (rig, animation):
                    self.assertEqual(report['sha256'], digest)
                    self.assertEqual(report['status'], 'pass', report)
                    self.assertTrue(report['checks'])
                    self.assertTrue(all(check['status'] == 'pass' for check in report['checks']))
                self.assertEqual(rig['measurements']['joints'], joints)
                measured = animation['measurements']
                self.assertEqual((measured['clips'], measured['channels'], measured['keyframes']),
                                 (clips, channels, keys))

    def test_accessor_cannot_extend_into_next_view_despite_remaining_bin_bytes(self):
        from command_center.lab_engine_import import inspect_engine_import
        doc, binary = mannequin_parts()
        matrix = doc['accessors'][doc['skins'][0]['inverseBindMatrices']]
        doc['bufferViews'][matrix['bufferView']]['byteLength'] -= 4
        self.inspect_fixture((inspect_rig, inspect_animation, inspect_engine_import),
                             'model.glb', glb(doc, binary), 'unavailable')

    def test_rig_rejects_an_unresolved_camera_even_without_camera_definitions(self):
        doc, binary = mannequin_parts()
        doc['nodes'][0]['camera'] = 0
        self.inspect_fixture((inspect_rig,), 'model.glb', glb(doc, binary), 'unavailable')

    def test_joint_indices_are_local_to_skin_and_weights_are_read_from_bin(self):
        for name in ('joint', 'weight_sum', 'weight_nan'):
            with self.subTest(case=name):
                doc, binary = mannequin_parts()
                attrs = doc['meshes'][0]['primitives'][0]['attributes']
                if name == 'joint':
                    # Valid node index, just outside this skin's joint palette.
                    offset = accessor_start(doc, attrs['JOINTS_0'])
                    binary[offset] = len(doc['skins'][0]['joints'])
                else:
                    offset = accessor_start(doc, attrs['WEIGHTS_0'])
                    weights = (0.0, 0.0, 0.0, 0.0) if name == 'weight_sum' else (1.0, float('nan'), 0.0, 0.0)
                    struct.pack_into('<4f', binary, offset, *weights)
                self.inspect_fixture((inspect_rig,), 'model.glb', glb(doc, binary), 'unavailable')

    def test_animation_measures_inputs_and_outputs_even_with_plausible_metadata(self):
        for name in ('duplicate_time', 'nonfinite_value', 'out_of_range_target', 'key_count'):
            with self.subTest(case=name):
                doc, binary = mannequin_parts()
                clip = doc['animations'][0]
                sampler = clip['samplers'][0]
                if name == 'duplicate_time':
                    offset = accessor_start(doc, sampler['input'])
                    binary[offset + 4:offset + 8] = binary[offset:offset + 4]
                elif name == 'nonfinite_value':
                    struct.pack_into('<f', binary, accessor_start(doc, sampler['output']), float('nan'))
                elif name == 'out_of_range_target':
                    clip['channels'][0]['target']['node'] = len(doc['nodes'])
                else:
                    doc['accessors'][sampler['output']]['count'] -= 1
                self.inspect_fixture((inspect_animation,), 'model.glb', glb(doc, binary), 'unavailable')

    def test_character_pipeline_stops_before_engine_on_one_broken_component(self):
        for affected_profile in ('rig', 'animation'):
            with self.subTest(component=affected_profile), tempfile.TemporaryDirectory() as temporary:
                doc, binary = mannequin_parts()
                if affected_profile == 'rig':
                    doc['skins'][0]['joints'].pop()
                else:
                    doc['animations'][0]['channels'][0]['target']['node'] = len(doc['nodes'])
                source = glb(doc, binary)
                path = Path(temporary) / 'character.glb'
                path.write_bytes(source)
                with patch('subprocess.Popen', side_effect=AssertionError('unexpected child process')):
                    report = inspect_pipeline(path, 'character', engine=True)
                self.assertEqual(report['status'], 'unavailable', report)
                expected = {name: 'unavailable' if name == affected_profile else 'pass'
                            for name in ('rig', 'animation')}
                expected['engine'] = 'unavailable'
                self.assertEqual({check['id']: check['status'] for check in report['checks']}, expected)
                digest = hashlib.sha256(source).hexdigest()
                self.assertEqual(report['sha256'], digest)
                self.assertEqual([child['sha256'] for child in report['reports']], [digest, digest])

    def test_external_buffer_fails_closed_before_engine_execution(self):
        from command_center.lab_engine_import import inspect_engine_import
        doc, binary = mannequin_parts()
        doc['buffers'][0]['uri'] = 'external.bin'
        with patch('subprocess.Popen', side_effect=AssertionError('unexpected child process')):
            self.inspect_fixture((inspect_rig, inspect_animation, inspect_engine_import),
                                 'model.glb', glb(doc, binary), 'unavailable')

    def test_unskinned_animation_cannot_bypass_mesh_preflight(self):
        from command_center.lab_engine_import import inspect_engine_import
        doc, binary = mannequin_parts()
        del doc['skins'], doc['meshes']
        for node in doc['nodes']:
            node.pop('skin', None)
        # Existing mesh reference is now dangling, while every animation track is valid.
        with patch('command_center.lab_engine_import._probe_scene',
                   side_effect=AssertionError('malformed scene entered the engine probe')):
            self.inspect_fixture((inspect_engine_import,), 'model.glb', glb(doc, binary), 'unavailable')

    def test_texture_decoder_verifies_bytes_and_bounds_before_allocating_pixels(self):
        good = png()
        self.inspect_fixture((inspect_texture,), 'map.png', good, 'pass')
        for case, data in (
            ('bad_crc', good[:-1] + bytes([good[-1] ^ 1])),
            ('invalid_filter', png(rows=b'\x05abcd')),
            ('extra_pixel', png(rows=b'\x00abcdwxyz')),
            ('declared_oversize', png(width=1_000_000, height=1_000_000)),
        ):
            with self.subTest(case=case):
                self.inspect_fixture((inspect_texture,), 'map.png', data, 'unavailable')


if __name__ == '__main__':
    unittest.main()
