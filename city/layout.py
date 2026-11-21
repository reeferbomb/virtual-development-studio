"""Generate a seeded city in metres. X and Z span the ground plane."""

import math
import random


ROAD_WIDTH = 12
BUILDING_SETBACK = 9  # Six metres of roadway plus room for the sidewalk.
RANGES = {"seed": (0, 2**31 - 1), "blocks": (3, 8), "block_size": (32, 64),
          "traffic": (0, 24), "civilians": (0, 40)}
DISTRICTS = (
    ("downtown", "Central Business District", "commercial"),
    ("residential", "Garden Quarter", "residential"),
    ("industrial", "Foundry District", "industrial"),
)
BUILDING_PROFILES = {
    "downtown": (("tower", 24, 48), ("midrise", 14, 25)),
    "residential": (("apartment", 9, 17), ("townhouse", 5, 9)),
    "industrial": (("warehouse", 6, 10), ("workshop", 5, 8)),
}


def validate(spec):
    """Return a copy of a valid spec; reject ambiguous JSON types and fields."""
    if not isinstance(spec, dict) or set(spec) != set(RANGES):
        raise ValueError("city spec must contain seed, blocks, block_size, traffic and civilians")
    for field, (low, high) in RANGES.items():
        if type(spec[field]) is not int or not low <= spec[field] <= high:
            raise ValueError(f"{field} must be an integer in {low}..{high}")
    return {field: spec[field] for field in RANGES}


def _road_graph(blocks, size):
    nodes = []
    edges = []
    for iz in range(blocks + 1):
        for ix in range(blocks + 1):
            node = f"n{ix}_{iz}"
            nodes.append({"id": node, "x": ix * size, "z": iz * size})
            if ix < blocks:
                edges.append({"from": node, "to": f"n{ix + 1}_{iz}"})
            if iz < blocks:
                edges.append({"from": node, "to": f"n{ix}_{iz + 1}"})
    return {"nodes": nodes, "edges": edges}


def _lot_ranges(start, length, split):
    if not split:
        return [(start, start + length)]
    middle = start + length // 2
    return [(start, middle - 1), (middle + 1, start + length)]


def _build_block(rng, ix, iz, size, district):
    available = size - 2 * BUILDING_SETBACK
    # A divided lot needs room for two footprints and a passage between them.
    can_split = available >= 23
    chance = 0.28 if district == "industrial" else 0.68
    x_ranges = _lot_ranges(ix * size + BUILDING_SETBACK, available, can_split and rng.random() < chance)
    z_ranges = _lot_ranges(iz * size + BUILDING_SETBACK, available, can_split and rng.random() < chance)
    result = []
    for x0, x1 in x_ranges:
        for z0, z1 in z_ranges:
            width = rng.randint((x1 - x0) * 2 // 3, x1 - x0)
            depth = rng.randint((z1 - z0) * 2 // 3, z1 - z0)
            x = rng.randint(x0, x1 - width) + width / 2
            z = rng.randint(z0, z1 - depth) + depth / 2
            style, low, high = rng.choice(BUILDING_PROFILES[district])
            result.append({
                "id": f"b{ix}_{iz}_{len(result)}", "center": [x, 0, z],
                "size": [width, rng.randint(low, high), depth], "district": district, "style": style,
            })
    return result


def generate(spec):
    """Return a JSON-serializable layout with a full, undirected grid road network."""
    result = validate(spec)
    blocks, size = result["blocks"], result["block_size"]
    # A city-specific random stream keeps procedural model generation reproducible.
    rng = random.Random(f"city:{result['seed']}")
    mid, last = blocks // 2, blocks - 1
    corner_x, corner_z = rng.choice((0, last)), rng.choice((0, last))
    anchors = [(mid, mid), (corner_x, corner_z), (last - corner_x, last - corner_z)]
    zoning, buildings = [], []
    for iz in range(blocks):
        for ix in range(blocks):
            nearest = min(range(len(anchors)),
                          key=lambda i: (ix - anchors[i][0]) ** 2 + (iz - anchors[i][1]) ** 2)
            district, _, zone = DISTRICTS[nearest]
            zoning.append({"block": [ix, iz], "district": district, "zone": zone})
            buildings.extend(_build_block(rng, ix, iz, size, district))
    result.update({
        "road_width": ROAD_WIDTH, "world_size": blocks * size,
        "spawn": [mid * size, 0, mid * size], "roads": _road_graph(blocks, size),
        "districts": [{"id": d, "name": name, "zone": zone} for d, name, zone in DISTRICTS],
        "zoning": zoning, "buildings": buildings,
    })
    return result


def _vector(value, length):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"expected {length} coordinates")
    if any(type(n) not in (int, float) or not math.isfinite(n) for n in value):
        raise ValueError("coordinates must be finite numbers")
    return value


def _validate_roads(roads, blocks, size):
    expected_points = {(x * size, z * size) for x in range(blocks + 1) for z in range(blocks + 1)}
    points = {}
    for node in roads["nodes"]:
        name = node["id"]
        point = tuple(_vector([node["x"], node["z"]], 2))
        if not isinstance(name, str) or not name or name in points or point not in expected_points:
            raise ValueError("invalid or duplicate road node")
        expected_points.remove(point)
        points[name] = point
    if expected_points:
        raise ValueError("missing road intersection")
    links = set()
    for edge in roads["edges"]:
        start, end = edge["from"], edge["to"]
        a, b = points[start], points[end]
        dx, dz = abs(a[0] - b[0]), abs(a[1] - b[1])
        link = frozenset((start, end))
        if (dx, dz) not in ((size, 0), (0, size)) or link in links:
            raise ValueError("invalid or duplicate road edge")
        links.add(link)
    # This is the total number of possible unit grid edges. Uniqueness and
    # adjacency above imply that every road is present and the graph is connected.
    if len(links) != 2 * blocks * (blocks + 1):
        raise ValueError("missing road segment")


def _validate_geometry(layout, blocks, size):
    district_zones = {}
    for district in layout["districts"]:
        district_id, zone = district["id"], district["zone"]
        if not all(isinstance(v, str) and v for v in (district_id, zone, district["name"])):
            raise ValueError("invalid district")
        if district_id in district_zones:
            raise ValueError("duplicate district")
        district_zones[district_id] = zone

    zoning = {}
    for cell in layout["zoning"]:
        block = tuple(_vector(cell["block"], 2))
        if any(type(n) is not int or not 0 <= n < blocks for n in block) or block in zoning:
            raise ValueError("invalid or duplicate zoning block")
        district = cell["district"]
        if district_zones[district] != cell["zone"]:
            raise ValueError("block zoning disagrees with district")
        zoning[block] = district
    if len(zoning) != blocks * blocks or set(zoning.values()) != set(district_zones):
        raise ValueError("incomplete zoning coverage")

    ids, footprints = set(), {}
    for building in layout["buildings"]:
        name = building["id"]
        if not isinstance(name, str) or not name or name in ids:
            raise ValueError("invalid or duplicate building ID")
        ids.add(name)
        x, y, z = _vector(building["center"], 3)
        width, height, depth = _vector(building["size"], 3)
        if y != 0 or min(width, height, depth) <= 0 or not isinstance(building["style"], str) or not building["style"]:
            raise ValueError("invalid building dimensions, base or style")
        ix, iz = math.floor(x / size), math.floor(z / size)
        if (ix, iz) not in zoning or zoning[ix, iz] != building["district"]:
            raise ValueError("building outside its zoned block")
        x0, x1, z0, z1 = x - width / 2, x + width / 2, z - depth / 2, z + depth / 2
        if min(x0 - ix * size, (ix + 1) * size - x1,
               z0 - iz * size, (iz + 1) * size - z1) < BUILDING_SETBACK:
            raise ValueError("building violates road or sidewalk setback")
        nearby = footprints.setdefault((ix, iz), [])
        if any(x0 < b and x1 > a and z0 < d and z1 > c for a, b, c, d in nearby):
            raise ValueError("overlapping buildings")
        nearby.append((x0, x1, z0, z1))
    if not ids:
        raise ValueError("city has no buildings")


def validate_layout(layout):
    """Validate serialized city geometry and references, raising ValueError on error."""
    try:
        spec = validate({k: layout[k] for k in RANGES})
        blocks, size = spec["blocks"], spec["block_size"]
        world = blocks * size
        if layout["world_size"] != world or layout["road_width"] != ROAD_WIDTH:
            raise ValueError("inconsistent city dimensions")
        _validate_roads(layout["roads"], blocks, size)
        _validate_geometry(layout, blocks, size)
        x, y, z = _vector(layout["spawn"], 3)
        if y != 0 or not (0 <= x <= world and 0 <= z <= world):
            raise ValueError("spawn outside city")
        distances = [abs(v - round(v / size) * size) for v in (x, z)]
        if min(distances) > ROAD_WIDTH / 2 or max(distances) > ROAD_WIDTH:
            raise ValueError("spawn must be on a road near an intersection")
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError(f"invalid city layout: {exc}") from exc
    return True
