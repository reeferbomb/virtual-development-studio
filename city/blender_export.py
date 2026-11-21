"""Blender background worker invoked by city/export.py."""
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy


def material_for(item, materials):
    if item["kind"] == "building":
        key = "Building " + str(item["district"]) + " " + str(item["style"])
    else:
        key = "Asphalt"
    if key in materials:
        return materials[key]
    stone = [(0.39, 0.46, 0.49), (0.55, 0.39, 0.31), (0.45, 0.48, 0.43),
             (0.29, 0.40, 0.47), (0.55, 0.52, 0.44), (0.42, 0.44, 0.50)]
    color = stone[hashlib.sha256(key.encode()).digest()[0] % len(stone)] if key != "Asphalt" else (0.075, 0.085, 0.09)
    mat = bpy.data.materials.new(key)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    surface = mat.node_tree.nodes.get("Principled BSDF")
    surface.inputs["Base Color"].default_value = (*color, 1)
    surface.inputs["Roughness"].default_value = 0.87
    materials[key] = mat
    return mat


def main(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "Procedural City"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    collections = {}
    for kind in ("building", "road", "junction"):
        collection = bpy.data.collections.new(kind.title() + "s")
        scene.collection.children.link(collection)
        collections[kind] = collection
    meshes = {}
    materials = {}
    # Eight corners and six outward-facing quads in Blender's right-handed Z-up frame.
    corners = [(-1,-1,-1), (1,-1,-1), (1,1,-1), (-1,1,-1),
               (-1,-1,1), (1,-1,1), (1,1,1), (-1,1,1)]
    faces = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
    for item in manifest["objects"]:
        name = item["name"]
        w, h, d = item["size_m"]
        material = material_for(item, materials)
        key = (w, h, d, material.name)
        if key not in meshes:
            mesh = bpy.data.meshes.new(name + "_Mesh")
            vertices = [(a*w/2, b*d/2, c*h/2) for a, b, c in corners]
            mesh.from_pydata(vertices, [], faces)
            mesh.materials.append(material)
            mesh.update()
            meshes[key] = mesh
        obj = bpy.data.objects.new(name, meshes[key])
        collections[item["kind"]].objects.link(obj)
        x, y, z = item["position_m"]
        obj.location = (x, -z, y)
        obj.rotation_euler[2] = math.radians(item["yaw_deg"])
        obj["kind"] = item["kind"]
        obj["layout_id"] = json.dumps(item["source_id"], ensure_ascii=False)
        if item["kind"] == "building":
            obj["district"] = str(item["district"])
            obj["style"] = str(item["style"])

    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / "city.blend"))
    result = bpy.ops.export_scene.gltf(filepath=str(folder / "city.glb"), export_format="GLB",
                                       export_yup=True, export_extras=True, export_animations=False)
    if "FINISHED" not in result:
        raise RuntimeError("glTF exporter did not finish")


if __name__ == "__main__":
    main(Path(sys.argv[sys.argv.index("--") + 1]))
