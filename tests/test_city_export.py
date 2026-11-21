import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from city.export import audit_glb, export_city, placements, unreal_placements


def layout():
    return {"seed": 42, "blocks": 2, "block_size": 32, "road_width": 12, "world_size": 64,
            "buildings": [{"id": "shop", "center": [5, 0, -10], "size": [8, 12, 6],
                           "district": "market", "style": "brick"}],
            "roads": {"nodes": [{"id": "a", "x": -16, "z": 0}, {"id": "b", "x": 16, "z": 0},
                                {"id": "c", "x": 8, "z": 24}],
                      "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]}}


class CityExportTests(unittest.TestCase):
    def test_axis_conversion_ground_pivot_road_extent(self):
        objects = placements(layout())
        building, road, diagonal = unreal_placements(objects)["actors"][:3]
        self.assertEqual(building["location_cm"], [1000, 500, 600])
        self.assertEqual(building["size_cm"], [600, 800, 1200])
        self.assertEqual(road["rotation_deg"]["yaw"], -90)
        self.assertEqual(road["size_cm"], [2000, 1200, 12.5])
        self.assertAlmostEqual(diagonal["rotation_deg"]["yaw"], 18.4349488, places=6)

    def test_invalid_layout_and_existing_output(self):
        for mutate in (
            lambda data: data["buildings"][0]["size"].__setitem__(0, 0),
            lambda data: data["roads"]["edges"][0].update({"to": "missing"}),
            lambda data: data["roads"]["edges"].append({"from": "b", "to": "a"}),
            lambda data: data["roads"]["nodes"].append({"id": "a", "x": 0, "z": 0}),
        ):
            data = layout()
            mutate(data)
            with self.assertRaises(ValueError):
                placements(data)
        with tempfile.TemporaryDirectory() as work:
            target = Path(work) / "out"
            target.mkdir()
            sentinel = target / "keep"
            sentinel.write_text("original")
            with self.assertRaises(FileExistsError):
                export_city(Path(work) / "missing-input", target)
            self.assertEqual(sentinel.read_text(), "original")

    def test_failed_worker_cleans_staging(self):
        with tempfile.TemporaryDirectory() as work:
            src = Path(work) / "layout.json"
            src.write_text(json.dumps(layout()))
            with self.assertRaises((FileNotFoundError, RuntimeError)):
                export_city(src, Path(work) / "out", shutil.which("false") or "missing-blender")
            self.assertEqual(list(Path(work).iterdir()), [src])

    @unittest.skipUnless(shutil.which("blender"), "Native Blender integration requires Blender")
    def test_blender_glb_and_reopened_project(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            src, out = root / "layout.json", root / "artifacts"
            src.write_text(json.dumps(layout()))
            report = export_city(src, out)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(report["triangles"], 72)
            self.assertEqual(report["mesh_instances"], 6)
            self.assertEqual(report, json.loads((out / "mesh-audit.json").read_text()))
            self.assertEqual(len(json.loads((out / "unreal-placements.json").read_text())["actors"]), 6)
            incorrect = copy.deepcopy(manifest["objects"])
            incorrect[0]["size_m"][0] += 1
            with self.assertRaisesRegex(ValueError, "dimensions"):
                audit_glb(out / "city.glb", incorrect)
            incorrect[0] = dict(manifest["objects"][0], position_m=[0, 0, 0])
            with self.assertRaisesRegex(ValueError, "transform"):
                audit_glb(out / "city.glb", incorrect)
            code = ("import bpy; objects = bpy.context.scene.objects; "
                    "assert len(objects) == 6; b = objects['Building_00000_shop']; "
                    "assert tuple(b.location) == (5, 10, 6) and tuple(b.dimensions) == (8, 6, 12); "
                    "assert b['district'] == 'market' and b.type == 'MESH'; print('CITY_BLEND_REOPENED')")
            proc = subprocess.run([shutil.which("blender"), "--background", "--threads", "1", str(out / "city.blend"),
                                   "--python-exit-code", "1", "--python-expr", code],
                                  capture_output=True, text=True, timeout=90)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("CITY_BLEND_REOPENED", proc.stdout)

    @unittest.skipUnless(shutil.which("blender") and shutil.which("godot"),
                         "Cross-engine GLB test requires Blender and Godot")
    def test_godot_reads_exported_geometry(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            src = root / "layout.json"
            src.write_text(json.dumps(layout()))
            export_city(src, root / "assets")
            (root / "project.godot").write_text('config_version=5\n[application]\nconfig/name="GLB Audit"\n')
            script = root / "check.gd"
            script.write_text("""extends SceneTree

func _initialize():
    var doc := GLTFDocument.new()
    var state := GLTFState.new()
    if doc.append_from_file("res://assets/city.glb", state) != OK:
        quit(1)
        return
    var scene := doc.generate_scene(state)
    var meshes := scene.find_children("*", "MeshInstance3D", true, false)
    var building := scene.find_child("Building_00000_shop", true, false) as MeshInstance3D
    var valid := meshes.size() == 6 and building != null
    if valid:
        valid = building.position.is_equal_approx(Vector3(5, 6, -10))
        valid = valid and building.get_aabb().size.is_equal_approx(Vector3(8, 12, 6))
    scene.free()
    if valid:
        print("CITY_GLB_GODOT_PASS")
    quit(0 if valid else 1)
""")
            proc = subprocess.run([shutil.which("godot"), "--headless", "--path", str(root),
                                   "--script", str(script)], capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("CITY_GLB_GODOT_PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
