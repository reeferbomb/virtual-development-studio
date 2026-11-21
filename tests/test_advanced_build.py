import json
from pathlib import Path
import shutil
import tempfile
import unittest

from advanced import build as advanced
from city import layout
from factory import build as factory


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = {'seed': 237, 'blocks': 4, 'block_size': 48, 'traffic': 12, 'civilians': 20}
PACKAGE = ROOT / 'advanced/demo/advanced_city'


class AdvancedBuildTests(unittest.TestCase):
    def test_fixture_and_exact_qa_guard(self):
        path = ROOT / 'advanced/demo_spec.json'
        self.assertEqual(advanced.validate(json.loads(path.read_text())), FIXTURE)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            spec = directory / 'custom.json'
            factory.write_json(spec, dict(FIXTURE, seed=238))
            with self.assertRaisesRegex(ValueError, 'exact shipped fixture'):
                advanced.build(spec, directory / 'rejected', advanced_qa=True)
            self.assertEqual(list(directory.iterdir()), [spec])

    def test_shipped_project_carries_inherited_and_advanced_evidence(self):
        self.assertEqual(advanced.verify(PACKAGE), [])
        manifest = json.loads((PACKAGE / 'manifest.json').read_text())
        self.assertEqual(manifest['kind'], 'advanced')
        self.assertEqual(manifest['spec'], FIXTURE)
        self.assertEqual(json.loads((PACKAGE / 'city.json').read_text()), layout.generate(FIXTURE))
        self.assertEqual(manifest['advanced_qa'], json.loads((PACKAGE / advanced.REPORT).read_text()))
        self.assertIs(manifest['advanced_qa']['pass'], True)
        self.assertIn(advanced.READY, (PACKAGE / 'reports/launch.log').read_text().splitlines())
        self.assertIn('run/main_scene="res://advanced.tscn"', (PACKAGE / 'project.godot').read_text())
        self.assertEqual(sorted(path.name for path in PACKAGE.glob('*.tscn')),
                         ['advanced.tscn', 'city.tscn', 'vertical.tscn'])
        self.assertFalse((PACKAGE / '.godot').exists())
        runtime, tests, _ = advanced._sources()
        self.assertEqual(len(tests), 12)
        for path in runtime:
            self.assertTrue((PACKAGE / path.name).is_file(), path.name)
        for path in tests:
            self.assertTrue((PACKAGE / 'tests' / path.name).is_file(), path.name)
            self.assertTrue((PACKAGE / 'reports' / f'{path.stem}.log').is_file(), path.name)

    def test_report_must_match_manifest_and_execution_even_after_rehashing(self):
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / 'city'
            shutil.copytree(PACKAGE, copy)
            report_path = copy / advanced.REPORT
            manifest_path = copy / 'manifest.json'
            manifest = json.loads(manifest_path.read_text())
            report = json.loads(report_path.read_text())
            report['checks'][0]['name'] = 'changed'
            factory.write_json(report_path, report)
            self.assertIn('Inventory or file hashes differ from manifest.', advanced.verify(copy))

            manifest['files'] = factory.inventory(copy)
            factory.write_json(manifest_path, manifest)
            self.assertIn('Advanced City scenario QA differs from the manifest', advanced.verify(copy))

            manifest['advanced_qa'] = report
            factory.write_json(manifest_path, manifest)
            self.assertIn('Advanced City scenario QA differs from the execution log', advanced.verify(copy))
