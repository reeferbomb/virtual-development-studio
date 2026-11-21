"""Exercise the real v32 generated project on an available local Godot installation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from command_center.lab_engine_import import _installed_godot, _offline_prefix, _sandbox_env


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'cinematic/production/examples'


class CinematicProductionIntegrationTests(unittest.TestCase):
    def require_engine(self):
        engine, offline = _installed_godot(), _offline_prefix()
        if not engine or not offline:
            self.skipTest('Local Godot and offline process prerequisites are required')
        probe = subprocess.run(offline + ['true'], capture_output=True, timeout=10)
        if probe.returncode != 0:
            self.skipTest('Local network isolation is unavailable')
        return engine, offline

    def run_example(self, output, plan):
        result = subprocess.run([
            sys.executable, '-m', 'cinematic.production.runner',
            str(plan), str(EXAMPLES / 'nightfall_bindings.json'),
            '--output', str(output), '--engine',
        ], cwd=ROOT, capture_output=True, text=True, timeout=180)
        if result.returncode:
            logs = '\n'.join((output / 'reports' / name).read_text(errors='replace')[-4096:]
                             for name in ('version.log', 'import.log', 'qa.log')
                             if (output / 'reports' / name).is_file())
            self.fail(result.stdout + result.stderr + '\n' + logs)
        report = json.loads(result.stdout)
        self.assertEqual(report, json.loads((output / 'reports/report.json').read_text()))
        self.assertEqual(report['status'], 'passed')
        qa = report['runtime']['qa']
        self.assertIs(qa['pass'], True)
        self.assertGreaterEqual(len(qa['checks']), 14)
        self.assertTrue(all(row['status'] == 'passed' for row in qa['checks']))
        self.assertEqual(qa['production_sha256'], hashlib.sha256((output / 'production.json').read_bytes()).hexdigest())
        return report

    def test_export_import_runtime_and_caption_layout(self):
        engine, offline = self.require_engine()
        with tempfile.TemporaryDirectory(prefix='graveforge-production-integration-') as directory:
            output = Path(directory) / 'project'
            report = self.run_example(output, EXAMPLES / 'nightfall_plan.json')
            for record in report['files']:
                path = output / record['path']
                self.assertTrue(path.resolve().is_relative_to(output.resolve()))
                data = path.read_bytes()
                self.assertEqual(record['bytes'], len(data))
                self.assertEqual(record['sha256'], hashlib.sha256(data).hexdigest())
            isolated = Path(directory) / 'caption-env'
            isolated.mkdir()
            overlay = subprocess.run(offline + [engine, '--headless', '--path', str(output),
                '--script', str(ROOT / 'cinematic/production/tests/caption_overlay_qa.gd')],
                cwd=output, env=_sandbox_env(isolated), capture_output=True, text=True, timeout=30)
            self.assertEqual(overlay.returncode, 0, overlay.stdout + overlay.stderr)
            self.assertIn('CAPTION_LAYOUT_QA passed', overlay.stdout)
            self.assertNotIn('ERROR:', overlay.stdout + overlay.stderr)

    def test_sparse_and_adjacent_cues_in_reordered_lanes(self):
        self.require_engine()
        plan = json.loads((EXAMPLES / 'nightfall_plan.json').read_text())
        plan.update(fps=24, frame_count=4, duration_ms=167, shots=[
            {'camera': 'street_pair', 'start_frame': 0, 'end_frame': 2},
            {'camera': 'ivo_single', 'start_frame': 2, 'end_frame': 4},
        ], blocking=[
            {'actor': 'ivo', 'clip': 'idle', 'start_frame': 2, 'end_frame': 3},
            {'actor': 'ivo', 'clip': 'idle', 'start_frame': 1, 'end_frame': 2},
        ], dialogue=[
            {'line': 'second', 'speaker': 'ivo', 'text': 'Wait.', 'start_frame': 2, 'end_frame': 3},
            {'line': 'first', 'speaker': 'ivo', 'text': 'Wait.', 'start_frame': 1, 'end_frame': 2},
        ])
        plan['subtitles'] = [{k: v for k, v in cue.items() if k != 'speaker'}
                             for cue in reversed(plan['dialogue'])]
        with tempfile.TemporaryDirectory(prefix='graveforge-production-edge-') as directory:
            source = Path(directory) / 'plan.json'
            source.write_text(json.dumps(plan))
            self.run_example(Path(directory) / 'project', source)


if __name__ == '__main__':
    unittest.main()
