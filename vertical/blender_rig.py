"""Blender worker for the original Switchyard Courier character. Run through rig.py."""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector


# Metres, soles at zero. Rest pose faces -Y, left is +X.
BONES = {
    "Hips": ((0, 0, .88), (0, 0, 1.03), None),
    "Spine": ((0, 0, 1.03), (0, 0, 1.23), "Hips"),
    "Chest": ((0, 0, 1.23), (0, 0, 1.47), "Spine"),
    "Neck": ((0, 0, 1.47), (0, 0, 1.54), "Chest"),
    "Head": ((0, 0, 1.54), (0, 0, 1.76), "Neck"),
}
for side, sign in (("L", 1), ("R", -1)):
    shoulder, elbow, wrist, fingertip = [(x*sign, y, z) for x, y, z in
        ((.205, 0, 1.43), (.30, -.012, 1.17), (.355, -.05, .948), (.365, -.063, .835))]
    hip, knee, ankle, toe = [(x*sign, y, z) for x, y, z in
        ((.102, 0, .906), (.115, -.016, .486), (.12, .008, .105), (.12, -.145, .043))]
    for joint, start, end, parent in (
        ("Clavicle", (0, 0, 1.43), shoulder, "Chest"),
        ("UpperArm", shoulder, elbow, "Clavicle."+side),
        ("Forearm", elbow, wrist, "UpperArm."+side),
        ("Hand", wrist, fingertip, "Forearm."+side),
        ("Thigh", hip, knee, "Hips"),
        ("Shin", knee, ankle, "Thigh."+side),
        ("Foot", ankle, toe, "Shin."+side),
    ):
        BONES[joint+"."+side] = (start, end, parent)

FRAMES = dict(idle=48, walk=28, run=18, crouch=42, aim=36, reload=40, jump=32, death=36)
LOOPS = {"idle", "walk", "run", "crouch", "aim"}
PALETTE = {
    "Storm canvas": (.067, .225, .245),
    "Night weave": (.027, .049, .067),
    "Signal orange": (.92, .235, .055),
    "Ivory tape": (.85, .77, .55),
    "Smoke glass": (.021, .085, .107),
    "Bearing steel": (.24, .31, .34),
}


class Tailor:
    """Cloth, hardware and panel geometry assembled into a single weighted mesh."""

    def __init__(self):
        self.verts, self.faces, self.face_slots, self.weights = [], [], [], []

    def rings(self, rings, material, sides=12, basis=None):
        # (center, elliptical radii, weight map) ordered along the extrusion axis.
        right, depth = basis or (Vector((1, 0, 0)), Vector((0, 1, 0)))
        first = len(self.verts)
        for center, width, thickness, weights in rings:
            for i in range(sides):
                angle = 2*math.pi*(i+.5)/sides
                self.verts.append(Vector(center) + width*math.cos(angle)*right
                                  + thickness*math.sin(angle)*depth)
                self.weights.append(weights)
        faces = [tuple(first+i for i in reversed(range(sides)))]
        for row in range(len(rings)-1):
            for i in range(sides):
                a = first + row*sides
                j = (i+1) % sides
                faces.append((a+i, a+j, a+j+sides, a+i+sides))
        faces.append(tuple(len(self.verts)-sides+i for i in range(sides)))
        self.faces.extend(faces)
        self.face_slots.extend([material]*len(faces))

    def vertical(self, sections, material, bone, center=(0, 0), sides=12):
        self.rings([((*center, z), w, d, {bone: 1.}) for z, w, d in sections], material, sides)

    def limb(self, bone, sections, material):
        start, end, parent = BONES[bone]
        start, end = Vector(start), Vector(end)
        direction = (end-start).normalized()
        right = Vector((0, 1, 0)).cross(direction).normalized()
        depth = direction.cross(right)
        rings = []
        for t, w, d, parent_share in sections:
            weights = {bone: 1.-parent_share}
            if parent_share:
                weights[parent] = parent_share
            rings.append((start.lerp(end, t), w, d, weights))
        self.rings(rings, material, basis=(right, depth))

    def panel(self, bone, center, size, material, roll=0.):
        # Eight-sided chamfered plates soften the silhouette of the harness and pack.
        w, d, h = size
        c = Vector(center)
        start = len(self.verts)
        angle = Euler((0, math.radians(roll), 0)).to_matrix()
        points = ((-.78,-1),(.78,-1),(1,-.72),(1,.72),(.78,1),(-.78,1),(-1,.72),(-1,-.72))
        for front in (-1, 1):
            for x, z in points:
                self.verts.append(c + angle @ Vector((x*w*.5, front*d*.5, z*h*.5)))
                self.weights.append({bone: 1.})
        faces = [tuple(start+i for i in range(8)), tuple(start+i for i in reversed(range(8,16)))]
        for i in range(8):
            j = (i+1)%8
            faces.append((start+i, start+i+8, start+j+8, start+j))
        self.faces.extend(faces)
        self.face_slots.extend([material]*len(faces))


def model():
    t = Tailor()
    t.rings([((0,0,z), w,d,weights) for z,w,d,weights in (
        (.875,.162,.113,{"Hips":1}),(.96,.18,.126,{"Hips":.9,"Spine":.1}),
        (1.04,.156,.103,{"Hips":.5,"Spine":.5}),(1.12,.167,.112,{"Spine":1}),
        (1.25,.198,.124,{"Spine":.45,"Chest":.55}),(1.39,.231,.137,{"Chest":1}),
        (1.445,.202,.118,{"Chest":1}),(1.49,.099,.088,{"Chest":1}))], "Storm canvas")
    t.vertical([(.979,.174,.121),(1.006,.17,.118),(1.018,.164,.115)],"Night weave","Hips")
    t.panel("Hips",(0,-.12,.998),(.062,.023,.033),"Bearing steel")
    t.vertical([(1.455,.094,.086),(1.502,.096,.085),(1.553,.073,.070)],"Night weave","Neck")
    t.vertical([(1.526,.068,.077),(1.564,.103,.098),(1.662,.123,.116),
                (1.728,.11,.103),(1.767,.079,.078)],"Ivory tape","Head")
    t.vertical([(1.65,.127,.121),(1.676,.136,.13),(1.735,.125,.12),
                (1.778,.092,.092),(1.79,.061,.065)],"Signal orange","Head")
    t.panel("Head",(0,-.103,1.638),(.217,.048,.081),"Night weave")
    t.panel("Head",(0,-.126,1.644),(.19,.014,.049),"Smoke glass")
    t.panel("Head",(.067,-.135,1.65),(.032,.007,.009),"Ivory tape")
    t.panel("Chest",(0,.147,1.272),(.254,.15,.33),"Night weave")
    t.panel("Chest",(0,.224,1.31),(.214,.033,.185),"Storm canvas")
    t.panel("Chest",(0,.248,1.305),(.18,.019,.023),"Signal orange")
    t.panel("Chest",(0,-.117,1.321),(.053,.048,.30),"Night weave",-23)
    t.panel("Chest",(.103,-.118,1.373),(.083,.032,.043),"Ivory tape")
    for side, s in (("L",1),("R",-1)):
        def sleeve(label, sections, mat):
            t.limb(label+"."+side, sections, mat)
        sleeve("Clavicle",[(.47,.063,.064,.32),(.8,.087,.081,.05),(1.05,.078,.071,0)],"Storm canvas")
        sleeve("UpperArm",[(-.07,.076,.075,.65),(.1,.09,.086,.23),(.48,.079,.078,0),
                            (.91,.064,.067,0),(1.03,.061,.063,0)],"Storm canvas")
        sleeve("UpperArm",[(.25,.091,.086,0),(.31,.09,.086,0),(.35,.087,.084,0)],"Signal orange")
        sleeve("Forearm",[(-.07,.061,.062,.64),(.08,.068,.066,.31),(.4,.066,.066,0),
                           (.9,.046,.048,0),(1,.043,.044,0)],"Storm canvas")
        sleeve("Forearm",[(.7,.055,.057,0),(.76,.055,.056,0),(.81,.053,.054,0)],"Ivory tape")
        sleeve("Hand",[(-.08,.043,.044,.6),(.18,.051,.046,.2),(.55,.050,.044,0),
                        (.93,.034,.031,0),(1,.025,.023,0)],"Night weave")
        sleeve("Thigh",[(-.05,.091,.101,.6),(.12,.103,.107,.23),(.47,.093,.099,0),
                         (.85,.078,.081,0),(1,.074,.074,0)],"Night weave")
        sleeve("Shin",[(-.085,.073,.074,.71),(.11,.082,.082,.25),(.36,.079,.085,0),
                        (.77,.052,.057,0),(1,.051,.054,0)],"Night weave")
        t.panel("Shin."+side,(s*.116,-.075,.435),(.118,.046,.129),"Storm canvas")
        t.vertical([(.012,.067,.144),(.035,.076,.15),(.067,.073,.143),
                    (.107,.058,.089),(.14,.052,.059)],"Night weave","Foot."+side,(s*.12,-.054))
        t.vertical([(.004,.069,.145),(.018,.075,.153),(.03,.076,.154)],
                   "Bearing steel","Foot."+side,(s*.12,-.054))
    t.panel("Forearm.L",(.346,-.097,1.039),(.075,.033,.094),"Bearing steel")
    t.panel("Forearm.L",(.346,-.116,1.04),(.051,.009,.057),"Signal orange")
    return t


def make_armature(t):
    arm = bpy.data.armatures.new("Courier Skeleton")
    rig = bpy.data.objects.new("Courier", arm)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name,(head,tail,parent) in BONES.items():
        bone = arm.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = arm.edit_bones[parent]
            bone.use_connect = (bone.head-bone.parent.tail).length < .0001
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh = bpy.data.meshes.new("Courier Garments")
    mesh.from_pydata(t.verts, [], t.faces)
    mesh.update()
    body = bpy.data.objects.new("Courier Suit", mesh)
    bpy.context.collection.objects.link(body)
    body.parent = rig
    for name, rgb in PALETTE.items():
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*rgb,1)
        mat.use_nodes = True
        shader = mat.node_tree.nodes["Principled BSDF"]
        shader.inputs["Base Color"].default_value = mat.diffuse_color
        shader.inputs["Roughness"].default_value = .24 if name == "Smoke glass" else .76
        shader.inputs["Metallic"].default_value = .55 if name == "Bearing steel" else .03
        mesh.materials.append(mat)
    for poly, mat in zip(mesh.polygons, t.face_slots):
        poly.material_index = mesh.materials.find(mat)
    groups = {name: body.vertex_groups.new(name=name) for name in BONES}
    for index, weights in enumerate(t.weights):
        for name,value in weights.items():
            groups[name].add([index], value, "REPLACE")
    body.modifiers.new("Garment Deformation", "ARMATURE").object = rig
    return rig


def sample(name, t):
    wave, pulse = math.sin(2*math.pi*t), .5-.5*math.cos(2*math.pi*t)
    p = {}
    height, back = 0., 0.
    if name == "idle":
        p.update(Spine=(1.9*wave,0,0), Head=(-1.2*wave,0,2.2*wave))
        height = .004*pulse
    elif name in ("walk","run"):
        run = name == "run"
        p.update(Chest=(11 if run else 4,0,5*wave), Hips=(0,2*wave,-4*wave))
        height = (.043 if run else .022)*math.sin(2*math.pi*t)**2
        for side, sign in (("L",1),("R",-1)):
            swing = sign*wave
            bend = (68 if run else 40)*max(0, -swing)
            p["Thigh."+side] = (-(43 if run else 26)*swing-5,0,0)
            p["Shin."+side] = (bend+8,0,0)
            p["Foot."+side] = (-bend*.55,0,0)
            p["UpperArm."+side] = ((35 if run else 20)*swing,0,0)
            p["Forearm."+side] = ((-61 if run else -17)-5*swing,0,0)
    elif name == "crouch":
        h = .93+.07*pulse
        height = -.268*h
        p.update(Chest=(20*h,0,2*wave),Head=(-12*h,0,0))
        for side in ("L","R"):
            p["Thigh."+side] = (-51*h,0,0)
            p["Shin."+side] = (100*h,0,0)
            p["Foot."+side] = (-49*h,0,0)
            p["Forearm."+side] = (-30*h,0,0)
    elif name in ("aim","reload"):
        # The courier points a forearm scanner and changes its battery.
        reach = pulse if name == "reload" else 0
        p.update(Chest=(4+wave,-2,-11-6*reach), Head=(-2+16*reach,0,11))
        p["UpperArm.L"] = (-63+22*reach,-15,4)
        p["Forearm.L"] = (-22-28*reach+pulse,0,-7)
        p["UpperArm.R"] = (-40-11*reach,17,-14)
        p["Forearm.R"] = (-45-22*reach,8,-13-29*reach)
    elif name == "jump":
        def bump(mid, radius):
            return max(0., 1.-abs(t-mid)/radius)
        coil = bump(.18,.18)+.8*bump(.82,.18)
        air = math.sin(math.pi*min(1.,max(0.,(t-.24)/.5)))
        height = .34*air-.145*coil
        p["Chest"] = (14*coil+6*air,0,0)
        for side in ("L","R"):
            p["Thigh."+side] = (-32*coil-24*air,0,0)
            p["Shin."+side] = (65*coil+37*air,0,0)
            p["Foot."+side] = (-33*coil-9*air,0,0)
            p["UpperArm."+side] = (22*coil-54*air,0,0)
    else:  # Backward fall with terminal hold.
        fall = min(1.,t/.76)
        fall = fall*fall*(3-2*fall)
        height, back = -.698*fall, .22*fall
        p.update(Hips=(-86*fall,0,-5*fall),Chest=(-4*fall,0,4*fall), Head=(9*fall,0,10*fall))
        for side, sign in (("L",1),("R",-1)):
            p["UpperArm."+side] = (-24*fall,sign*28*fall,0)
            p["Thigh."+side] = ((-14+9*sign)*fall,0,0)
            p["Shin."+side] = (26*fall,0,0)
    return p, Vector((0,back,height))


def animate(rig):
    scene = bpy.context.scene
    scene.render.fps, scene.frame_end = 24, FRAMES["idle"]+1
    ad = rig.animation_data_create()
    for name, length in FRAMES.items():
        action = bpy.data.actions.new(name)
        action.use_fake_user = True
        action.use_cyclic = name in LOOPS
        ad.action = action
        for step in range(17):
            t = step/16
            angles, offset = sample(name,t)
            for bone in rig.pose.bones:
                local = bone.bone.matrix_local.to_quaternion()
                rot = Euler(tuple(math.radians(a) for a in angles.get(bone.name,(0,0,0)))).to_quaternion()
                bone.rotation_mode = "QUATERNION"
                bone.rotation_quaternion = local.inverted() @ rot @ local
                bone.keyframe_insert(data_path="rotation_quaternion",frame=1+t*length)
                if bone.name == "Hips":
                    bone.location = local.inverted() @ offset
                    bone.keyframe_insert(data_path="location",frame=1+t*length)
        track = ad.nla_tracks.new()
        track.name = name
        strip = track.strips.new(name,1,action)
        if hasattr(strip, "action_slot"):
            strip.action_slot = ad.action_slot
        track.mute = True
        ad.action = None
    ad.action = bpy.data.actions["idle"]
    scene.frame_set(1)


def build(out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rig = make_armature(model())
    animate(rig)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(out/"courier.blend"))
    bpy.ops.export_scene.gltf(filepath=str(out/"courier.glb"), export_format="GLB",
        export_animation_mode="ACTIONS", export_force_sampling=True, export_yup=True,
        export_optimize_animation_size=False)


def inspect(out):
    rig = bpy.data.objects["Courier"]
    body = bpy.data.objects["Courier Suit"]
    assert rig.type == "ARMATURE" and body.parent == rig
    assert any(mod.type == "ARMATURE" and mod.object == rig for mod in body.modifiers)
    assert {b.name for b in rig.data.bones if b.use_deform} == set(BONES)
    used = set()
    blended = 0
    for vertex in body.data.vertices:
        ws = [g for g in vertex.groups if g.weight > .00001]
        assert 1 <= len(ws) <= 4 and abs(sum(g.weight for g in ws)-1) < .0001
        used.update(body.vertex_groups[g.group].name for g in ws)
        blended += len(ws) > 1
    assert used == set(BONES) and blended > 0
    assert set(FRAMES) == {a.name for a in bpy.data.actions}
    motion = {}
    for name,duration in FRAMES.items():
        rig.animation_data.action = bpy.data.actions[name]
        def positions(f):
            bpy.context.scene.frame_set(f)
            ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
            return [v.co.copy() for v in ev.data.vertices]
        a = positions(1)
        b = positions(1+round(duration*.25))
        motion[name] = round(max((u-v).length for u,v in zip(a,b)),6)
        assert motion[name] > .0001, name+" has no mesh movement"
    report = dict(blender=bpy.app.version_string, bones=len(used),
                  vertices=len(body.data.vertices), multi_weight_vertices=blended,
                  peak_vertex_motion_m=motion)
    (out/"native-inspection.json").write_text(json.dumps(report))


if __name__ == "__main__":
    mode, directory = sys.argv[sys.argv.index("--")+1:]
    {"build": build, "inspect": inspect}[mode](Path(directory))
