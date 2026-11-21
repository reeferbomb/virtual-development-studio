import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "world" / "build.py"
spec = importlib.util.spec_from_file_location("world_build", MODULE)
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


def layout():
    return {
        "id": "sample", "terrain": {"width": 32, "depth": 24, "segments": 32,
                                     "flat_radius": 10, "amplitude": 0.7},
        "spawn": [-7, 0, 0], "goal": [7, 0, 0], "blocks": [],
        "placements": [{"id": "crate_1", "asset": "supply_crate", "position": [0, 0, 5],
                         "collider_size": [1, 1, 1]}],
    }


class LevelSpecTests(unittest.TestCase):
    def test_valid_design_is_normalized(self):
        spec = world.validate(layout())
        self.assertEqual(spec["placements"][0]["yaw_deg"], 0)

    def test_rejects_unsafe_asset_identifier(self):
        data = layout()
        data["placements"][0]["asset"] = "../secret"
        with self.assertRaises(ValueError):
            world.validate(data)

    def test_rejects_spawn_inside_wall(self):
        data = layout()
        data["blocks"] = [{"id": "wall", "position": [-7, 1, 0], "size": [2, 2, 2]}]
        with self.assertRaises(ValueError):
            world.validate(data)

    def test_rejects_goal_beyond_flat_spawn_area(self):
        data = layout()
        data["goal"] = [15, 0, 0]
        with self.assertRaises(ValueError):
            world.validate(data)

    def test_rejects_bad_resolution(self):
        data = layout()
        data["terrain"]["segments"] = 10000
        with self.assertRaises(ValueError):
            world.validate(data)

    def test_rejects_duplicate_node_names(self):
        data = layout()
        data["blocks"] = [{"id": "crate_1", "position": [0, 1, 4], "size": [2, 2, 2]}]
        with self.assertRaises(ValueError):
            world.validate(data)


if __name__ == "__main__":
    unittest.main()
