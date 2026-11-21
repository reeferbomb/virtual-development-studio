import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "studio.py"


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "studio.json"

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, ok=True):
        result = subprocess.run(
            [sys.executable, str(CLI), "--state", str(self.state), *args],
            capture_output=True, text=True, timeout=20,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def register(self):
        self.cli("register", "demo", "--name", "Demo", "--source", str(self.root),
                 "--objective", "Deliver a verified prototype")

    def task(self, id, *extra):
        self.cli("task", "demo", id, "--title", "Probe " + id, "--owner", "Quality",
                 "--acceptance", "Verification exits zero", *extra)

    def load(self):
        return json.loads(self.state.read_text())["projects"][0]

    def test_registration_preserves_existing_project(self):
        self.register()
        self.cli("register", "demo", "--name", "Replacement", "--source", str(self.root),
                 "--objective", "Different", ok=False)
        self.assertEqual(self.load()["name"], "Demo")

    def test_invalid_id_does_not_change_state(self):
        self.cli("register", "../bad", "--name", "Bad", "--source", str(self.root),
                 "--objective", "Bad", ok=False)
        self.assertFalse(self.state.exists())

    def test_dependency_is_not_runnable_until_passed(self):
        self.register()
        self.task("base")
        self.task("child", "--depends", "base")
        self.cli("run", "demo", "child", "--", sys.executable, "-c", "print('bad')", ok=False)
        self.assertEqual(self.load()["tasks"][1]["status"], "pending")

    def test_pass_records_verifiable_evidence_and_unblocks(self):
        self.register()
        self.task("base")
        self.task("child", "--depends", "base")
        self.cli("run", "demo", "base", "--", sys.executable, "-c", "print('evidence')")
        task = self.load()["tasks"][0]
        self.assertEqual(task["status"], "passed")
        self.assertIn("evidence", Path(task["evidence"][-1]["log"]).read_text())
        self.assertEqual(len(task["evidence"][-1]["sha256"]), 64)
        self.cli("run", "demo", "child", "--", sys.executable, "-c", "print('done')")
        self.assertEqual(self.load()["tasks"][1]["status"], "passed")

    def test_failure_is_not_pass(self):
        self.register()
        self.task("base")
        self.cli("run", "demo", "base", "--", sys.executable, "-c", "raise SystemExit(3)", ok=False)
        evidence = self.load()["tasks"][0]["evidence"][-1]
        self.assertEqual(evidence["exit_code"], 3)
        self.assertEqual(self.load()["tasks"][0]["status"], "failed")

    def test_unsafe_or_missing_dependency_rejected(self):
        self.register()
        self.cli("task", "demo", "x", "--title", "Task", "--owner", "QA",
                 "--acceptance", "test", "--depends", "missing", ok=False)
        self.assertEqual(self.load()["tasks"], [])

    def test_brief_and_report_do_not_claim_unknown_acceptance(self):
        self.register()
        self.task("base")
        self.assertIn("Verification exits zero", self.cli("brief", "demo", "base").stdout)
        self.assertIn("0/1", self.cli("report").stdout)

    def test_tampered_evidence_blocks_gate(self):
        self.register()
        self.task("base")
        self.cli("gate", "demo", "G2", "--task", "base")
        self.cli("run", "demo", "base", "--", sys.executable, "-c", "print('verified')")
        self.assertIn("G2: passed", self.cli("report").stdout)
        Path(self.load()["tasks"][0]["evidence"][-1]["log"]).write_text("tampered")
        self.assertIn("G2: blocked", self.cli("report").stdout)

    def test_rerun_invalidates_downstream_pass(self):
        self.register()
        self.task("base")
        self.task("child", "--depends", "base")
        for task in ("base", "child", "base"):
            self.cli("run", "demo", task, "--", sys.executable, "-c", "print('verified')")
        self.assertEqual(self.load()["tasks"][1]["status"], "pending")

    def test_unlinked_gate_is_never_passed(self):
        self.register()
        self.cli("gate", "demo", "Device acceptance")
        self.assertIn("Device acceptance: pending", self.cli("report").stdout)


if __name__ == "__main__":
    unittest.main()
