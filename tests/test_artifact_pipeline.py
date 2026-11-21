import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from command_center.artifact_pipeline import inspect_pipeline


ROOT = Path(__file__).resolve().parents[1]


def report(profile, status='pass', digest='a' * 64):
    return {'profile': profile, 'status': status, 'sha256': digest,
            'measurements': {}, 'checks': [], 'note': 'Synthetic component result'}


class ArtifactPipelineTests(unittest.TestCase):
    def test_real_static_props_retain_exact_digest(self):
        path = ROOT / 'demo/first-batch/assets/supply_crate.glb'
        result = inspect_pipeline(path, 'static')
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(result['measurements']['profiles_passed'], 1)
        self.assertEqual(result['reports'][0]['measurements']['triangles'], 792)

    def test_real_character_reports_both_profiles_for_identical_bytes(self):
        path = ROOT / 'vertical/demo/character/courier.glb'
        result = inspect_pipeline(path, 'character')
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(result['measurements']['profiles_passed'], 2)
        self.assertEqual(len(result['reports']), 2)
        self.assertTrue(all(r['sha256'] == result['sha256'] for r in result['reports']))

    def test_character_pipeline_requires_all_reports_for_same_bytes(self):
        with patch('command_center.artifact_pipeline._inspect', side_effect=[
                report('rig'), report('animation', digest='b' * 64)]) as inspect:
            result = inspect_pipeline('model.glb', 'character', engine=True)
        self.assertEqual(inspect.call_count, 2)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['sha256'])

    def test_known_budget_failure_prevents_optional_engine_launch(self):
        with patch('command_center.artifact_pipeline._inspect', return_value=report('static', 'fail')) as inspect:
            result = inspect_pipeline('bad.glb', 'static', engine=True)
        inspect.assert_called_once_with('static', 'bad.glb')
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['checks'][-1]['status'], 'unavailable')

    def test_successful_character_combines_rig_animation_and_explicit_engine(self):
        with patch('command_center.artifact_pipeline._inspect', side_effect=[
                report('rig'), report('animation'), report('engine')]) as inspect:
            result = inspect_pipeline('model.glb', 'character', engine=True)
        self.assertEqual([call.args[0] for call in inspect.call_args_list], ['rig', 'animation', 'engine'])
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['measurements']['profiles_passed'], 3)

    def test_unavailable_component_is_not_a_pass(self):
        with patch('command_center.artifact_pipeline._inspect', side_effect=[
                report('rig'), report('animation', 'unavailable')]):
            result = inspect_pipeline('model.glb', 'character')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['measurements']['profiles_unavailable'], 1)

    def test_texture_cannot_request_godot_import(self):
        with self.assertRaises(ValueError):
            inspect_pipeline('texture.png', 'texture', engine=True)

    def test_cli_status_and_json_for_budget_failure_and_missing_file(self):
        for profile, path, expected, code in (
            ('texture', ROOT / 'demo/asset-preview.png', 'fail', 1),
            ('static', ROOT / 'missing-fixture.glb', 'unavailable', 2),
        ):
            with self.subTest(profile=profile):
                proc = subprocess.run([sys.executable, '-m', 'command_center.artifact_pipeline',
                                       '--profile', profile, str(path)], cwd=ROOT,
                                      check=False, capture_output=True, text=True)
                self.assertEqual(proc.returncode, code, proc.stderr)
                self.assertEqual(json.loads(proc.stdout)['status'], expected)
