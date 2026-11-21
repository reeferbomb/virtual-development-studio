import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "simulation/build.py"
SPEC_PATH = ROOT / "simulation/demo_spec.json"
SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
WORLD_SPEC = json.loads((ROOT / "simulation/world_spec.json").read_text(encoding="utf-8"))
loader = importlib.util.spec_from_file_location("simulation_factory", BUILDER_PATH)
builder = importlib.util.module_from_spec(loader)
loader.loader.exec_module(builder)
LEVEL = builder.world.validate(WORLD_SPEC)


class SimulationSpecTests(unittest.TestCase):
    def test_demo_and_supported_environment_settings(self):
        self.assertEqual(builder.validate(SPEC, LEVEL), SPEC)
        for weather in ("clear", "rain", "fog"):
            with self.subTest(weather=weather):
                settings = {**SPEC, "weather": weather, "start_hour": 23.999, "cycle_seconds": 6.5}
                self.assertEqual(builder.validate(settings, LEVEL), settings)

    def test_strict_coordinates_and_clock(self):
        for key, value in (
            ("vehicle_spawn", [True, 0, 10]), ("vehicle_spawn", [0, 10]),
            ("vehicle_spawn", [0, 1, 10]), ("vehicle_spawn", [float("inf"), 0, 10]),
            ("checkpoint", [25, 0, -10]), ("weather", "hail"),
            ("start_hour", 24), ("start_hour", -0.01), ("start_hour", float("nan")),
            ("cycle_seconds", 0), ("cycle_seconds", -1), ("cycle_seconds", True),
        ):
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key):
                builder.validate({**SPEC, key: value}, LEVEL)
        with self.assertRaisesRegex(ValueError, "exactly"):
            builder.validate({**SPEC, "unknown": True}, LEVEL)

    def test_clearance_checks_blocks_props_and_initial_actor_positions(self):
        for key, value, message in (
            ("vehicle_spawn", [-13, 0, 7], "world collider"),
            ("vehicle_spawn", [-4, 0, 10], "player spawn"),
            ("checkpoint", [0, 0, 9], "outside reach"),
            ("interactables", [{"id": "relay", "kind": "beacon", "position": [10, 0, -7.5]}], "world collider"),
            ("interactables", [{"id": "relay", "kind": "beacon", "position": [0, 0, 10]}], "vehicle_spawn"),
        ):
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, message):
                builder.validate({**SPEC, key: value}, LEVEL)

    def test_mission_stage_targets_match_a_single_runtime_action(self):
        for stage in (
            {"action": "fly", "target": "goal"},
            {"action": "interact", "target": "goal"},
            {"action": "drive", "target": "relay"},
            {"action": "visit", "target": "spawn"},
            {"action": "visit", "target": []},
            SPEC["stages"][0],
        ):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                builder.validate({**SPEC, "stages": SPEC["stages"] + [stage]}, LEVEL)

    def test_object_kinds_unique_ids_and_non_demo_stage_orders(self):
        for duplicate in ("relay", "goal", "checkpoint", "bad/id"):
            config = copy.deepcopy(SPEC)
            config["interactables"].append({"id": duplicate, "kind": "switch", "position": [-4, 0, -4]})
            with self.subTest(id=duplicate), self.assertRaises(ValueError):
                builder.validate(config, LEVEL)
        config = copy.deepcopy(SPEC)
        config["interactables"] = [{"id": "switch_a", "kind": "switch", "position": [-4, 0, -4]},
                                   {"id": "supply_a", "kind": "supply", "position": [-5, 0, 4]}]
        config["stages"] = [{"action": "visit", "target": "goal"},
                            {"action": "interact", "target": "switch_a"},
                            {"action": "interact", "target": "supply_a"}]
        self.assertEqual(builder.validate(config, LEVEL), config)


class SimulationBuildTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = self.root / "world"
        self.dest = self.root / "simulation"
        (self.source / "reports").mkdir(parents=True)
        builder.factory.write_json(self.source / "level.json", LEVEL)
        (self.source / "project.godot").write_text(
            '[application]\nconfig/name="Studio Generated Training World"\nrun/main_scene="res://main.tscn"\n',
            encoding="utf-8",
        )
        (self.source / "world.tscn").write_text("[gd_scene format=3]\n", encoding="utf-8")
        builder.factory.write_json(self.source / "manifest.json", {
            "schema": 1, "status": "passed", "level": LEVEL["id"],
            "files": builder.factory.inventory(self.source),
        })

    def _build(self, qa_output=None):
        def invoke(command, log, timeout):
            if command[-2:] == ["--quit-after", "10"]:
                log.write_text("STUDIO_SIMULATION_READY\n", encoding="utf-8")
            elif command[-2:] == ["--script", "res://simulation_qa.gd"]:
                self.assertEqual(command[-4:-2], ["--fixed-fps", "60"])
                log.write_text(qa_output, encoding="utf-8")
            else:
                log.touch()

        with (patch.object(builder.factory, "invoke", side_effect=invoke),
              redirect_stdout(StringIO()), redirect_stderr(StringIO())):
            builder.build(SPEC_PATH, self.source, self.dest, simulation_qa=qa_output is not None)

    def test_validated_report_and_component_tests_are_in_the_verified_package(self):
        report = {"pass": True, "checks": [{"name": "expedition", "status": "passed"}]}
        self._build(builder.QA_MARKER + json.dumps(report) + "\n")
        self.assertEqual(builder.factory.verify_package(self.dest), [])
        self.assertIn('run/main_scene="res://simulation.tscn"', (self.dest / "project.godot").read_text())
        self.assertEqual(json.loads((self.dest / "simulation.json").read_text()), SPEC)
        self.assertEqual(json.loads((self.dest / "reports/simulation-qa.json").read_text()), report)
        manifest = json.loads((self.dest / "manifest.json").read_text())
        self.assertEqual(manifest["simulation_qa"], report)
        self.assertEqual(manifest["world_sha256"], builder.factory.hash_file(self.source / "manifest.json"))
        self.assertTrue((self.dest / "reports/world-source-manifest.json").is_file())
        for test in sorted((ROOT / "simulation/tests").glob("test_*.gd")):
            with self.subTest(test=test.name):
                self.assertTrue((self.dest / "tests" / test.name).is_file())
                self.assertTrue((self.dest / "reports" / f"{test.stem}.log").is_file())
        proc = subprocess.run([sys.executable, str(BUILDER_PATH), "--verify", str(self.dest)],
                              capture_output=True, text=True, check=False, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("SIMULATION_INTEGRITY_PASS", proc.stdout)

    def test_optional_qa_is_not_run_without_flag(self):
        self._build()
        self.assertIsNone(json.loads((self.dest / "manifest.json").read_text())["simulation_qa"])
        self.assertFalse((self.dest / "reports/simulation-qa.json").exists())

    def test_full_qa_requires_the_default_fixture(self):
        custom_spec = self.root / "custom.json"
        builder.factory.write_json(custom_spec, {**SPEC, "weather": "rain"})
        with self.assertRaisesRegex(ValueError, "--simulation-qa requires"):
            builder.build(custom_spec, self.source, self.dest, simulation_qa=True)
        self.assertFalse(self.dest.exists())

    def test_fails_if_a_required_component_test_is_missing(self):
        with patch.object(builder, "HERE", self.root):
            with self.assertRaisesRegex(ValueError, "Missing simulation component tests.*test_vehicle.gd"):
                builder.build(SPEC_PATH, self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_qa_rejects_invalid_duplicate_or_failing_reports(self):
        for output in (
            '{"pass":false}\n', '{"pass":1}\n', '[]\n', '{bad JSON}\n',
            '{"pass":true}\n' + builder.QA_MARKER + '{"pass":true}\n',
        ):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "Simulation QA"):
                self._build(builder.QA_MARKER + output)
            self.assertFalse(self.dest.exists())

    def test_refuses_nested_output_and_modified_world(self):
        with self.assertRaisesRegex(ValueError, "outside the source world"):
            builder.build(SPEC_PATH, self.source, self.source / "nested")
        self.assertEqual(builder.factory.verify_package(self.source), [])
        (self.source / "world.tscn").write_text("modified", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "World source integrity"):
            builder.build(SPEC_PATH, self.source, self.dest)
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
