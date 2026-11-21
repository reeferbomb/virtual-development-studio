"""Build an original six-frontage night street. Usage: blender52 -b --python city.py -- OUTPUT_DIR SEED."""
import json
import random
import sys
from pathlib import Path

import bpy


class Assembly:
    """Batch architectural details into one multi-material mesh per assembly."""
    def __init__(self, name):
        self.name = name
        self.vertices = []
        self.faces = []
        self.indices = []
        self.slots = []

    def box(self, x, y, z, width, depth, height, material):
        start = len(self.vertices)
        corners = ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                   (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))
        self.vertices.extend((x+a*width/2, y+b*depth/2, z+c*height/2) for a,b,c in corners)
        sides = ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
        self.faces.extend(tuple(start+i for i in face) for face in sides)
        if material not in self.slots:
            self.slots.append(material)
        self.indices.extend([self.slots.index(material)] * 6)

    def finish(self):
        mesh = bpy.data.meshes.new(self.name)
        mesh.from_pydata(self.vertices, [], self.faces)
        for name in self.slots:
            mesh.materials.append(bpy.data.materials[name])
        mesh.polygons.foreach_set("material_index", self.indices)
        mesh.update()
        obj = bpy.data.objects.new(self.name, mesh)
        bpy.context.collection.objects.link(obj)


def palette():
    colors = {
        "Wet asphalt": (.042,.058,.068), "Pavement": (.24,.26,.27),
        "Limestone": (.59,.48,.34), "Oxide brick": (.29,.105,.069),
        "Petrol plaster": (.085,.205,.216), "Slate blue": (.12,.17,.23),
        "Bronze": (.18,.12,.065), "Iron": (.036,.05,.058),
        "Window amber": (1,.48,.14), "Window honey": (.95,.68,.33),
        "Window dark": (.034,.071,.09), "Lane paint": (.67,.47,.18),
        "Porcelain": (.76,.72,.6), "Canopy": (.48,.115,.06),
    }
    for name, rgb in colors.items():
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*rgb,1)
        mat.use_nodes = True
        shader = mat.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (*rgb,1)
        shader.inputs["Roughness"].default_value = .32 if name == "Wet asphalt" else .7
        if name in ("Window amber", "Window honey"):
            shader.inputs["Emission Color"].default_value = (*rgb,1)
            shader.inputs["Emission Strength"].default_value = 1.8


def frontage(side, y, index, rng):
    build = Assembly(f"Facade {side:+d} {index}")
    def box(x, offset, z, w, d, h, mat):
        build.box(side*x, y+offset, z, w, d, h, mat)
    floors = rng.randint(2, 4)
    height = 2.85 + 2.25*floors
    wall = ("Oxide brick", "Petrol plaster", "Slate blue")[(index + side) % 3]
    box(9.5, 0, height/2, 5, 9.72, height, wall)
    for z, w, thick in ((.35,.3,.23),(2.76,.45,.23),(height-.24,.35,.12),(height,.65,.25)):
        box(7,0,z,w,9.92,thick,"Limestone")
    box(9.48,0,height+.08,4.94,9.88,.16,"Iron")
    box(9.52,1.6,height+.45,1.6,1.3,.75,"Slate blue")
    for offset in (-4.63,4.63):
        box(6.97,offset,height/2,.21,.22,height,"Limestone")
    for level in range(floors):
        z = 3.84 + level*2.25
        for offset in (-3.35,-1.12,1.12,3.35):
            box(6.93,offset,z,.18,1.53,1.72,"Bronze")
            glass = rng.choice(("Window amber","Window honey","Window dark","Window dark"))
            box(6.82,offset,z,.07,1.33,1.51,glass)
            box(6.77,offset,z,.06,.07,1.55,"Iron")
            box(6.77,offset,z+.28,.06,1.36,.07,"Iron")
            box(6.86,offset,z-.89,.48,1.75,.13,"Limestone")
    for offset in (-3.1,0,3.1):
        box(6.92,offset,1.39,.22,2.49,2.29,"Iron")
        box(6.78,offset,1.42,.07,2.28,1.96,"Window dark" if offset==0 else "Window honey")
        box(6.72,offset,1.39,.08,.1,2.14,"Bronze")
    box(6.4,0,2.52,1.23,8.88,.15,"Iron")
    for stripe in range(18):
        box(5.8,-4.19+stripe*.49,2.45,.12,.48,.24,"Porcelain" if stripe%2 else "Canopy")
    build.finish()


def street():
    road = Assembly("Street")
    road.box(0,0,-.1,24,30,.2,"Wet asphalt")
    for y in range(-14,15,4):
        road.box(0,y,.009,.11,1.8,.018,"Lane paint")
    for y in (-12.1,12.1):
        for x in range(-4,5):
            road.box(x,y,.012,.51,1.34,.024,"Porcelain")
    road.finish()
    for side in (-1,1):
        walk = Assembly(f"Sidewalk {side:+d}")
        walk.box(side*8.25,0,.09,7.5,30,.18,"Pavement")
        for i in range(30):
            walk.box(side*4.55,i-14.5,.12,.24,.97,.24,"Limestone")
        walk.finish()
        for i, y in enumerate((-13.5,-5,5,13.5)):
            lamp = Assembly(f"Lantern {side:+d} {i}")
            for x,z,w,d,h,mat in ((5,.39,.31,.31,.48,"Iron"),(5,1.79,.13,.13,2.7,"Iron"),
                                  (4.69,3.16,.75,.12,.12,"Bronze"),(4.39,2.95,.28,.28,.34,"Window amber"),
                                  (4.39,3.14,.4,.4,.1,"Iron"),(4.39,2.75,.35,.35,.08,"Iron")):
                lamp.box(side*x,y,z,w,d,h,mat)
            lamp.finish()


def main():
    args = sys.argv[sys.argv.index("--")+1:]
    out, seed = Path(args[0]).resolve(), int(args[1])
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    palette()
    street()
    rng = random.Random(seed)
    for side in (-1,1):
        for i, y in enumerate((-10,0,10)):
            frontage(side,y,i,rng)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    info = dict(seed=seed, mesh_count=len(meshes), materials=sorted(m.name for m in bpy.data.materials),
                triangles=sum(len(p.vertices)-2 for o in meshes for p in o.data.polygons))
    bpy.ops.wm.save_as_mainfile(filepath=str(out/"city.blend"))
    bpy.ops.export_scene.gltf(filepath=str(out/"city.glb"),export_format="GLB")
    (out/"city.json").write_text(json.dumps(info,indent=2)+"\n")


if __name__ == "__main__":
    main()
