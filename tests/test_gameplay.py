import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'gameplay/demo_spec.json'
TACTICAL_SPEC_PATH = ROOT / 'gameplay/tactical_spec.json'
WORLD = ROOT / 'world/demo/training_yard'
SPEC = json.loads(SPEC_PATH.read_text())
LEVEL = json.loads((WORLD / 'level.json').read_text())

class GameplaySpecTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'gameplay/build.py'
        self.assertTrue(path.exists(), 'Gameplay builder missing')
        loader = importlib.util.spec_from_file_location('gameplay_builder', path)
        self.builder = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(self.builder)

    def test_valid_legacy_configuration(self):
        self.assertEqual(self.builder.validate(SPEC, LEVEL), SPEC)

    def test_tactical_settings_are_independent_and_preserved(self):
        for settings in (
            {'tactical': True},
            {'tactical': False, 'destructible_blocks': ['qa_wall']},
            {'tactical': True, 'destructible_blocks': []},
            {'destructible_blocks': ['cover_ne', 'qa_wall']},
        ):
            with self.subTest(settings=settings):
                spec = {**SPEC, **settings}
                self.assertEqual(self.builder.validate(spec, LEVEL), spec)

    def test_tactical_requires_boolean(self):
        for value in (1, 'true', None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'tactical'):
                self.builder.validate({**SPEC, 'tactical': value}, LEVEL)

    def test_destructible_selection_requires_unique_world_block_ids(self):
        for value in ('qa_wall', ['qa_wall', 'qa_wall'], ['crate_a'], ['missing'], [[]]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.builder.validate({**SPEC, 'destructible_blocks': value}, LEVEL)

    def test_invalid_duplicate_enemy(self):
        bad = {**SPEC, 'enemies': [SPEC['enemies'][0]] * 2}
        with self.assertRaises(ValueError):
            self.builder.validate(bad, LEVEL)

    def test_invalid_patrol_inside_cover(self):
        bad = {**SPEC, 'enemies': [{**SPEC['enemies'][0], 'patrol': [[0,0,4]]}]}
        with self.assertRaises(ValueError):
            self.builder.validate(bad, LEVEL)

    def test_reject_point_outside_flat_zone(self):
        bad = {**SPEC, 'enemies': [{**SPEC['enemies'][0], 'position': [12,0,0]}]}
        with self.assertRaises(ValueError):
            self.builder.validate(bad, LEVEL)

    def test_seeded_encounters_replay_and_vary(self):
        a = self.builder.generate(LEVEL, 237, 3)
        self.assertEqual(a, self.builder.generate(LEVEL, 237, 3))
        self.assertNotEqual(a['enemies'], self.builder.generate(LEVEL, 238, 3)['enemies'])
        self.assertEqual(len(a['enemies']), 3)
        self.assertEqual(a, self.builder.validate(a, LEVEL))

    def test_generated_encounter_rejects_tactical_qa_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = subprocess.run(
                [sys.executable, str(ROOT / 'gameplay/build.py'), '--world', str(WORLD),
                 '--output', str(Path(directory) / 'build'), '--generate', '237', '--tactical-qa'],
                capture_output=True, text=True, check=False, timeout=10,
            )
        self.assertEqual(proc.returncode, 2)
        self.assertIn('--tactical-qa requires a gameplay spec', proc.stderr)

    def _build_with_tactical_output(self, destination, output):
        def invoke(args, log, timeout):
            if args[-2:] == ['--script', 'res://tactical_qa.gd']:
                log.write_text(output, encoding='utf-8')
            elif args[-2:] == ['--quit-after', '10']:
                log.write_text('STUDIO_GAMEPLAY_READY\n', encoding='utf-8')
            else:
                log.touch()

        with (patch.object(self.builder.factory, 'invoke', side_effect=invoke),
              redirect_stdout(StringIO()), redirect_stderr(StringIO())):
            self.builder.build(TACTICAL_SPEC_PATH, WORLD, destination, 'godot', False, tactical_qa=True)

    def test_tactical_qa_is_in_report_and_verified_package(self):
        report = {'pass': True, 'checks': [{'name': 'fixture check', 'status': 'passed'}], 'metrics': {}}
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'build'
            self._build_with_tactical_output(destination, f'STUDIO_TACTICAL_QA_JSON {json.dumps(report)}\n')
            self.assertEqual(self.builder.factory.verify_package(destination), [])
            self.assertEqual(json.loads((destination / 'reports/tactical-qa.json').read_text()), report)
            self.assertEqual(json.loads((destination / 'manifest.json').read_text())['tactical_qa'], report)

    def test_tactical_qa_requires_a_single_passing_object(self):
        for output in (
            '{"pass":false}\n',
            '{"pass":1}\n',
            '[]\n',
            '{"pass":true}\nSTUDIO_TACTICAL_QA_JSON {"pass":true}\n',
        ):
            with self.subTest(output=output), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / 'build'
                with self.assertRaisesRegex(ValueError, 'Tactical QA'):
                    self._build_with_tactical_output(destination, f'STUDIO_TACTICAL_QA_JSON {output}')
                self.assertFalse(destination.exists())
