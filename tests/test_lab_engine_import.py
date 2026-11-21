import hashlib
import importlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from command_center.lab_artifact import read_chunks


ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / 'demo/first-batch/assets/supply_crate.glb'
MANNEQUIN = ROOT / 'demo/first-batch/assets/training_mannequin.glb'
MODULE = 'command_center.lab_engine_import'


def with_glb_json(mutate, source=CRATE):
    doc, binary = read_chunks(source.read_bytes())
    mutate(doc)
    json_bytes = json.dumps(doc, separators=(',', ':')).encode()
    json_bytes += b' ' * (-len(json_bytes) % 4)
    chunks = struct.pack('<I4s', len(json_bytes), b'JSON') + json_bytes
    chunks += struct.pack('<I4s', len(binary), b'BIN\0') + binary.tobytes()
    return struct.pack('<4sII', b'glTF', 2, len(chunks) + 12) + chunks


class EngineImportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), 'The offline engine import probe is missing')
        self.probe = importlib.import_module(MODULE)

    def test_malformed_or_unsupported_glb_never_starts_a_child(self):
        cases = (
            CRATE.read_bytes()[:-1],
            with_glb_json(lambda doc: doc['buffers'][0].update(uri='../outside.bin')),
            with_glb_json(lambda doc: doc.update(extensionsUsed=['KHR_materials_unlit'])),
            with_glb_json(lambda doc: doc.update(images=[{'uri': 'https://invalid.example/a.png'}])),
            with_glb_json(lambda doc: doc['nodes'][0].update(translation=[0, 'unknown', 0])),
            with_glb_json(lambda doc: doc['materials'][0].update(alphaMode='UNKNOWN')),
        )
        with tempfile.TemporaryDirectory() as directory, patch.object(
                self.probe, '_probe_scene', side_effect=AssertionError('preflight must run first')):
            path = Path(directory) / 'input.glb'
            for raw in cases:
                with self.subTest(raw_size=len(raw)):
                    path.write_bytes(raw)
                    report = self.probe.inspect_engine_import(path)
                    self.assertEqual(report['status'], 'unavailable', report)
                    self.assertEqual(report['sha256'], hashlib.sha256(raw).hexdigest())

    def test_over_budget_source_never_starts_a_child(self):
        raw = with_glb_json(lambda doc: doc.update(materials=[{}] * 9))
        with tempfile.TemporaryDirectory() as directory, patch.object(
                self.probe, '_probe_scene', side_effect=AssertionError('source budget must gate execution')):
            path = Path(directory) / 'input.glb'
            path.write_bytes(raw)
            report = self.probe.inspect_engine_import(path)
        self.assertEqual(report['status'], 'fail', report)
        self.assertIn((9, 8, 'fail'), [(c['measured'], c['limit'], c['status']) for c in report['checks']])

    def test_unskinned_animation_cannot_bypass_geometry_preflight(self):
        raw = with_glb_json(lambda doc: doc.pop('skins'), MANNEQUIN)
        with tempfile.TemporaryDirectory() as directory, patch.object(
                self.probe, '_probe_scene', side_effect=AssertionError('animation-only GLB reached engine execution')):
            path = Path(directory) / 'input.glb'
            path.write_bytes(raw)
            report = self.probe.inspect_engine_import(path)
        self.assertEqual(report['status'], 'unavailable', report)
        self.assertEqual(report['sha256'], hashlib.sha256(raw).hexdigest())

    def test_node_and_mesh_instance_limits_gate_engine_execution(self):
        for nodes, limit in (([{}] * 4097, 4096), ([{'mesh': 0}] * 1025, 1024)):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as directory, patch.object(
                    self.probe, '_probe_scene', side_effect=AssertionError('scene limits must gate execution')):
                path = Path(directory) / 'input.glb'
                path.write_bytes(with_glb_json(lambda doc: doc.update(nodes=nodes)))
                report = self.probe.inspect_engine_import(path)
                self.assertEqual(report['status'], 'fail', report)
                self.assertIn((limit + 1, limit, 'fail'),
                              [(c['measured'], c['limit'], c['status']) for c in report['checks']])

    def test_post_preflight_workspace_error_preserves_unique_checks(self):
        with patch.object(self.probe, '_probe_scene', side_effect=OSError('workspace unavailable')):
            report = self.probe.inspect_engine_import(CRATE)
        self.assertEqual(report['status'], 'unavailable', report)
        ids = [check['id'] for check in report['checks']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('temporary_workspace', ids)

    def test_unavailable_offline_environment_keeps_verified_source_digest(self):
        with patch.object(self.probe, '_offline_prefix', return_value=None), patch.object(
                self.probe.subprocess, 'Popen', side_effect=AssertionError('there must be no networked fallback')):
            report = self.probe.inspect_engine_import(CRATE)
        self.assertEqual(report['status'], 'unavailable', report)
        self.assertEqual(report['sha256'], '5c18d05fc15645860b9dedd1b43002af39882fcebb678af5d68d12adad7533f1')
        self.assertIn('offline_environment', [c['id'] for c in report['checks'] if c['status'] == 'unavailable'])

    def test_missing_engine_keeps_verified_source_digest(self):
        with patch.object(self.probe, '_offline_prefix', return_value=['/usr/bin/unshare']), patch.object(
                self.probe, '_installed_godot', return_value=None), patch.object(
                self.probe.subprocess, 'Popen', side_effect=AssertionError('no engine is installed')):
            report = self.probe.inspect_engine_import(CRATE)
        self.assertEqual(report['status'], 'unavailable', report)
        self.assertIsNotNone(report['sha256'])
        self.assertIn('godot_version', [c['id'] for c in report['checks'] if c['status'] == 'unavailable'])

    def test_nonzero_exit_or_unverified_scene_marker_never_passes(self):
        raw = CRATE.read_bytes()
        exact_hash = hashlib.sha256(raw).hexdigest()
        inventory = {'sha256': exact_hash, 'mesh_instances': 18, 'skeletons': 0, 'bones': 0,
                     'animation_players': 0, 'animations': 0}
        for scenario in ('editor_exit', 'scene_exit', 'no_marker', 'wrong_hash', 'duplicate_marker', 'boolean_count'):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                input_path = Path(directory) / 'source.glb'
                input_path.write_bytes(raw)

                def simulate_engine(command, project, env, **_limits):
                    self.assertEqual((project / 'source_asset.glb').read_bytes(), raw)
                    self.assertEqual(project.parent.parent, Path(directory))
                    self.assertNotEqual(env['HOME'], os.environ.get('HOME'))
                    if '--version' in command:
                        output, code = b'4.7.2.stable.official.ed1daf0bf\n', 0
                    elif '--import' in command:
                        (project / 'source_asset.glb.import').write_text('[remap]\n', encoding='utf-8')
                        output, code = b'editor import', int(scenario == 'editor_exit')
                    else:
                        self.assertNotEqual(scenario, 'editor_exit', 'a failed import must not load the scene')
                        observed = dict(inventory)
                        if scenario == 'wrong_hash':
                            observed['sha256'] = '0' * 64
                        elif scenario == 'boolean_count':
                            observed['mesh_instances'] = True
                        prefix = 'GRAVEFORGE_IMPORT_' + command[-1] + ' '
                        output = (prefix + json.dumps(observed) + '\n').encode()
                        if scenario == 'duplicate_marker':
                            output *= 2
                        elif scenario == 'no_marker':
                            output = b'scene output without a marker'
                        code = int(scenario == 'scene_exit')
                    return subprocess.CompletedProcess(command, code, stdout=output)

                with patch.object(tempfile, 'tempdir', directory), patch.object(
                        self.probe, '_offline_prefix', return_value=['/usr/bin/unshare']), patch.object(
                        self.probe, '_installed_godot', return_value='/usr/bin/godot4'), patch.object(
                        self.probe, '_run_bounded', side_effect=simulate_engine):
                    report = self.probe.inspect_engine_import(input_path)
                self.assertEqual(report['status'], 'fail', report)
                self.assertNotIn('mesh_instances', report['measurements'])
                self.assertEqual(list(Path(directory).iterdir()), [input_path])

    @unittest.skipUnless(sys.platform == 'linux', 'The offline runner uses Linux process groups')
    def test_child_timeout_and_output_limit_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            for source, timeout, expected in (
                    ('import time; time.sleep(30)', 0.1, 'timed out'),
                    ('import os; os.write(1, b"x" * 10000)', 5, 'output limit')):
                with self.subTest(expected=expected), self.assertRaisesRegex(RuntimeError, expected):
                    self.probe._run_bounded([sys.executable, '-I', '-c', source], Path(directory),
                                            {}, timeout=timeout, max_output=128)

    def require_local_engine(self, report):
        if report['status'] == 'unavailable' and any(
                check['status'] == 'unavailable' and check['id'] in ('offline_environment', 'godot_version')
                for check in report['checks']):
            self.skipTest(report['note'])

    def test_real_crate_cli_import_observes_instantiated_meshes(self):
        result = subprocess.run([sys.executable, '-m', MODULE, str(CRATE)], cwd=ROOT,
                                capture_output=True, text=True, timeout=60)
        self.assertIn(result.returncode, (0, 2), result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.require_local_engine(report)
        self.assertEqual(result.returncode, 0, report)
        self.assertEqual(report['status'], 'pass', report)
        self.assertEqual(report['sha256'], '5c18d05fc15645860b9dedd1b43002af39882fcebb678af5d68d12adad7533f1')
        self.assertEqual({key: report['measurements'][key] for key in ('mesh_instances', 'skeletons', 'animations')},
                         {'mesh_instances': 18, 'skeletons': 0, 'animations': 0})

    def test_real_mannequin_import_observes_skeleton_and_clip(self):
        report = self.probe.inspect_engine_import(MANNEQUIN)
        self.require_local_engine(report)
        self.assertEqual(report['status'], 'pass', report)
        self.assertGreaterEqual(report['measurements']['mesh_instances'], 1)
        self.assertEqual(report['measurements']['skeletons'], 1)
        self.assertEqual(report['measurements']['bones'], 16)
        self.assertEqual(report['measurements']['animations'], 1)


if __name__ == '__main__':
    unittest.main()
