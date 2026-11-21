"""Blender-side entry point; run only in Blender."""
import json
import sys
from pathlib import Path
import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "recipes"))

def main():
    cut = sys.argv.index("--")
    spec = json.loads(sys.argv[cut + 1])
    out = Path(sys.argv[cut + 2])
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    if spec["kind"] == "prop":
        from prop import create
    else:
        from character import create
    create(spec)
    if not any(obj.type == "MESH" for obj in bpy.context.scene.objects):
        raise RuntimeError("Recipe did not create a mesh")
    bpy.ops.wm.save_as_mainfile(filepath=str(out / (spec["id"] + ".blend")))
    bpy.ops.export_scene.gltf(filepath=str(out / (spec["id"] + ".glb")),
                              export_format="GLB", export_animations=True,
                              export_apply=(spec["kind"] == "prop"))
    print("FACTORY_EXPORT_PASS", spec["id"])

if __name__ == "__main__":
    main()
