import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from command_center import lab_artifact

ROOT = Path(__file__).resolve().parents[1]
MANNEQUIN = ROOT / 'demo/first-batch/assets/training_mannequin.glb'
ACTOR = ROOT / 'cinematic/demo/nightfall_patrol/assets/animated_actor.glb'
COURIER = ROOT / 'vertical/demo/character/courier.glb'


class RigLabTests(unittest.TestCase):
    def test_only_rig_enabled_loader_accepts_float_mat4(self):
        doc, binary = lab_artifact.read_chunks(MANNEQUIN.read_bytes())
        with self.assertRaises(ValueError):
            lab_artifact.read_layout(doc, binary)
        accessors, _ = lab_artifact.read_layout(doc, binary, allow_mat4=True)
        matrix_id = doc['skins'][0]['inverseBindMatrices']
        self.assertEqual(accessors[matrix_id].packed.size, 64)
        doc['accessors'][matrix_id]['componentType'] = 5123
        with self.assertRaises(ValueError):
            lab_artifact.read_layout(doc, binary, allow_mat4=True)

    def test_shared_inspection_uses_profile_budgets_and_digest(self):
        report = lab_artifact.inspect_profile(
            MANNEQUIN, 'test', lambda raw: {'bytes': len(raw)}, {'bytes': 0}, 'byte count')
        self.assertEqual(report['sha256'], hashlib.sha256(MANNEQUIN.read_bytes()).hexdigest())
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['checks'], [
            {'id': 'bytes', 'limit': 0, 'measured': MANNEQUIN.stat().st_size, 'status': 'fail'}])

    def test_cli_reads_real_character_exports(self):
        for path, expected in [(MANNEQUIN, (16, 5712, 3096, 1)),
                               (ACTOR, (16, 5712, 3096, 1)), (COURIER, (19, 5208, 2856, 2))]:
            with self.subTest(asset=path.name):
                result = subprocess.run([sys.executable, '-m', 'command_center.lab_rig', str(path)],
                                        cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual(report['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(report['status'], 'pass')
                self.assertEqual(report['profile'], 'skinned-character-glb-v1')
                measured = report['measurements']
                self.assertEqual(tuple(measured[k] for k in
                                       ('joints', 'weighted_vertices', 'triangles', 'max_influences')), expected)

    def inspect_mutation(self, edit):
        from command_center.lab_rig import inspect_rig
        doc, raw = lab_artifact.read_chunks(MANNEQUIN.read_bytes())
        binary = bytearray(raw)
        edit(doc, binary)
        encoded = json.dumps(doc, separators=(',', ':')).encode()
        encoded += b' ' * (-len(encoded) % 4)
        data = (struct.pack('<4sIIII', b'glTF', 2, 28 + len(encoded) + len(binary),
                            len(encoded), 0x4e4f534a) + encoded +
                struct.pack('<I4s', len(binary), b'BIN\0') + binary)
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'rig.glb'
            dest.write_bytes(data)
            report = inspect_rig(dest)
            self.assertEqual(dest.read_bytes(), data)
            self.assertEqual(report['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(list(dest.parent.iterdir()), [dest])
            return report

    def test_budget_failure_still_has_measurements(self):
        report = self.inspect_mutation(lambda d, b: d['materials'].extend([{}] * 15))
        self.assertEqual(report['status'], 'fail', report)
        self.assertEqual([c for c in report['checks'] if c['status'] == 'fail'],
                         [{'id': 'materials', 'measured': 17, 'limit': 16, 'status': 'fail'}])

    def test_weight_and_joint_encodings(self):
        def integer_weights(doc, binary):
            attrs = doc['meshes'][0]['primitives'][0]['attributes']
            row = doc['accessors'][attrs['WEIGHTS_0']]
            view = doc['bufferViews'][row['bufferView']]
            offset = view['byteOffset']
            weights = list(struct.iter_unpack('<4f', binary[offset:offset + view['byteLength']]))
            for i, w in enumerate(weights):
                struct.pack_into('<4H', binary, offset + 8 * i, *(int(v * 65535) for v in w))
            row.update(componentType=5123, normalized=True)
            view['byteLength'] = 8 * len(weights)
        self.assertEqual(self.inspect_mutation(integer_weights)['status'], 'pass')

    def test_invalid_binary_rows_rejected_even_at_last_vertex(self):
        def replace_row(accessor, fmt, value):
            def edit(doc, binary):
                row = doc['accessors'][accessor]
                start = doc['bufferViews'][row['bufferView']]['byteOffset']
                struct.pack_into(fmt, binary, start + (row['count'] - 1) * struct.calcsize(fmt), *value)
            return edit
        mutations = [('joint palette', replace_row(2, '<4B', (1, 0, 0, 16))),
                     ('negative', replace_row(3, '<4f', (1., -.2, .2, 0.))),
                     ('sum', replace_row(3, '<4f', (.25, .25, .25, 0.))),
                     ('nonfinite weight', replace_row(3, '<4f', (float('nan'), 0., 0., 0.))),
                     ('invalid triangle', replace_row(4, '<H', (65535,))),
                     ('nonfinite matrix', replace_row(10, '<16f', (float('nan'),) * 16)),
                     ('projective matrix', replace_row(10, '<16f', (0.,) * 16)),
                     ('singular affine matrix', replace_row(10, '<16f',
                         (1., 2., 3., 0., 4., 5., 6., 0., 1., 2., 3., 0., 7., 8., 9., 1.))),
                     ('nonfinite geometry', replace_row(0, '<3f', (0., 0., float('inf'))))]
        for case, edit in mutations:
            with self.subTest(case=case):
                self.assertEqual(self.inspect_mutation(edit)['status'], 'unavailable')

    def test_binding_declarations_and_forest(self):
        cases = [
            ('missing skin', lambda d, b: d['nodes'][16].pop('skin')),
            ('nonexistent skin', lambda d, b: d['nodes'][16].update(skin=1)),
            ('missing mesh', lambda d, b: d['nodes'][16].pop('mesh')),
            ('unreferenced skin', lambda d, b: d['skins'].append(d['skins'][0].copy())),
            ('dangling camera', lambda d, b: d['nodes'][0].update(camera=0)),
            ('cyclic', lambda d, b: d['nodes'][0].update(children=[17])),
            ('multiple parents', lambda d, b: d['nodes'][16].update(children=[0])),
            ('disconnected skeleton', lambda d, b: d['nodes'][17].update(children=[16])),
            ('wrong skeleton root', lambda d, b: d['skins'][0].update(skeleton=16)),
            ('out of range joint', lambda d, b: d['skins'][0]['joints'].__setitem__(0, 99)),
            ('duplicate joint', lambda d, b: d['skins'][0]['joints'].__setitem__(1, 15)),
            ('wrong matrix count', lambda d, b: d['accessors'][10].update(count=15)),
            ('absent matrix', lambda d, b: d['skins'][0].pop('inverseBindMatrices')),
            ('invalid node transform', lambda d, b: d['nodes'][0].update(translation=[True, 0, 0])),
            ('weights missing', lambda d, b: d['meshes'][0]['primitives'][0]['attributes'].pop('WEIGHTS_0')),
            ('extra palette', lambda d, b: d['meshes'][0]['primitives'][0]['attributes'].update(JOINTS_1=2)),
            ('counts differ', lambda d, b: d['accessors'][2].update(count=1)),
            ('wrong joint type', lambda d, b: d['accessors'][2].update(normalized=True)),
            ('extension', lambda d, b: d.update(extensionsUsed=['TEST_extension'])),
            ('sparse', lambda d, b: d['accessors'][2].update(sparse={})),
        ]
        for name, edit in cases:
            with self.subTest(case=name):
                self.assertEqual(self.inspect_mutation(edit)['status'], 'unavailable')

    def test_read_and_sample_bounds(self):
        from command_center.lab_rig import inspect_rig
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'linked.glb'
            path.symlink_to(MANNEQUIN)
            self.assertEqual(inspect_rig(path)['status'], 'unavailable')
            self.assertEqual(inspect_rig(directory)['status'], 'unavailable')
        with patch('command_center.lab_rig.MAX_SAMPLES', 10):
            self.assertEqual(inspect_rig(MANNEQUIN)['status'], 'unavailable')

    def test_shared_reader_returns_bytes_and_rejects_symlinks(self):
        self.assertEqual(lab_artifact.read_glb_bytes(COURIER), COURIER.read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / 'model.glb'
            link.symlink_to(COURIER)
            with self.assertRaises(OSError):
                lab_artifact.read_glb_bytes(link)
