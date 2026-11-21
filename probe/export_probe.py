import bpy
import sys

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_cube_add(size=1.0)
bpy.context.object.name = "StudioProbe"
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB")
print("STUDIO_EXPORT_PASS")
