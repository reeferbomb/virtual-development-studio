import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "asset_audit.py"


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
