"""Generate a new editable Godot project from a structured level design."""
import argparse
import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
loader = importlib.util.spec_from_file_location("asset_factory", HERE.parent / "factory" / "build.py")
factory = importlib.util.module_from_spec(loader)
loader.loader.exec_module(factory)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ValueError("Unsafe or missing identifier")
    return value


def vector(value, low, high, label):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} needs three numeric coordinates")
    return [factory.number(x, low, high, label) for x in value]


def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get("terrain"), dict):
        raise ValueError("Invalid level specification")
    t = data["terrain"]
    width = factory.number(t.get("width"), 12, 256, "terrain width")
    depth = factory.number(t.get("depth"), 12, 256, "terrain depth")
    flat_radius = factory.number(t.get("flat_radius"), 2, min(width, depth) / 2 - 1, "flat radius")
    terrain = {"width": width, "depth": depth,
               "segments": factory.integer(t.get("segments"), 8, 128, "terrain segments"),
               "flat_radius": flat_radius,
               "amplitude": factory.number(t.get("amplitude", 0), 0, 4, "terrain amplitude")}
    spawn = vector(data.get("spawn"), -128, 128, "spawn")
    goal = vector(data.get("goal"), -128, 128, "goal")
    for point in (spawn, goal):
        if point[1] != 0 or max(abs(point[0]), abs(point[2])) + .6 > flat_radius:
            raise ValueError("Spawn and goal must have ground clearance inside the flat core")
    if math.dist(spawn, goal) < 3:
        raise ValueError("Spawn and goal must be at least 3m apart")
    ids, blocks, placements = set(), [], []

    def new_id(row):
        if not isinstance(row, dict):
            raise ValueError("Level objects must be JSON objects")
        name = identifier(row.get("id"))
        if name in ids or name in {"spawn", "goal", "terrain", "world", "player"}:
            raise ValueError("Duplicate or reserved object ID")
        ids.add(name)
        return name

    def bounds_check(pos, size):
        if abs(pos[0]) + size[0] / 2 > width / 2 - .5 or abs(pos[2]) + size[2] / 2 > depth / 2 - .5:
            raise ValueError("Object extends beyond the playable terrain")
        for point in (spawn, goal):
            if (abs(pos[0] - point[0]) < size[0] / 2 + .45 and
                abs(pos[2] - point[2]) < size[2] / 2 + .45 and
                pos[1] + size[1] / 2 > point[1] and
                pos[1] - size[1] / 2 < point[1] + 1.8):
                raise ValueError("Object collides with spawn or goal clearance")

    for key in ("blocks", "placements"):
        if not isinstance(data.get(key, []), list) or len(data.get(key, [])) > 128:
            raise ValueError(f"{key} must be a list with up to 128 objects")
    for row in data.get("blocks", []):
        name = new_id(row)
        pos = vector(row.get("position"), -128, 128, "block position")
        size = vector(row.get("size"), .05, 64, "block dimensions")
        bounds_check(pos, size)
        blocks.append({"id": name, "position": pos, "size": size,
                       "color": vector(row.get("color", [.33, .37, .39]), 0, 1, "block color")})
    for row in data.get("placements", []):
        name = new_id(row)
        pos = vector(row.get("position"), -128, 128, "placement position")
        yaw = factory.number(row.get("yaw_deg", 0), -360, 360, "yaw")
        asset = {"id": name, "asset": identifier(row.get("asset")), "position": pos, "yaw_deg": yaw}
        if "collider_size" in row:
            size = vector(row["collider_size"], .05, 32, "collider size")
            r = math.radians(yaw)
            aabb = [abs(math.cos(r))*size[0] + abs(math.sin(r))*size[2], size[1],
                    abs(math.sin(r))*size[0] + abs(math.cos(r))*size[2]]
            bounds_check([pos[0], pos[1]+size[1]/2, pos[2]], aabb)
            asset["collider_size"] = size
        elif abs(pos[0]) > width/2-.5 or abs(pos[2]) > depth/2-.5:
            raise ValueError("Placement is outside the terrain")
        placements.append(asset)
    return {"id": identifier(data.get("id")), "terrain": terrain, "spawn": spawn, "goal": goal,
            "blocks": blocks, "placements": placements}


def run_stage(args, log, marker=None):
    factory.invoke(args, log, timeout=120)
    output = log.read_text(encoding="utf-8", errors="replace")
    if "SCRIPT ERROR:" in output or "Parse Error:" in output or (marker and marker not in output):
        raise ValueError(f"Godot stage did not pass. See {log}")
    return output


def build(spec_path, batch, dest, godot, demo_qa, route_qa=False):
    spec = validate(json.loads(spec_path.read_text(encoding="utf-8")))
    if factory.verify_package(batch):
        raise ValueError("Source asset batch has not passed integrity verification")
    batch_manifest = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
    allowed = {record["id"] for record in batch_manifest["assets"] if record["qa"].get("pass") is True}
    names = {row["asset"] for row in spec["placements"]}
    if not names <= allowed:
        raise ValueError(f"Unknown or rejected source assets: {sorted(names - allowed)}")
    stage = factory.new_staging(dest)
    print(f"Level staging: {stage}", flush=True)
    try:
        for file in (HERE / "template").iterdir():
            if file.is_file():
                shutil.copy2(file, stage / file.name)
        (stage / "assets").mkdir()
        (stage / "reports").mkdir()
        for name in names:
            shutil.copy2(batch / "assets" / f"{name}.glb", stage / "assets" / f"{name}.glb")
        provenance = json.loads((batch / "assets" / "provenance.json").read_text(encoding="utf-8"))
        factory.write_json(stage / "assets" / "provenance.json",
                           [p for p in provenance if p["path"] in {n+".glb" for n in names}])
        factory.write_json(stage / "level.json", spec)
        if route_qa:
            sys.path.insert(0, str(HERE))
            from procedural import plan_route
            factory.write_json(stage / "route.json", plan_route(spec))
        Godot = [godot, "--headless", "--path", str(stage)]
        run_stage(Godot + ["--editor", "--import"], stage / "reports" / "import.log")
        run_stage(Godot + ["--script", "res://bake.gd"], stage / "reports" / "bake.log",
                  "STUDIO_WORLD_BAKE_PASS")
        run_stage(Godot + ["--quit-after", "10"], stage / "reports" / "launch.log",
                  "STUDIO_WORLD_READY")
        qa = None
        if route_qa:
            output = run_stage(Godot + ["--fixed-fps", "60", "--script", "res://route_qa.gd"], stage / "reports" / "route-qa.log", "STUDIO_ROUTE_QA_JSON ")
            markers = [line.split(" ",1)[1] for line in output.splitlines() if line.startswith("STUDIO_ROUTE_QA_JSON ")]
            if len(markers) != 1 or json.loads(markers[0]).get("pass") is not True:
                raise ValueError("Physical route QA failed")
            factory.write_json(stage / "reports" / "route-qa.json", json.loads(markers[0]))
        if demo_qa:
            output = run_stage(Godot + ["--script", "res://qa.gd"], stage / "reports" / "qa.log",
                               "STUDIO_WORLD_QA_JSON ")
            markers = [s for s in output.splitlines() if s.startswith("STUDIO_WORLD_QA_JSON ")]
            if len(markers) != 1:
                raise ValueError("Ambiguous QA output")
            qa = json.loads(markers[0].split(" ", 1)[1])
            if qa.get("pass") is not True:
                raise ValueError("Gameplay QA failed")
            factory.write_json(stage / "reports" / "qa.json", qa)
        # Godot regenerates this derived cache on the user's machine.
        cache = stage / ".godot"
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
        factory.write_json(stage / "manifest.json", {
            "schema": 1, "status": "passed", "date": datetime.now(timezone.utc).isoformat(),
            "level": spec["id"], "asset_batch_sha256": factory.hash_file(batch / "manifest.json"),
            "validation": "headless baked scene and launch" + (" + physical route QA" if route_qa else "") + (" + demo gameplay checks" if demo_qa else ""),
            "gameplay_qa": qa, "files": factory.inventory(stage)})
        if factory.verify_package(stage):
            raise ValueError("Generated project integrity check failed")
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(dest)
        stage.rename(dest)
        print(f"WORLD_FACTORY_PASS {dest}")
    except Exception:
        print(f"Level generation failed; diagnostics retained: {stage}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", nargs="?", type=Path)
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--godot", default="godot")
    parser.add_argument("--demo-qa", action="store_true",
                        help="Run training-yard-specific physical traversal and gameplay checks.")
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--route-qa", action="store_true", help="Drive the real player along a clearance-safe route")
    args = parser.parse_args()
    if args.verify:
        errors = factory.verify_package(args.verify.absolute())
        print("; ".join(errors) if errors else "WORLD_INTEGRITY_PASS")
        return int(bool(errors))
    if not all((args.spec, args.assets, args.output)):
        parser.error("Specify level spec, --assets, --output, or --verify.")
    build(args.spec.absolute(), args.assets.absolute(), args.output.absolute(), args.godot, args.demo_qa, args.route_qa)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"World factory: {error}", file=sys.stderr)
        sys.exit(1)
