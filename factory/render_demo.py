"""CPU-render a review image of the four DEMO exports. Blender-side script."""
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def main():
    cut = sys.argv.index("--")
    asset_dir, output = Path(sys.argv[cut + 1]), Path(sys.argv[cut + 2])
    if output.exists():
        raise FileExistsError(output)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for name, offset in (
        ("supply_crate", (-2.5, -.4, 0)),
        ("industrial_barrel", (-.8, -.7, 0)),
        ("road_barricade", (1.0, -.2, 0)),
        ("training_mannequin", (2.8, .4, 0)),
    ):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(asset_dir / (name + ".glb")))
        created = set(bpy.data.objects) - before
        for obj in created:
            if obj.parent not in created:
                obj.location += Vector(offset)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -.018))
    ground = bpy.data.materials.new("Neutral studio floor")
    ground.diffuse_color = (.17, .20, .23, 1)
    bpy.context.object.data.materials.append(ground)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 12
    scene.cycles.use_denoising = True
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    bpy.ops.object.camera_add(location=(4.2, -12, 5.7))
    camera = bpy.context.object
    point_at(camera, (0, 0, .70))
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 8.1
    scene.camera = camera
    for pos, power, size in (((-4, -4, 6), 1300, 6), ((4, -2, 4), 800, 4), ((0, 5, 5), 1000, 4)):
        bpy.ops.object.light_add(type="AREA", location=pos)
        light = bpy.context.object
        light.data.energy, light.data.shape, light.data.size = power, "DISK", size
        point_at(light, (0, 0, .5))
    scene.world.color = (.16, .16, .16)
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
