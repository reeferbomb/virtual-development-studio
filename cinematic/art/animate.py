"""Build the cinematic actor with blender52 -b --python animate.py -- OUTPUT_DIR."""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "factory" / "recipes"))
import character


def pose_sample(name, t):
    """Return joint angles in rest-space world axes, degrees, and pelvis height delta."""
    pose = {}
    wave = math.sin(2 * math.pi * t)
    pulse = .5 - .5 * math.cos(2 * math.pi * t)
    height = 0
    if name == "Idle":
        pose.update(Chest=(2*wave, 0, 0), Head=(-1.3*wave, 0, wave))
    elif name in ("Walk", "Run"):
        run = name == "Run"
        height = (.055 if run else .026) * abs(wave)
        pose["Chest"] = (12 if run else 3, 0, 5*wave)
        for side, sign in (("L", 1), ("R", -1)):
            swing = sign*wave
            knee = max(0, swing) * (75 if run else 38)
            pose["Thigh."+side] = ((43 if run else 26)*swing-4, 0, 0)
            pose["Shin."+side] = (knee+5, 0, 0)
            pose["Foot."+side] = (-knee*.5, 0, 0)
            pose["UpperArm."+side] = (-(35 if run else 18)*swing, 0, 0)
            pose["Forearm."+side] = (-58 if run else -15, 0, 0)
    elif name == "Crouch":
        depth = .90 + .10*pulse
        height = -.195*depth
        pose["Chest"] = (19*depth, 0, 0)
        for side in ("L", "R"):
            pose["Thigh."+side] = (-46*depth, 0, 0)
            pose["Shin."+side] = (84*depth, 0, 0)
            pose["Foot."+side] = (-38*depth, 0, 0)
            pose["Forearm."+side] = (-35, 0, 0)
    else:
        reload = pulse if name == "Reload" else 0
        pose.update({
            "Chest": (5+pulse, 0, -7-6*reload),
            "Head": (-3+9*reload, 0, 7),
            "UpperArm.R": (-58+23*reload, -14, 0),
            "Forearm.R": (-32-16*reload-pulse, 0, 0),
            "UpperArm.L": (-53+49*reload, 15, 0),
            "Forearm.L": (-43-21*reload, 0, -14),
        })
    return pose, height


def build(directory):
    directory.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    character.create({"id": "CinematicActor", "height_m": 1.75, "color": (.18, .45, .53)})
    rig = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    animation = rig.animation_data
    original = animation.action
    animation.action = None
    bpy.data.actions.remove(original)
    scene = bpy.context.scene
    scene.render.fps = 24
    for name, duration in (("Idle", 48), ("Walk", 32), ("Run", 16),
                           ("Aim", 48), ("Crouch", 40), ("Reload", 32)):
        action = bpy.data.actions.new(name)
        animation.action = action
        for step in range(9):
            pose, height = pose_sample(name, step/8)
            frame = 1+duration*step/8
            for bone in rig.pose.bones:
                orientation = bone.bone.matrix_local.to_quaternion()
                angles = tuple(math.radians(v) for v in pose.get(bone.name, (0, 0, 0)))
                bone.rotation_mode = "QUATERNION"
                bone.rotation_quaternion = orientation.inverted() @ Euler(angles).to_quaternion() @ orientation
                bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)
                if bone.name == "Pelvis":
                    bone.location = orientation.inverted() @ Vector((0, 0, height))
                    bone.keyframe_insert(data_path="location", frame=frame)
        track = animation.nla_tracks.new()
        track.name = name
        strip = track.strips.new(name, 1, action)
        strip.action_slot = animation.action_slot
        track.mute = name != "Idle"
        animation.action = None
    scene.frame_set(1)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(directory / "animated_actor.blend"))
    bpy.ops.export_scene.gltf(filepath=str(directory / "animated_actor.glb"),
                              export_format="GLB", export_animation_mode="ACTIONS",
                              export_nla_strips=True, export_force_sampling=True)


if __name__ == "__main__":
    build(Path(sys.argv[sys.argv.index("--")+1]).resolve())
