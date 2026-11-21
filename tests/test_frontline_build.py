import json
from pathlib import Path
import shutil
import tempfile
import unittest

from advanced import build as advanced
from city import layout
from factory import build as factory
from frontline import build as frontline


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'frontline/demo_spec.json'
PACKAGE = ROOT / 'frontline/demo/frontline_city'
FIXTURE = {'seed': 237, 'blocks': 4, 'block_size': 48, 'traffic': 12, 'civilians': 20}


class FrontlineBuildTests(unittest.TestCase):
    def test_fixture_and_exact_qa_guard(self):
        self.assertEqual(frontline.validate(json.loads(SPEC.read_text())), FIXTURE)
        self.assertEqual(frontline._fixture(), advanced._fixture())
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            spec = directory / 'custom.json'
            factory.write_json(spec, dict(FIXTURE, seed=238))
            with self.assertRaisesRegex(ValueError, 'exact shipped fixture'):
                frontline.build(spec, directory / 'rejected', frontline_qa=True)
            self.assertEqual(list(directory.iterdir()), [spec])

    def test_shipped_project_contains_inherited_and_frontline_evidence(self):
        self.assertEqual(frontline.verify(PACKAGE), [])
        manifest = json.loads((PACKAGE / 'manifest.json').read_text())
        self.assertEqual(manifest['kind'], 'frontline')
        self.assertEqual(manifest['spec'], FIXTURE)
        self.assertEqual(json.loads((PACKAGE / 'city.json').read_text()), layout.generate(FIXTURE))
        self.assertEqual(manifest['frontline_qa'], json.loads((PACKAGE / frontline.REPORT).read_text()))
        self.assertIs(manifest['frontline_qa']['pass'], True)
        self.assertIn(frontline.READY, (PACKAGE / 'reports/launch.log').read_text().splitlines())
        self.assertIn('run/main_scene="res://frontline.tscn"', (PACKAGE / 'project.godot').read_text())
        self.assertEqual(sorted(path.name for path in PACKAGE.glob('*.tscn')),
                         ['advanced.tscn', 'city.tscn', 'frontline.tscn', 'vertical.tscn'])
        self.assertFalse((PACKAGE / '.godot').exists())

        runtime, tests, project_file = frontline._sources()
        inherited_runtime, inherited_tests, inherited_project = advanced._sources()
        self.assertEqual(project_file, inherited_project)
        self.assertTrue(set(inherited_runtime).issubset(runtime))
        self.assertTrue(set(inherited_tests).issubset(tests))
        self.assertEqual(len(tests), 17)
        for path in runtime:
            self.assertTrue((PACKAGE / path.name).is_file(), path.name)
        for path in tests:
            self.assertTrue((PACKAGE / 'tests' / path.name).is_file(), path.name)
            self.assertTrue((PACKAGE / 'reports' / f'{path.stem}.log').is_file(), path.name)

    def test_report_must_match_manifest_and_execution_even_after_rehashing(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / 'city'
            shutil.copytree(PACKAGE, package)
            report_path = package / frontline.REPORT
            manifest_path = package / 'manifest.json'
            manifest = json.loads(manifest_path.read_text())
            report = json.loads(report_path.read_text())
            report['checks'][0]['name'] = 'Changed check'
            factory.write_json(report_path, report)
            self.assertIn('Inventory or file hashes differ from manifest.', frontline.verify(package))

            manifest['files'] = factory.inventory(package)
            factory.write_json(manifest_path, manifest)
            self.assertIn('Frontline City scenario QA differs from the manifest', frontline.verify(package))

            manifest['frontline_qa'] = report
            factory.write_json(manifest_path, manifest)
            self.assertIn('Frontline City scenario QA differs from the execution log', frontline.verify(package))
