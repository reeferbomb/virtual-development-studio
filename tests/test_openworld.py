import json
import tempfile
import unittest
from pathlib import Path
from openworld import build as builder

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / 'openworld/demo_spec.json').read_text())


class OpenWorldFactoryTests(unittest.TestCase):
    def test_default_and_custom_specs(self):
        self.assertEqual(builder.validate(SPEC), SPEC)
        custom = dict(SPEC, seed=0, chunk_size=64, radius=2, capacity=120)
        self.assertEqual(builder.validate(custom), custom)

    def test_invalid_specs(self):
        for key, value in [('seed', True), ('seed', -1), ('seed', 2**31), ('chunk_size', 15), ('chunk_size', 65),
                           ('chunk_size', float('nan')), ('radius', 0), ('radius', 3), ('radius', 1.0), ('capacity', 0), ('capacity', 121)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                builder.validate(dict(SPEC, **{key: value}))
        for bad in ([], {}, dict(SPEC, extra=1)):
            with self.assertRaises(ValueError):
                builder.validate(bad)

    def test_qa_requires_exact_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / 'spec.json'
            spec.write_text(json.dumps(dict(SPEC, seed=238)))
            with self.assertRaisesRegex(ValueError, 'fixture'):
                builder.build(spec, Path(tmp) / 'output', openworld_qa=True)
            self.assertFalse((Path(tmp) / 'output').exists())

    def test_shipped_package_inventory(self):
        package = ROOT / 'openworld/demo/frontier'
        self.assertEqual(builder.factory.verify_package(package), [])
        qa = json.loads((package / 'reports/openworld-qa.json').read_text())
        self.assertIs(qa['pass'], True)
        self.assertGreaterEqual(len(qa['checks']), 15)
        self.assertLessEqual(qa['metrics']['loaded_npcs'], 18)
        self.assertEqual(qa['metrics']['loaded_chunks'], 9)
