import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "factory" / "build.py"
spec = importlib.util.spec_from_file_location("factory_build", MODULE)
factory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(factory)


class FactoryTests(unittest.TestCase):
    def test_normalizes_a_valid_spec(self):
        assets = factory.validate_spec({"assets": [{"id": "crate", "kind": "prop", "variant": "crate"}]})
        self.assertEqual(assets[0]["max_triangles"], 10000)
        self.assertEqual(assets[0]["size_m"], 1.0)

    def test_rejects_path_traversal_and_duplicate_ids(self):
        for records in (
            [{"id": "../escape", "kind": "prop", "variant": "crate"}],
            [{"id": "a", "kind": "character"}, {"id": "a", "kind": "character"}],
        ):
            with self.assertRaises(ValueError):
                factory.validate_spec({"assets": records})

    def test_rejects_bad_geometry_budget_and_recipe(self):
        for record in (
            {"id": "bad", "kind": "prop", "variant": "unknown"},
            {"id": "bad", "kind": "character", "height_m": -1},
            {"id": "bad", "kind": "character", "max_triangles": 0},
            {"id": "bad", "kind": "character", "color": [1, 0, 2]},
        ):
            with self.assertRaises(ValueError):
                factory.validate_spec({"assets": [record]})

    def test_output_collision_is_non_destructive(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "output"
            dest.mkdir()
            original = dest / "keep.txt"
            original.write_text("existing")
            with self.assertRaises(FileExistsError):
                factory.new_staging(dest)
            self.assertEqual(original.read_text(), "existing")

    def test_manifest_detects_tampered_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.glb").write_bytes(b"test")
            manifest = {"schema": 1, "status": "passed", "files": factory.inventory(root)}
            (root / "manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(factory.verify_package(root), [])
            (root / "sample.glb").write_bytes(b"tampered")
            self.assertTrue(factory.verify_package(root))

    def test_manifest_rejects_unexpected_file_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.glb").write_bytes(b"test")
            (root / "manifest.json").write_text(json.dumps(
                {"schema": 1, "status": "passed", "files": factory.inventory(root)}
            ))
            (root / "surprise").write_text("not recorded")
            self.assertTrue(factory.verify_package(root))


if __name__ == "__main__":
    unittest.main()
