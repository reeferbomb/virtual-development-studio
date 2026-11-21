import itertools
import json
import unittest

from city.layout import generate, validate, validate_layout


SPEC = {"seed": 57, "blocks": 5, "block_size": 48, "traffic": 8, "civilians": 12}


class CityLayoutTests(unittest.TestCase):
    def test_spec_requires_five_integer_fields(self):
        self.assertEqual(validate(SPEC), SPEC)
        self.assertEqual(validate(dict(SPEC, seed=2**31 - 1))["seed"], 2**31 - 1)
        for field, invalid in {"seed": (True, 5.0, -1, 2**31), "blocks": (2, 9), "block_size": (31, 65),
                               "traffic": (-1, 25), "civilians": (-1, 41)}.items():
            for value in invalid:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate(dict(SPEC, **{field: value}))
        for value in (None, [], {}, dict(SPEC, lanes=2)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate(value)

    def test_json_round_trip_and_seed_reproducibility(self):
        first = generate(SPEC)
        generate(dict(SPEC, seed=100))
        second = generate(dict(reversed(list(SPEC.items()))))
        self.assertEqual(json.dumps(first), json.dumps(second))
        self.assertTrue(validate_layout(json.loads(json.dumps(first))))
        self.assertNotEqual(first["buildings"], generate(dict(SPEC, seed=SPEC["seed"] + 1))["buildings"])
        changed_counts = generate(dict(SPEC, traffic=0, civilians=40))
        self.assertEqual(first["buildings"], changed_counts["buildings"])

    def test_grid_is_connected_and_spans_the_city(self):
        for blocks in range(3, 9):
            size = 47
            city = generate(dict(SPEC, blocks=blocks, block_size=size))
            graph = city["roads"]
            points = {n["id"]: (n["x"], n["z"]) for n in graph["nodes"]}
            axis = range(0, city["world_size"] + 1, size)
            self.assertEqual(set(points.values()), set(itertools.product(axis, repeat=2)))
            neighbors = {node: set() for node in points}
            for edge in graph["edges"]:
                a, b = edge["from"], edge["to"]
                ax, az = points[a]
                bx, bz = points[b]
                self.assertIn((abs(ax-bx), abs(az-bz)), ((0, size), (size, 0)))
                self.assertNotIn(b, neighbors[a])
                neighbors[a].add(b)
                neighbors[b].add(a)
            self.assertEqual(len(graph["edges"]), 2 * blocks * (blocks + 1))
            seen, pending = set(), [next(iter(neighbors))]
            while pending:
                node = pending.pop()
                if node not in seen:
                    seen.add(node)
                    pending.extend(neighbors[node] - seen)
            self.assertEqual(seen, set(points))
            x, y, z = city["spawn"]
            self.assertEqual(y, 0)
            self.assertIn((x, z), points.values())

    def test_zoning_bounds_road_clearance_and_nonoverlap(self):
        for seed, size, blocks in itertools.product((0, 53, 771, 2**31 - 1), (32, 47, 64), (3, 8)):
            with self.subTest(seed=seed, size=size, blocks=blocks):
                city = generate(dict(SPEC, seed=seed, block_size=size, blocks=blocks))
                self.assertTrue(validate_layout(city))
                self.assertEqual(city["world_size"], size * blocks)
                self.assertEqual(city["road_width"], 12)
                zoning = {tuple(cell["block"]): cell["district"] for cell in city["zoning"]}
                self.assertEqual(set(zoning), set(itertools.product(range(blocks), repeat=2)))
                self.assertEqual(set(zoning.values()), {"downtown", "residential", "industrial"})
                footprints = []
                for building in city["buildings"]:
                    x, y, z = building["center"]
                    w, h, d = building["size"]
                    self.assertEqual(y, 0)
                    self.assertGreater(min(w, h, d), 0)
                    ix, iz = int(x // size), int(z // size)
                    self.assertEqual(building["district"], zoning[ix, iz])
                    x0, x1, z0, z1 = x - w / 2, x + w / 2, z - d / 2, z + d / 2
                    self.assertGreaterEqual(x0, ix * size + 9)
                    self.assertLessEqual(x1, (ix + 1) * size - 9)
                    self.assertGreaterEqual(z0, iz * size + 9)
                    self.assertLessEqual(z1, (iz + 1) * size - 9)
                    for a, b, c, e in footprints:
                        self.assertTrue(x1 <= a or x0 >= b or z1 <= c or z0 >= e)
                    footprints.append((x0, x1, z0, z1))

    def test_validator_rejects_breaks_in_geometry_or_references(self):
        city = generate(SPEC)
        city["buildings"].append(dict(city["buildings"][0], id="overlap"))
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_layout(city)
        city = generate(SPEC)
        city["buildings"][0]["center"][0] = 7
        with self.assertRaisesRegex(ValueError, "setback"):
            validate_layout(city)
        city = generate(SPEC)
        city["roads"]["edges"].pop()
        with self.assertRaisesRegex(ValueError, "missing road segment"):
            validate_layout(city)
        city = generate(SPEC)
        city["zoning"][0]["zone"] = "incorrect"
        with self.assertRaisesRegex(ValueError, "zoning"):
            validate_layout(city)
        for spawn in ([24, 0, 24], [-1, 0, 0], [0, float("nan"), 0]):
            city = generate(SPEC)
            city["spawn"] = spawn
            with self.assertRaises(ValueError):
                validate_layout(city)


if __name__ == "__main__":
    unittest.main()
