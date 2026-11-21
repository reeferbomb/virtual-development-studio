"""Build a standalone simulation project over a verified Godot world."""

import argparse
import importlib.util
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
loader = importlib.util.spec_from_file_location("simulation_world_factory", HERE.parent / "world/build.py")
world = importlib.util.module_from_spec(loader)
loader.loader.exec_module(world)
factory = world.factory

loader = importlib.util.spec_from_file_location("simulation_world_geometry", HERE.parent / "world/procedural.py")
geometry = importlib.util.module_from_spec(loader)
loader.loader.exec_module(geometry)

SPEC_FIELDS = {
    "vehicle_spawn", "checkpoint", "interactables", "stages", "weather", "cycle_seconds", "start_hour",
}
KINDS = ("beacon", "supply", "switch")
WEATHER = ("clear", "rain", "fog")
RESERVED_IDS = {"spawn", "goal", "vehicle_spawn", "checkpoint"}
QA_MARKER = "STUDIO_SIMULATION_QA_JSON "
REQUIRED_TESTS = {"test_interactions.gd", "test_objectives.gd", "test_vehicle.gd", "test_weather.gd"}
# The vehicle starts facing -Z with a 1.96 × 3.55 m footprint.
VEHICLE_HALF_WIDTH = 1.1
VEHICLE_HALF_DEPTH = 1.9
# A checkpoint can be approached at any heading and clears a 2.5 m trigger.
CHECKPOINT_CLEARANCE = 2.1
CHECKPOINT_REACH = 2.5
OBJECT_CLEARANCE = 0.5


def _ground_point(value, label, terrain, obstacles, half_width, half_depth):
    point = world.vector(value, -128, 128, label)
    x, y, z = point
    flat = terrain["flat_radius"]
    if y != 0 or abs(x) + half_width > flat or abs(z) + half_depth > flat:
        raise ValueError(f"{label} needs ground clearance in the flat core")
    if any(x - half_width <= right and x + half_width >= left
           and z - half_depth <= far and z + half_depth >= near
           for left, near, right, far in obstacles):
        raise ValueError(f"{label} overlaps world collider clearance")
    return point


def _clock(config):
    cycle = factory.number(config["cycle_seconds"], 0.0, sys.float_info.max, "cycle_seconds")
    if cycle <= 0.0:
        raise ValueError("cycle_seconds must be positive")
    hour = factory.number(config["start_hour"], 0.0, 24.0, "start_hour")
    if hour == 24.0:
        raise ValueError("start_hour must be less than 24")
    return cycle, hour


def validate(data, level):
    """Normalize a simulation specification for a validated world level."""
    if not isinstance(data, dict) or data.keys() != SPEC_FIELDS:
        raise ValueError("Simulation spec must contain exactly: " + ", ".join(sorted(SPEC_FIELDS)))
    if data["weather"] not in WEATHER:
        raise ValueError("weather must be clear, rain, or fog")
    if not isinstance(data["interactables"], list):
        raise ValueError("interactables must be a list")
    if not isinstance(data["stages"], list) or not data["stages"]:
        raise ValueError("stages must be a nonempty list")

    cycle, hour = _clock(data)
    terrain = level["terrain"]
    obstacles = geometry.rectangles(level, margin=0.0)
    vehicle = _ground_point(data["vehicle_spawn"], "vehicle_spawn", terrain, obstacles,
                            VEHICLE_HALF_WIDTH, VEHICLE_HALF_DEPTH)
    checkpoint = _ground_point(data["checkpoint"], "checkpoint", terrain, obstacles,
                               CHECKPOINT_CLEARANCE, CHECKPOINT_CLEARANCE)
    if math.dist(vehicle, checkpoint) <= CHECKPOINT_REACH:
        raise ValueError("checkpoint must be outside reach of the parked vehicle")

    def overlaps_car(point, radius):
        return (abs(point[0] - vehicle[0]) <= VEHICLE_HALF_WIDTH + radius
                and abs(point[2] - vehicle[2]) <= VEHICLE_HALF_DEPTH + radius)

    if overlaps_car(level["spawn"], 0.35):
        raise ValueError("vehicle_spawn overlaps the player spawn")

    interactables, ids = [], set()
    for row in data["interactables"]:
        if not isinstance(row, dict) or row.keys() != {"id", "kind", "position"}:
            raise ValueError("Each interactable needs exactly id, kind, and position")
        name = world.identifier(row["id"])
        if name in ids or name in RESERVED_IDS:
            raise ValueError(f"Duplicate or reserved interactable ID: {name}")
        kind = row["kind"]
        if kind not in KINDS:
            raise ValueError(f"Unsupported interactable kind for {name}")
        point = _ground_point(row["position"], f"Interactable {name}", terrain, obstacles,
                              OBJECT_CLEARANCE, OBJECT_CLEARANCE)
        if overlaps_car(point, OBJECT_CLEARANCE):
            raise ValueError(f"Interactable {name} overlaps vehicle_spawn")
        if any(math.dist(point, existing["position"]) < 2 * OBJECT_CLEARANCE for existing in interactables):
            raise ValueError(f"Interactable {name} overlaps another interactable")
        ids.add(name)
        interactables.append({"id": name, "kind": kind, "position": point})

    stages, seen = [], set()
    targets = {"interact": ids, "drive": {"checkpoint"}, "visit": {"goal"}}
    for row in data["stages"]:
        if not isinstance(row, dict) or row.keys() != {"action", "target"}:
            raise ValueError("Each mission stage needs exactly action and target")
        action = row["action"]
        if not isinstance(action, str) or action not in targets:
            raise ValueError("Mission stage action must be interact, drive, or visit")
        target = world.identifier(row["target"])
        if target not in targets[action] or (action, target) in seen:
            raise ValueError(f"Unknown or repeated {action} stage target: {target}")
        seen.add((action, target))
        stages.append({"action": action, "target": target})

    return {
        "vehicle_spawn": vehicle, "checkpoint": checkpoint, "interactables": interactables,
        "stages": stages, "weather": data["weather"], "cycle_seconds": cycle, "start_hour": hour,
    }


def build(spec_path, source, dest, godot="godot", *, simulation_qa=False):
    if dest.resolve().is_relative_to(source.resolve()):
        raise ValueError("Output must be outside the source world package")
    if factory.verify_package(source):
        raise ValueError("World source integrity check failed")
    source_manifest = source / "manifest.json"
    world_sha256 = factory.hash_file(source_manifest)
    level_text = (source / "level.json").read_text(encoding="utf-8")
    level = world.validate(json.loads(level_text))
    if json.loads(source_manifest.read_text(encoding="utf-8")).get("level") != level["id"]:
        raise ValueError("Source must be a verified world factory package")
    config = validate(json.loads(spec_path.read_text(encoding="utf-8")), level)
    if simulation_qa:
        fixture_config = json.loads((HERE / "demo_spec.json").read_text(encoding="utf-8"))
        fixture_level = world.validate(json.loads((HERE / "world_spec.json").read_text(encoding="utf-8")))
        if config != fixture_config or level != fixture_level:
            raise ValueError("--simulation-qa requires the simulation/demo_spec.json and simulation/world_spec.json fixture")
    tests = sorted(file for file in (HERE / "tests").glob("test_*.gd") if file.is_file())
    missing_tests = REQUIRED_TESTS - {file.name for file in tests}
    if missing_tests:
        raise ValueError("Missing simulation component tests: " + ", ".join(sorted(missing_tests)))

    stage = factory.new_staging(dest)
    print(f"Simulation staging: {stage}", flush=True)
    try:
        shutil.copytree(source, stage, symlinks=True, dirs_exist_ok=True)
        if (factory.verify_package(stage)
                or factory.hash_file(stage / "manifest.json") != world_sha256
                or (stage / "level.json").read_text(encoding="utf-8") != level_text):
            raise ValueError("World source changed during staging")
        reports = stage / "reports"
        shutil.copy2(stage / "manifest.json", reports / "world-source-manifest.json")
        for file in sorted((HERE / "template").iterdir()):
            if file.is_file() and file.suffix in {".gd", ".tscn"}:
                shutil.copy2(file, stage / file.name)
        (stage / "tests").mkdir()
        for file in tests:
            shutil.copy2(file, stage / "tests" / file.name)
        factory.write_json(stage / "simulation.json", config)

        project = stage / "project.godot"
        settings = project.read_text(encoding="utf-8")
        world_entry = 'run/main_scene="res://main.tscn"'
        if world_entry not in settings:
            raise ValueError("World project is missing its expected main scene")
        project.write_text(settings.replace(world_entry, 'run/main_scene="res://simulation.tscn"')
                           .replace("Studio Generated Training World", "Studio Simulation Lab"),
                           encoding="utf-8")

        command = [godot, "--headless", "--path", str(stage)]
        world.run_stage(command + ["--editor", "--import"], reports / "simulation-import.log")
        world.run_stage(command + ["--quit-after", "10"], reports / "simulation-launch.log",
                        "STUDIO_SIMULATION_READY")
        fixed = command + ["--fixed-fps", "60"]
        for file in tests:
            world.run_stage(fixed + ["--script", f"res://tests/{file.name}"], reports / f"{file.stem}.log")

        qa = None
        if simulation_qa:
            log = reports / "simulation-qa.log"
            output = world.run_stage(fixed + ["--script", "res://simulation_qa.gd"], log, QA_MARKER)
            lines = [line.removeprefix(QA_MARKER) for line in output.splitlines() if line.startswith(QA_MARKER)]
            if len(lines) != 1:
                raise ValueError(f"Simulation QA must emit one report. See {log}")
            try:
                qa = json.loads(lines[0])
            except ValueError as exc:
                raise ValueError(f"Simulation QA emitted invalid JSON. See {log}") from exc
            if not isinstance(qa, dict) or qa.get("pass") is not True:
                raise ValueError(f"Simulation QA failed. See {log}")
            factory.write_json(reports / "simulation-qa.json", qa)

        cache = stage / ".godot"
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
        factory.write_json(stage / "manifest.json", {
            "schema": 1, "status": "passed", "world_sha256": world_sha256,
            "simulation_qa": qa, "files": factory.inventory(stage),
        })
        if factory.verify_package(stage) or dest.exists() or dest.is_symlink():
            raise ValueError("Destination integrity or overwrite check failed")
        stage.rename(dest)
        print(f"SIMULATION_FACTORY_PASS {dest}")
    except Exception:
        print(f"Simulation build failed; diagnostics retained: {stage}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", nargs="?", type=Path)
    parser.add_argument("--world", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--godot", default="godot")
    parser.add_argument("--simulation-qa", action="store_true", help="Run the integrated expedition QA fixture")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        errors = factory.verify_package(args.verify.absolute())
        print("; ".join(errors) if errors else "SIMULATION_INTEGRITY_PASS")
        return int(bool(errors))
    if not all((args.spec, args.world, args.output)):
        parser.error("Specify simulation spec, --world, --output, or --verify")
    build(args.spec.absolute(), args.world.absolute(), args.output.absolute(), args.godot,
          simulation_qa=args.simulation_qa)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError, OverflowError, subprocess.TimeoutExpired) as exc:
        print(f"Simulation factory: {exc}", file=sys.stderr)
        sys.exit(1)
