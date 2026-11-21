"""Export a generated city layout as editable Blender geometry and a portable GLB."""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _vector(value, name, positive=False):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{name} must have three components")
    return [_number(component, name, positive) for component in value]


def _id(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or value == "":
        raise ValueError("Expected a string or integer layout ID")
    return value


def _name(kind, index, identifier):
    # Preserve a recognizable suffix while keeping names unique within Blender's byte limit.
    suffix = "".join(c if c.isascii() and (c.isalnum() or c in "_-") else "_" for c in str(identifier))
    return f"{kind}_{index:05}_{suffix[:35]}"


def placements(layout):
    width = _number(layout["road_width"], "road_width", positive=True)
    items = []
    seen = set()
    for i, building in enumerate(layout["buildings"]):
        ident = _id(building["id"])
        if ident in seen:
            raise ValueError(f"Duplicate building ID {ident}")
        seen.add(ident)
        x, ground, z = _vector(building["center"], "building.center")
        w, h, d = _vector(building["size"], "building.size", positive=True)
        items.append({"name": _name("Building", i, ident), "kind": "building", "source_id": ident,
                      "position_m": [x, ground + h / 2, z], "size_m": [w, h, d], "yaw_deg": 0,
                      "district": building["district"], "style": building["style"]})

    nodes = {}
    for node in layout["roads"]["nodes"]:
        ident = _id(node["id"])
        if ident in nodes:
            raise ValueError(f"Duplicate road node {ident}")
        nodes[ident] = (_number(node["x"], "node.x"), _number(node["z"], "node.z"))
    seen.clear()
    for i, edge in enumerate(layout["roads"]["edges"]):
        start, end = _id(edge["from"]), _id(edge["to"])
        if start not in nodes or end not in nodes:
            raise ValueError(f"Unknown road endpoint {start}, {end}")
        pair = frozenset((start, end))
        if pair in seen:
            raise ValueError(f"Duplicate road edge {start}, {end}")
        seen.add(pair)
        x1, z1 = nodes[start]
        x2, z2 = nodes[end]
        dx, dz = x2 - x1, z2 - z1
        length = math.hypot(dx, dz)
        if not length:
            raise ValueError(f"Road {start}, {end} has zero length")
        # Axis-aligned block roads meet a full-width square junction without overlapping it.
        trim = width if (dx == 0 or dz == 0) and length > width else 0
        items.append({"name": _name("Road", i, f"{start}_{end}"), "kind": "road",
                      "source_id": [start, end], "position_m": [(x1 + x2) / 2, -0.0625, (z1 + z2) / 2],
                      "size_m": [width, 0.125, length - trim],
                      "yaw_deg": math.degrees(math.atan2(dx, dz))})
    for i, (ident, (x, z)) in enumerate(nodes.items()):
        # A small height offset also keeps diagonal roads and short segments free of coincident top faces.
        items.append({"name": _name("Junction", i, ident), "kind": "junction", "source_id": ident,
                      "position_m": [x, -0.06, z], "size_m": [width, 0.13, width], "yaw_deg": 0})
    if not items:
        raise ValueError("No city geometry to export")
    return items


def unreal_placements(items):
    actors = []
    for item in items:
        x, y, z = item["position_m"]
        w, h, d = item["size_m"]
        actors.append({"name": item["name"], "kind": item["kind"], "source_id": item["source_id"],
                       "location_cm": [-100 * z, 100 * x, 100 * y],
                       "size_cm": [100 * d, 100 * w, 100 * h],
                       "rotation_deg": {"pitch": 0, "yaw": -item["yaw_deg"], "roll": 0}})
    return {"schema": 1, "coordinate_system": "Unreal left-handed, +X forward, +Y right, +Z up",
            "units": "centimeters", "pivot": "geometric center",
            "placement_usage": "Use these transforms and full local sizes to reconstruct centered unit boxes. "
                               "The GLB scene already contains its own placements.",
            "conversion": "location = (-source.z, source.x, source.y) * 100; yaw = -source yaw",
            "verification": "Placement conversion checked in Python; Unreal Editor import requires a local check.",
            "actors": actors}


def _glb_chunks(path):
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise ValueError("Incomplete GLB header")
        magic, version, total = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2 or total != path.stat().st_size:
            raise ValueError("Invalid GLB header")
        parts = []
        for kind in (b"JSON", b"BIN\0"):
            header = stream.read(8)
            if len(header) != 8:
                raise ValueError("Missing GLB chunk")
            size, tag = struct.unpack("<I4s", header)
            data = stream.read(size)
            if kind != tag or len(data) != size or size % 4:
                raise ValueError("Invalid GLB chunk")
            parts.append(data)
        if stream.read(1):
            raise ValueError("Unexpected trailing GLB data")
    return json.loads(parts[0]), parts[1]


def _accessor(doc, binary, index, expected):
    accessor = doc["accessors"][index]
    view = doc["bufferViews"][accessor["bufferView"]]
    if accessor["type"] != expected or view["buffer"] != 0 or "sparse" in accessor:
        raise ValueError("Unexpected GLB accessor layout")
    component = accessor["componentType"]
    if expected == "VEC3" and component != 5126:
        raise ValueError("GLB positions must use floating point")
    if expected == "SCALAR" and component not in (5121, 5123, 5125):
        raise ValueError("Invalid GLB triangle index format")
    form = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[component]
    word = struct.Struct("<" + form * (3 if expected == "VEC3" else 1))
    start = view.get("byteOffset", 0)
    end = start + view["byteLength"]
    offset = accessor.get("byteOffset", 0) + start
    stride = view.get("byteStride", word.size)
    count = accessor["count"]
    if count <= 0 or stride < word.size or start < 0 or offset < start or end > len(binary) or (
            offset + (count - 1) * stride + word.size > end):
        raise ValueError("GLB accessor exceeds its bounds")
    return [word.unpack_from(binary, offset + n * stride) for n in range(count)]


def _close(actual, expected):
    return len(actual) == len(expected) and all(
        math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-5) for a, b in zip(actual, expected))


def _check_box_surface(positions, name):
    """Weld duplicated face corners before checking geometry and edge winding."""
    edges = Counter()
    for i in range(0, len(positions), 3):
        a, b, c = positions[i:i + 3]
        if len({a, b, c}) != 3:
            raise ValueError(f"Degenerate GLB triangle for {name}")
        edges.update(((a, b), (b, c), (c, a)))
    if len(set(positions)) != 8 or len(edges) != 36 or any(
            count != 1 or edges[(end, start)] != 1 for (start, end), count in edges.items()):
        raise ValueError(f"Expected a closed and consistently wound box for {name}")


def audit_glb(path, items):
    """Check the active scene, object transforms, dimensions and triangle indices from the binary."""
    path = Path(path)
    doc, binary = _glb_chunks(path)
    if len(doc["buffers"]) != 1 or "uri" in doc["buffers"][0] or doc.get("images"):
        raise ValueError("Expected a self-contained untextured GLB")
    scene = doc["scenes"][doc.get("scene", 0)]
    if sorted(scene["nodes"]) != list(range(len(doc["nodes"]))):
        raise ValueError("Expected all mesh placements at the scene root")
    nodes = {node["name"]: node for node in doc["nodes"]}
    if len(nodes) != len(doc["nodes"]) or set(nodes) != {item["name"] for item in items}:
        raise ValueError("GLB placement names differ from the manifest")
    meshes = {}
    triangles = 0
    for item in items:
        name = item["name"]
        node = nodes[name]
        half = math.radians(item["yaw_deg"]) / 2
        rotation = [0, math.sin(half), 0, math.cos(half)]
        actual = node.get("rotation", [0, 0, 0, 1])
        if (node.get("children") or "matrix" in node or not _close(node.get("scale", [1, 1, 1]), [1, 1, 1])
                or not _close(node.get("translation", [0, 0, 0]), item["position_m"])
                or not (_close(actual, rotation) or _close(actual, [-v for v in rotation]))):
            raise ValueError(f"GLB transform mismatch for {name}")
        mesh_index = node["mesh"]
        if mesh_index not in meshes:
            positions = []
            faces = 0
            for primitive in doc["meshes"][mesh_index]["primitives"]:
                if primitive.get("mode", 4) != 4:
                    raise ValueError("Expected triangles")
                vertices = _accessor(doc, binary, primitive["attributes"]["POSITION"], "VEC3")
                indices = [row[0] for row in _accessor(doc, binary, primitive["indices"], "SCALAR")]
                if len(indices) % 3 or max(indices) >= len(vertices):
                    raise ValueError("Invalid GLB triangle indices")
                positions.extend(vertices[index] for index in indices)
                faces += len(indices) // 3
            if faces != 12 or not all(math.isfinite(c) for v in positions for c in v):
                raise ValueError(f"Invalid box geometry for {name}")
            _check_box_surface(positions, name)
            meshes[mesh_index] = ([min(axis) for axis in zip(*positions)],
                                  [max(axis) for axis in zip(*positions)], faces)
        low, high, faces = meshes[mesh_index]
        if not _close(low, [-s / 2 for s in item["size_m"]]) or not _close(high, [s / 2 for s in item["size_m"]]):
            raise ValueError(f"GLB dimensions or pivot mismatch for {name}")
        triangles += faces
    return {"passed": True, "format": "glTF 2.0 binary", "mesh_instances": len(items),
            "unique_meshes": len(meshes), "triangles": triangles, "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "checks": ["scene membership", "unique object names", "placement transforms",
                       "triangle index bounds", "closed mesh topology and winding",
                       "dimensions from binary vertices", "centered pivots"]}


def export_city(layout_path, output_dir, blender="blender"):
    layout_path = Path(layout_path)
    output = Path(output_dir).absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"Choose a new output directory: {output}")
    raw = layout_path.read_bytes()
    layout = json.loads(raw)
    items = placements(layout)
    executable = shutil.which(str(blender))
    if not executable:
        raise FileNotFoundError(f"Blender executable unavailable: {blender}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".city-export-", dir=output.parent) as tmp:
        stage = Path(tmp) / "artifacts"
        stage.mkdir()
        manifest = {"schema": 1, "layout_sha256": hashlib.sha256(raw).hexdigest(),
                    "layout": {field: layout[field] for field in ("seed", "blocks", "block_size", "road_width", "world_size")},
                    "coordinates": "Right-handed meters; X right, Y up, -Z forward; yaw about +Y.",
                    "geometry": "Procedural solid box meshes; local sizes are full extents and positions are centered pivots.",
                    "source": "Original procedural geometry and materials generated from the supplied city layout.",
                    "artifacts": {"blend": "city.blend", "glb": "city.glb", "unreal": "unreal-placements.json",
                                  "audit": "mesh-audit.json"}, "objects": items}
        write_json(stage / "manifest.json", manifest)
        write_json(stage / "unreal-placements.json", unreal_placements(items))
        script = Path(__file__).with_name("blender_export.py").resolve()
        proc = subprocess.run([executable, "--background", "--factory-startup", "--threads", "1",
                               "--python-exit-code", "1", "--python", str(script), "--", str(stage)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        if proc.returncode:
            raise RuntimeError(f"Blender export failed ({proc.returncode})\n{proc.stdout[-3500:]}")
        if not (stage / "city.blend").is_file() or not (stage / "city.blend").stat().st_size:
            raise ValueError("Blender did not create its native project")
        audit = audit_glb(stage / "city.glb", items)
        write_json(stage / "mesh-audit.json", audit)
        if os.path.lexists(output):
            raise FileExistsError(f"Output appeared during export: {output}")
        stage.rename(output)
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--blender", default="blender")
    args = parser.parse_args()
    try:
        print(json.dumps(export_city(args.layout, args.out, args.blender), indent=2))
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"City export failed: {exc}\n")


if __name__ == "__main__":
    main()
