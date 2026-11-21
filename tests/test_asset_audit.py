import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "asset_audit.py"
CINEMATIC = CLI.parent / "cinematic" / "demo" / "nightfall_patrol"


class AssetAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "assets"
        self.root.mkdir()

    def run_cli(self, *args):
        proc = subprocess.run([sys.executable, str(CLI), str(self.root), *args],
                              check=False, capture_output=True, text=True)
        return proc.returncode, json.loads(proc.stdout)

    def manifest(self, rows):
        (self.root / "provenance.json").write_text(json.dumps(rows))

    def godot_fixture(self):
        (self.root.parent / "project.godot").touch()
        source = self.root / "city.glb"
        source.write_bytes(b"fixture")
        sidecar = self.root / "city.glb.import"
        shutil.copyfile(CINEMATIC / "assets" / sidecar.name, sidecar)
        self.manifest([dict(path=source.name, source="fixture", license="MIT",
                            attribution="Studio")])
        return source, sidecar

    def test_generated_import_is_in_inventory_and_budgets(self):
        source, sidecar = self.godot_fixture()
        status, report = self.run_cli()
        self.assertEqual(status, 0, report["errors"])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(report["files"][1],
                         dict(path=sidecar.name, bytes=sidecar.stat().st_size,
                              category="godot_import"))
        self.assertEqual(report["total_bytes"], source.stat().st_size + sidecar.stat().st_size)
        status, report = self.run_cli("--max-file-bytes", str(sidecar.stat().st_size - 1),
                                      "--max-total-bytes", str(report["total_bytes"] - 1))
        self.assertEqual(status, 1)
        self.assertIn(dict(code="file_budget_exceeded", path=sidecar.name), report["errors"])
        self.assertIn(dict(code="total_budget_exceeded", path="."), report["errors"])

    def test_import_requires_real_listed_source(self):
        source, sidecar = self.godot_fixture()
        expected = dict(code="missing_provenance", path=sidecar.name)
        status, report = self.run_cli()
        self.assertEqual(status, 0, report["errors"])
        source.unlink()
        self.assertIn(expected, self.run_cli()[1]["errors"])
        external = self.root.parent / "outside.glb"
        external.touch()
        source.symlink_to(external)
        self.assertIn(expected, self.run_cli()[1]["errors"])
        source.unlink()
        source.touch()
        self.manifest([])
        self.assertEqual(self.run_cli()[1]["errors"],
                         [dict(code="missing_provenance", path=source.name), expected])

    def test_malformed_or_misdirected_import_still_requires_provenance(self):
        _, sidecar = self.godot_fixture()
        valid = sidecar.read_bytes()
        expected = dict(code="missing_provenance", path=sidecar.name)
        for data in (b"arbitrary content", b"\xff", valid.replace(b"[deps]", b"[other]"),
                     valid.replace(b"res://assets/city.glb", b"res://other/city.glb"),
                     valid.replace(b'path="res://.godot/', b'path="res://elsewhere/'),
                     valid.replace(b'importer="scene"', b'importer="wav"'),
                     valid.replace(b'uid="uid://', b'uid="invalid://'),
                     valid.replace(b"animation/fps=30", b"animation/fps=invalid"),
                     valid + b"invalid trailing content\n", valid + b"#" + b"x" * 65536):
            with self.subTest(data=data[:32]):
                sidecar.write_bytes(data)
                self.assertIn(expected, self.run_cli()[1]["errors"])
        sidecar.write_bytes(valid)
        (self.root.parent / "project.godot").unlink()
        self.assertIn(expected, self.run_cli()[1]["errors"])

    def test_bundled_cinematic_asset_records_match_inventory_and_license(self):
        provenance = CINEMATIC / "assets" / "provenance.json"
        inventory = json.loads((CINEMATIC / "manifest.json").read_text())["files"]
        entry = next(row for row in inventory if row["path"] == "assets/provenance.json")
        self.assertEqual(entry["sha256"], hashlib.sha256(provenance.read_bytes()).hexdigest())
        self.assertEqual(entry["bytes"], provenance.stat().st_size)
        rows = json.loads(provenance.read_text())
        self.assertEqual(len(rows), 7)
        spec = importlib.util.spec_from_file_location("cinematic_build", CLI.parent / "cinematic/build.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        for row in rows:
            with self.subTest(path=row["path"]):
                self.assertEqual(row["license"], "MIT")
                self.assertIn("Virtual Development Studio contributors", row["attribution"])
                file = provenance.parent / row["path"]
                data = file.read_bytes()
                self.assertEqual(row["sha256"], hashlib.sha256(data).hexdigest())
                shutil.copyfile(file, self.root / file.name)
        self.assertEqual(builder.original_asset_provenance(self.root), rows)
        (self.root / "additional.wav").touch()
        with self.assertRaises(ValueError):
            builder.original_asset_provenance(self.root)

    def test_valid_inventory_and_limit_boundary(self):
        (self.root / "hat.glb").write_bytes(b"abc")
        self.manifest([dict(path="hat.glb", source="Ana", license="CC0",
                            attribution="not required")])
        status, report = self.run_cli("--max-file-bytes", "3")
        self.assertEqual(status, 0)
        self.assertEqual(report["files"], [dict(path="hat.glb", bytes=3, category="scene")])

    def test_collision_budget_and_metadata(self):
        for name in ["Hat.glb", "hat.glb"]:
            (self.root / name).write_bytes(b"abc")
        self.manifest([dict(path="Hat.glb", license="CC0"), dict(path="../bad")])
        status, report = self.run_cli("--max-file-bytes", "2", "--max-total-bytes", "5")
        self.assertEqual(status, 1)
        self.assertEqual({item["code"] for item in report["errors"]},
                         {"case_collision", "file_budget_exceeded", "total_budget_exceeded",
                          "missing_source", "missing_attribution", "missing_provenance",
                          "invalid_manifest_path"})

    def test_external_links(self):
        outside = self.root.parent / "private"
        outside.mkdir()
        (outside / "secret.png").touch()
        (self.root / "shortcut").symlink_to(outside, target_is_directory=True)
        self.manifest([])
        status, report = self.run_cli()
        self.assertEqual(status, 0)
        self.assertEqual(report["files"], [])
        self.assertEqual(report["warnings"][0]["code"], "skipped_symlink")
        (self.root / "provenance.json").unlink()
        (self.root / "provenance.json").symlink_to(outside / "secret.png")
        status, report = self.run_cli()
        self.assertEqual(status, 1)
        self.assertEqual(report["errors"][0]["code"], "missing_or_invalid_manifest")
        self.root = self.root / "shortcut"
        self.assertEqual(self.run_cli()[1]["errors"][0]["code"], "symlink_root")
