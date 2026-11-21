import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from command_center.catalog import catalog

ROOT = Path(__file__).resolve().parents[1]


class CommandCatalogTests(unittest.TestCase):
    def test_shipped_catalog(self):
        data = catalog(ROOT)
        packages = {package['id']: package for package in data['packages']}
        self.assertEqual(len(data["packages"]), 16)
        self.assertEqual(len(packages), 16)
        self.assertIn("frontier", packages)
        self.assertIn("expedition", packages)
        self.assertIn("tactical_yard", packages)
        self.assertEqual(packages['unified_expedition']['kind'], 'unified')
        self.assertEqual(packages['unified_expedition']['path'], 'unified/demo/expedition')
        self.assertEqual(packages['living_world']['kind'], 'living')
        self.assertEqual(packages['living_world']['path'], 'living/demo/frontier')
        self.assertEqual(packages['metropolis']['kind'], 'city')
        self.assertEqual(packages['metropolis']['path'], 'city/demo/metropolis')
        self.assertEqual(packages['vertical_city']['kind'], 'vertical')
        self.assertEqual(packages['vertical_city']['path'], 'vertical/demo/connected_city')
        self.assertEqual(packages['advanced_city']['kind'], 'advanced')
        self.assertEqual(packages['advanced_city']['path'], 'advanced/demo/advanced_city')
        self.assertEqual(packages['frontline_city']['kind'], 'frontline')
        self.assertEqual(packages['frontline_city']['path'], 'frontline/demo/frontline_city')
        self.assertTrue(all(p["verified"] for p in data["packages"]))
        self.assertEqual({a["id"] for a in data["animations"]},
                         {"Aim", "Crouch", "Idle", "Idle_loop", "Reload", "Run", "Walk"})
        self.assertEqual({a["id"] for a in data["audio"]}, {"ambience", "footstep", "thunder"})
        for cue in data["audio"]:
            self.assertGreater(cue["seconds"], 0)
            self.assertTrue((ROOT / cue["path"]).is_file())
        assets = {a["id"]: a for a in data["assets"]}
        self.assertIn("supply_crate", assets)
        self.assertTrue((ROOT / assets["city"]["preview"]).is_file())
        for asset in assets.values():
            for file in asset["files"]:
                self.assertFalse(Path(file["path"]).is_absolute())
                self.assertEqual((ROOT / file["path"]).stat().st_size, file["bytes"])

    def test_same_size_tamper_changes_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "world/demo/training_yard"
            package.mkdir(parents=True)
            data = package / "level.json"
            data.write_bytes(b"ab")
            (package / "manifest.json").write_text(json.dumps({
                "schema": 1, "status": "passed", "files": [
                    {"path": "level.json", "bytes": 2, "sha256": hashlib.sha256(b"ab").hexdigest()}]}))
            def verified():
                return next(p["verified"] for p in catalog(root)["packages"] if p["id"] == "training_yard")
            self.assertTrue(verified())
            data.write_bytes(b"ac")
            self.assertFalse(verified())
