import json
import tempfile
import unittest
from pathlib import Path

from living import build as builder


ROOT = Path(__file__).resolve().parents[1]
SPEC = {'seed': 237, 'chunk_size': 32, 'radius': 1, 'capacity': 40}


class LivingBuildTests(unittest.TestCase):
    def test_fixture_and_custom_specifications(self):
        fixture = json.loads((ROOT / 'living/demo_spec.json').read_text())
        self.assertEqual(fixture, SPEC)
        self.assertEqual(builder.validate(fixture), SPEC)
        custom = {'seed': 0, 'chunk_size': 16, 'radius': 2, 'capacity': 3}
        self.assertEqual(builder.validate(custom), custom)

    def test_spec_requires_four_in_range_integer_fields(self):
        invalid = ({}, [], dict(SPEC, extra=1), dict(SPEC, seed=True), dict(SPEC, seed=2**31),
                   dict(SPEC, chunk_size=15), dict(SPEC, chunk_size=65), dict(SPEC, radius=1.0),
                   dict(SPEC, radius=3), dict(SPEC, capacity=2), dict(SPEC, capacity=121))
        for spec in invalid:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                builder.validate(spec)

    def test_qa_rejects_an_edited_fixture_before_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = root / 'spec.json'
            spec.write_text(json.dumps(dict(SPEC, seed=238)))
            with self.assertRaisesRegex(ValueError, 'exact shipped fixture'):
                builder.build(spec, root / 'output', living_qa=True)
            self.assertEqual(list(root.iterdir()), [spec])

    def test_shipped_package_preserves_runtime_and_component_evidence(self):
        package = ROOT / 'living/demo/frontier'
        self.assertEqual(builder.factory.verify_package(package), [])
        self.assertIn('run/main_scene="res://living.tscn"', (package / 'project.godot').read_text())
        self.assertTrue((package / 'unified.tscn').is_file())
        self.assertTrue((package / 'unified_qa.gd').is_file())
        self.assertFalse((package / '.godot').exists())
        manifest = json.loads((package / 'manifest.json').read_text())
        self.assertEqual(manifest['kind'], 'living')
        self.assertEqual(manifest['spec'], SPEC)
        reports = package / 'reports'
        qa = json.loads((reports / 'living-qa.json').read_text())
        self.assertEqual(manifest['living_qa'], qa)
        self.assertIs(qa['pass'], True)
        self.assertTrue(qa['checks'])
        self.assertTrue(all(check['status'] == 'passed' for check in qa['checks']))
        self.assertIn('STUDIO_LIVING_READY', (reports / 'launch.log').read_text())
        for component in ('streaming', 'population', 'inventory', 'factions', 'persistence', 'transport',
                          'range_combat', 'scheduled_population', 'quests', 'economy', 'encounters',
                          'diplomacy', 'contracts', 'character_animator'):
            with self.subTest(component=component):
                self.assertTrue((reports / f'test_{component}.log').is_file())
