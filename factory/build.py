"""Build original procedural assets into a new, evidence-backed batch."""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be between {low} and {high}.")
    return float(value)


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer between {low} and {high}.")
    return value


def validate_spec(spec):
    if not isinstance(spec, dict) or not isinstance(spec.get("assets"), list) or not 1 <= len(spec["assets"]) <= 32:
        raise ValueError("Supply an assets list containing 1–32 records.")
    result, seen = [], set()
    for record in spec["assets"]:
        if not isinstance(record, dict):
            raise ValueError("Each asset must be an object.")
        identifier = record.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", identifier) or identifier in seen:
            raise ValueError("Asset IDs must be unique lowercase safe names.")
        seen.add(identifier)
        kind = record.get("kind")
        if kind not in ("prop", "character"):
            raise ValueError("Supported kinds: prop, character.")
        color = record.get("color", [0.36, 0.48, 0.58])
        if not isinstance(color, list) or len(color) != 3:
            raise ValueError("Color must contain three RGB numbers.")
        asset = {
            "id": identifier, "kind": kind,
            "color": [number(v, 0, 1, "Color") for v in color],
            "max_triangles": integer(record.get("max_triangles", 10000), 1, 100000, "Triangle budget"),
            "max_materials": integer(record.get("max_materials", 8), 1, 32, "Material budget"),
            "max_file_bytes": integer(record.get("max_file_bytes", 8 * 1024 * 1024), 1, 128 * 1024 * 1024, "File budget"),
        }
        if kind == "prop":
            variant = record.get("variant")
            if variant not in ("crate", "barrel", "barricade"):
                raise ValueError("Supported props: crate, barrel, barricade.")
            asset["variant"] = variant
            asset["size_m"] = number(record.get("size_m", 1.0), 0.1, 10, "Prop scale")
        else:
            asset["height_m"] = number(record.get("height_m", 1.7), 0.5, 3.0, "Character height")
        result.append(asset)
    return result


def new_staging(dest):
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"Refusing to overwrite {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=dest.name + ".staging-", dir=dest.parent))


def hash_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(root):
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Unexpected symlink: {path}")
        if path.is_file() and path != root / "manifest.json":
            files.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                          "sha256": hash_file(path)})
    return files


def verify_package(root):
    try:
        if root.is_symlink() or (root / "manifest.json").is_symlink():
            return ["Unexpected symlink"]
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema") != 1 or manifest.get("status") != "passed":
            return ["Batch is not a passed schema-1 package."]
        if manifest.get("files") != inventory(root):
            return ["Inventory or file hashes differ from manifest."]
        return []
    except (ValueError, OSError, AttributeError) as exc:
        return [str(exc)]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def invoke(args, log, timeout=90):
    with log.open("wb") as stream:
        result = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{Path(args[0]).name} exited {result.returncode}. See {log}")


def validate_glb(path):
    with path.open("rb") as stream:
        header = stream.read(12)
    if len(header) != 12:
        raise ValueError("GLB header is incomplete")
    magic, version, size = struct.unpack("<4sII", header)
    if magic != b"glTF" or version != 2 or size != path.stat().st_size:
        raise ValueError("Invalid GLB header or length")


def build(spec_path, dest, blender, godot):
    if not shutil.which(blender) or not shutil.which(godot):
        raise ValueError("Blender and Godot executables must be available.")
    assets = validate_spec(json.loads(spec_path.read_text(encoding="utf-8")))
    stage = new_staging(dest)
    print(f"Staging batch: {stage}", flush=True)
    (stage / "assets").mkdir()
    (stage / "reports").mkdir()
    records, provenance = [], []
    try:
        write_json(stage / "spec.json", {"assets": assets})
        for asset in assets:
            ident = asset["id"]
            target = stage / "assets"
            reports = stage / "reports"
            print(f"Building {ident}", flush=True)
            invoke([blender, "-b", "--factory-startup", "--python-exit-code", "1",
                    "--python", str(HERE / "generate.py"), "--", json.dumps(asset), str(target)],
                   reports / f"{ident}.blender.log", timeout=150)
            glb, blend = target / f"{ident}.glb", target / f"{ident}.blend"
            validate_glb(glb)
            if not blend.is_file() or not blend.stat().st_size:
                raise ValueError("Editable Blender file was not generated.")
            for path in (glb, blend):
                if path.stat().st_size > asset["max_file_bytes"]:
                    raise ValueError(f"{path.name} exceeds the file budget.")
                provenance.append({"path": path.name, "source": "Original studio procedural recipe: " + ident,
                                   "license": "Original generated studio test asset; no external inputs",
                                   "attribution": "No external attribution"})
            with tempfile.TemporaryDirectory(prefix="studio-godot-") as tmp:
                root = Path(tmp)
                for fixture in ("project.godot", "check_asset.gd"):
                    shutil.copy2(HERE / "godot" / fixture, root / fixture)
                shutil.copy2(glb, root / "asset.glb")
                invoke([godot, "--headless", "--path", str(root), "--editor", "--import"],
                       reports / f"{ident}.import.log")
                qa_log = reports / f"{ident}.qa.log"
                invoke([godot, "--headless", "--path", str(root), "--script", "res://check_asset.gd", "--",
                        "--kind", asset["kind"], "--max-triangles", str(asset["max_triangles"]),
                        "--max-materials", str(asset["max_materials"])], qa_log)
                lines = [line for line in qa_log.read_text(encoding="utf-8").splitlines()
                         if line.startswith("STUDIO_ASSET_QA_JSON ")]
                if len(lines) != 1:
                    raise ValueError(f"Missing or ambiguous QA evidence: {qa_log}")
                qa = json.loads(lines[0].split(" ", 1)[1])
                if qa.get("pass") is not True:
                    raise ValueError(f"Godot asset validation failed: {qa}")
                write_json(reports / f"{ident}.qa.json", qa)
                records.append({"id": ident, "kind": asset["kind"], "qa": qa})
        write_json(stage / "assets" / "provenance.json", provenance)
        invoke([sys.executable, str(HERE.parent / "asset_audit.py"), str(stage / "assets")],
               stage / "reports" / "asset_audit.json")
        manifest = {"schema": 1, "status": "passed", "date": datetime.now(timezone.utc).isoformat(),
                    "assets": records, "validation": "headless Godot, not visual/device acceptance",
                    "files": inventory(stage)}
        write_json(stage / "manifest.json", manifest)
        errors = verify_package(stage)
        if errors:
            raise ValueError("; ".join(errors))
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(f"Destination appeared during build: {dest}")
        stage.rename(dest)
        print(f"FACTORY_PASS: {len(records)} assets; {dest}", flush=True)
    except Exception:
        print(f"Batch failed. Diagnostic staging retained: {stage}", file=sys.stderr)
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("spec", nargs="?", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--blender", default=os.environ.get("STUDIO_BLENDER", "blender52"))
    p.add_argument("--godot", default=os.environ.get("STUDIO_GODOT", "godot"))
    p.add_argument("--verify", type=Path)
    args = p.parse_args()
    if args.verify:
        errors = verify_package(args.verify.absolute())
        print("; ".join(errors) if errors else "PACKAGE_INTEGRITY_PASS")
        return int(bool(errors))
    if not args.spec or not args.output:
        p.error("Specify a JSON spec and --output, or --verify PACKAGE.")
    build(args.spec.absolute(), args.output.absolute(), args.blender, args.godot)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"Factory: {exc}", file=sys.stderr)
        sys.exit(1)
