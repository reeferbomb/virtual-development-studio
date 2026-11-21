import json
import shutil
import tempfile
import unittest
from pathlib import Path

from city import layout
from factory import build as factory
from vertical import build as vertical


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = {"seed": 237, "blocks": 4, "block_size": 48, "traffic": 12, "civilians": 20}


class VerticalBuildTests(unittest.TestCase):
    def test_fixture_and_exact_qa_guard(self):
        path = ROOT / 'vertical/demo_spec.json'
        self.assertEqual(vertical.validate(json.loads(path.read_text())), FIXTURE)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            spec = directory / 'custom.json'
            factory.write_json(spec, dict(FIXTURE, seed=238))
            destination = directory / 'rejected'
            with self.assertRaisesRegex(ValueError, 'exact shipped fixture'):
                vertical.build(spec, destination, vertical_qa=True)
            self.assertEqual(list(directory.iterdir()), [spec])

    def test_shipped_manifest_binds_layout_and_scenario(self):
        package = ROOT / 'vertical/demo/connected_city'
        self.assertEqual(vertical.verify(package), [])
        manifest = json.loads((package / 'manifest.json').read_text())
        self.assertEqual(manifest['kind'], 'vertical')
        self.assertEqual(manifest['spec'], FIXTURE)
        self.assertEqual(json.loads((package / 'city.json').read_text()), layout.generate(FIXTURE))
        self.assertEqual(manifest['vertical_qa'], json.loads((package / vertical.REPORT).read_text()))
        self.assertIs(manifest['vertical_qa']['pass'], True)
        self.assertIn(vertical.READY, (package / 'reports/launch.log').read_text())
        runtime, tests, _ = vertical._sources()
        for path in runtime:
            self.assertTrue((package / path.name).is_file(), path.name)
        for path in tests:
            self.assertTrue((package / 'tests' / path.name).is_file(), path.name)
            self.assertTrue((package / 'reports' / f'{path.stem}.log').is_file(), path.name)

        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / 'city'
            shutil.copytree(package, copy)
            report_path = copy / vertical.REPORT
            report = json.loads(report_path.read_text())
            report['pass'] = False
            factory.write_json(report_path, report)
            self.assertIn('Inventory or file hashes differ from manifest.', vertical.verify(copy))
            manifest['files'] = factory.inventory(copy)
            factory.write_json(copy / 'manifest.json', manifest)
            self.assertIn('Vertical City scenario QA differs from the manifest', vertical.verify(copy))
