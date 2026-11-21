"""Run after generating a city: blender52 -b --python-exit-code 1 --python test_city.py -- OUTPUT_DIR."""
import json
import sys
from pathlib import Path
import bpy

out = Path(sys.argv[sys.argv.index("--") + 1])
assert (out / "city.glb").read_bytes()[:4] == b"glTF"
info = json.loads((out / "city.json").read_text())
bpy.ops.wm.open_mainfile(filepath=str(out / "city.blend"))
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
assert len(meshes) == info["mesh_count"]
assert len([o for o in meshes if o.name.startswith("Facade")]) == 6
assert sum(len(p.vertices) - 2 for o in meshes for p in o.data.polygons) == info["triangles"]
assert "Window amber" in info["materials"]
for obj in meshes:
    if obj.name.startswith(("Facade", "Lantern", "Sidewalk")):
        xs = [v.co.x for v in obj.data.vertices]
        assert max(xs) <= -3 or min(xs) >= 3, obj.name
print("City validation passed", info["triangles"])
