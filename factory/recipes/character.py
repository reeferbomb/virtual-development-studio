"""Generate a skinned, segmented training mannequin in an empty Blender scene."""
import math

import bpy
from mathutils import Vector


def create(spec: dict) -> None:
    name = spec["id"]
    height = float(spec.get("height_m", 1.7))
    if not math.isfinite(height) or height <= 0:
        raise ValueError("height_m must be positive and finite")
    color = tuple(spec["color"])
    vertices, faces, materials, weights = [], [], [], {}
    bones = []

    def bone(label, start, end, parent=None):
        bones.append((label, start, end, parent))

    def solid(label, start, end, rings, material=0):
        # Elliptical cross-sections follow the segment from start to end.
        start, end = Vector(start), Vector(end)
        axis = (end - start).normalized()
        right = Vector((0, 1, 0)).cross(axis).normalized()
        depth = axis.cross(right)
        first = len(vertices)
        sides = 12
        for position, radius, thickness in rings:
            center = start.lerp(end, position)
            for i in range(sides):
                angle = 2 * math.pi * i / sides
                point = center + radius * math.cos(angle) * right + thickness * math.sin(angle) * depth
                vertices.append(tuple(point * height))
        faces.append(tuple(first + i for i in reversed(range(sides))))
        for j in range(len(rings) - 1):
            for i in range(sides):
                a = first + j * sides + i
                b = first + j * sides + (i + 1) % sides
                faces.append((a, b, b + sides, a + sides))
        top = len(vertices) - sides
        faces.append(tuple(top + i for i in range(sides)))
        materials.extend([material] * (2 + (len(rings) - 1) * sides))
        weights.setdefault(label, []).extend(range(first, len(vertices)))

    def shell(label, start, end, width, depth, taper=.82):
        solid(label, start, end, [
            (.07, width * .70, depth * .7), (.18, width, depth),
            (.80, width * taper, depth * taper), (.94, width * taper * .7, depth * taper * .7)])

    def joint(label, center, radius):
        x, y, z = center
        solid(label, (x, y, z-radius), (x, y, z+radius),
              [(0, .30*radius, .30*radius), (.2, .80*radius, .80*radius),
               (.5, radius, radius), (.8, .80*radius, .80*radius),
               (1, .30*radius, .30*radius)], 1)

    pelvis, waist, collar = (0, 0, .485), (0, 0, .59), (0, 0, .80)
    neck, crown = (0, 0, .838), (0, 0, 1)
    bone("Pelvis", pelvis, waist)
    bone("Chest", waist, collar, "Pelvis")
    bone("Neck", collar, neck, "Chest")
    bone("Head", neck, crown, "Neck")
    shell("Pelvis", pelvis, waist, .112, .073)
    joint("Chest", waist, .051)
    solid("Chest", waist, collar, [(.04, .081, .058), (.30, .103, .068),
                                   (.76, .145, .084), (.96, .113, .065)])
    joint("Neck", (0, 0, .819), .029)
    solid("Head", neck, crown, [(0, .041, .048), (.23, .059, .069),
                                (.69, .073, .077), (.90, .064, .068), (1, .041, .044)])
    # A dark inset on the forward (-Y) face gives a clear facing direction.
    solid("Head", (0, -.059, .909), (0, -.059, .946),
          [(0, .047, .015), (.5, .061, .021), (1, .051, .016)], 1)

    for side, s in (("L", 1), ("R", -1)):
        shoulder, elbow, wrist, hand = [
            (s*x, y, z) for x, y, z in ((.128, 0, .763), (.208, 0, .624),
                                         (.249, -.017, .494), (.260, -.024, .409))]
        hip, knee, ankle, toe = [
            (s*x, y, z) for x, y, z in ((.070, 0, .50), (.080, -.008, .274),
                                         (.082, .002, .063), (.082, -.076, .031))]
        for limb, start, end, parent, w, d in [
                ("UpperArm", shoulder, elbow, "Chest", .042, .048),
                ("Forearm", elbow, wrist, "UpperArm."+side, .035, .040),
                ("Hand", wrist, hand, "Forearm."+side, .033, .025),
                ("Thigh", hip, knee, "Pelvis", .064, .070),
                ("Shin", knee, ankle, "Thigh."+side, .049, .050)]:
            label = limb + "." + side
            bone(label, start, end, parent)
            joint(label, start, min(w, d)*.85)
            shell(label, start, end, w, d)
        foot = "Foot." + side
        bone(foot, ankle, toe, "Shin."+side)
        joint(foot, ankle, .028)
        x = ankle[0]
        solid(foot, (x, -.029, 0), (x, -.029, .057),
              [(0, .039, .076), (.21, .044, .080), (.72, .041, .068), (1, .031, .042)])

    arm = bpy.data.armatures.new(name + "_Skeleton")
    rig = bpy.data.objects.new(name + "_Rig", arm)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for label, start, end, parent in bones:
        edit = arm.edit_bones.new(label)
        edit.head, edit.tail = Vector(start)*height, Vector(end)*height
        if parent:
            edit.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh = bpy.data.meshes.new(name + "_Geometry")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name + "_Body", mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = rig
    for label, rgb in (("Shell", color), ("Joint", (.040, .052, .060))):
        material = bpy.data.materials.new(name + "_" + label)
        material.diffuse_color = (*rgb, 1)
        material.use_nodes = True
        shader = material.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (*rgb, 1)
        shader.inputs["Roughness"].default_value = .62
        mesh.materials.append(material)
    for polygon, index in zip(mesh.polygons, materials):
        polygon.material_index = index
    for label, indices in weights.items():
        obj.vertex_groups.new(name=label).add(indices, 1.0, "REPLACE")
    modifier = obj.modifiers.new("Skeleton", "ARMATURE")
    modifier.object = rig
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 49
    for frame, amount in ((1, 0), (13, 1), (25, 0), (37, -1), (49, 0)):
        for label, amplitude in (("Chest", .025), ("Head", -.017),
                                 ("UpperArm.L", .023), ("UpperArm.R", -.023)):
            pose = rig.pose.bones[label]
            pose.rotation_mode = "XYZ"
            pose.rotation_euler.x = amplitude * amount
            pose.keyframe_insert(data_path="rotation_euler", frame=frame)
    rig.animation_data.action.name = "Idle_loop"
    scene.frame_set(1)
    obj.select_set(True)
