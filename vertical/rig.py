"""Generate, reopen, and independently inspect the Switchyard Courier character.

    python vertical/rig.py --out /path/to/new-directory
"""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile


CLIPS = ("idle", "walk", "run", "crouch", "aim", "reload", "jump", "death")
PARENTS = {"Hips": None, "Spine": "Hips", "Chest": "Spine", "Neck": "Chest", "Head": "Neck"}
for side in ("L", "R"):
    for joint, parent in (("Clavicle","Chest"), ("UpperArm","Clavicle."+side),
                          ("Forearm","UpperArm."+side), ("Hand","Forearm."+side),
                          ("Thigh","Hips"), ("Shin","Thigh."+side), ("Foot","Shin."+side)):
        PARENTS[joint+"."+side] = parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


class BinaryGltf:
    """Read packed or interleaved, little-endian glTF 2.0 accessor data."""

    def __init__(self, path):
        raw = Path(path).read_bytes()
        require(len(raw) >= 20, "truncated GLB")
        magic, version, length = struct.unpack_from("<4sII", raw)
        require((magic, version, length) == (b"glTF", 2, len(raw)), "invalid GLB header")
        chunks = {}
        offset = 12
        while offset < len(raw):
            require(offset+8 <= len(raw), "truncated chunk header")
            size, tag = struct.unpack_from("<I4s", raw, offset)
            offset += 8
            require(tag not in chunks and offset+size <= len(raw), "invalid GLB chunk")
            chunks[tag] = raw[offset:offset+size]
            offset += size
        require(b"JSON" in chunks and b"BIN\0" in chunks, "embedded geometry missing")
        self.doc = json.loads(chunks[b"JSON"])
        self.bin = chunks[b"BIN\0"]
        require(self.doc["asset"]["version"] == "2.0", "glTF version mismatch")
        self.cache = {}

    def read(self, index, kind):
        doc = self.doc
        ac = doc["accessors"][index]
        require(ac["type"] == kind, "unexpected accessor type "+ac["type"])
        if index in self.cache:
            return self.cache[index]
        types = {5121:"B",5123:"H",5125:"I",5126:"f"}
        sizes = {"SCALAR":1, "VEC3":3, "VEC4":4, "MAT4":16}
        component = ac["componentType"]
        fmt = struct.Struct("<"+types[component]*sizes[kind])
        view = doc["bufferViews"][ac["bufferView"]]
        start = view.get("byteOffset",0)
        end = start+view["byteLength"]
        offset = start+ac.get("byteOffset",0)
        stride = view.get("byteStride", fmt.size)
        count = ac["count"]
        require(view["buffer"] == 0 and count > 0 and 0 <= start <= offset and stride >= fmt.size
                and offset+(count-1)*stride+fmt.size <= end <= len(self.bin), "accessor outside buffer")
        values = list(fmt.iter_unpack(self.bin[offset:offset+count*stride])) if stride == fmt.size else [
            fmt.unpack_from(self.bin,offset+i*stride) for i in range(count)]
        if ac.get("normalized"):
            require(component in (5121,5123), "invalid normalized accessor")
            maximum = 255 if component == 5121 else 65535
            values = [tuple(v/maximum for v in row) for row in values]
        require(all(math.isfinite(v) for row in values for v in row), "nonfinite accessor")
        self.cache[index] = values
        return values


def audit_glb(path):
    glb = BinaryGltf(path)
    doc = glb.doc
    require(len(doc.get("skins",[])) == 1, "expected one skin")
    skin = doc["skins"][0]
    joints = skin["joints"]
    joint_names = {idx:doc["nodes"][idx]["name"] for idx in joints}
    require(len(joints) == len(PARENTS) and set(joint_names.values()) == set(PARENTS),
            "named joint set mismatch")
    for parent in joints:
        child_names = {joint_names[i] for i in doc["nodes"][parent].get("children",[]) if i in joint_names}
        require(child_names == {n for n,p in PARENTS.items() if p == joint_names[parent]},
                "joint hierarchy mismatch")
    bind = glb.read(skin["inverseBindMatrices"],"MAT4")
    require(len(bind) == len(joints) and all(abs(m[15]-1.) < .0001 for m in bind), "inverse bind matrices")
    mesh_nodes = [node for node in doc["nodes"] if "mesh" in node]
    require(len(mesh_nodes) == 1 and mesh_nodes[0].get("skin") == 0, "skinned mesh missing")
    vertex_count, multi, triangles = 0, 0, 0
    weighted_joints = set()
    mesh = doc["meshes"][mesh_nodes[0]["mesh"]]
    for primitive in mesh["primitives"]:
        attr = primitive["attributes"]
        points = glb.read(attr["POSITION"],"VEC3")
        indices = glb.read(primitive["indices"],"SCALAR")
        require(primitive.get("mode",4) == 4 and len(indices)%3 == 0 and
                all(0 <= row[0] < len(points) for row in indices), "invalid triangle indices")
        blend_indices = glb.read(attr["JOINTS_0"],"VEC4")
        weights = glb.read(attr["WEIGHTS_0"],"VEC4")
        require(len(points) == len(blend_indices) == len(weights), "skin attribute count mismatch")
        for bones, shares in zip(blend_indices, weights):
            require(all(isinstance(i,int) and 0 <= i < len(joints) for i in bones), "joint index out of range")
            require(all(0 <= w <= 1. for w in shares) and abs(sum(shares)-1.) < .001,
                    "weights must sum to one")
            active = [i for i,w in zip(bones,shares) if w > .0001]
            weighted_joints.update(active)
            multi += len(active) > 1
        vertex_count += len(points)
        triangles += len(indices)//3
    require(len(weighted_joints) == len(joints) and multi > 0, "skin lacks blended or weighted joints")
    animations = doc.get("animations",[])
    require(len(animations) == len(CLIPS) and {a["name"] for a in animations} == set(CLIPS),
            "missing or duplicate animation clips")
    clips = {}
    for anim in animations:
        moving = set()
        seconds = 0.
        for channel in anim["channels"]:
            target = channel["target"]
            require(target["node"] in joint_names, "animation target outside skeleton")
            sampler = anim["samplers"][channel["sampler"]]
            times = [row[0] for row in glb.read(sampler["input"],"SCALAR")]
            require(all(b>a for a,b in zip(times,times[1:])) and times[0] >= 0, "invalid key times")
            require(target["path"] in ("rotation","translation","scale"), "invalid animation target path")
            rotation = target["path"] == "rotation"
            values = glb.read(sampler["output"],"VEC4" if rotation else "VEC3")
            require(len(values) == len(times), "animation key count mismatch")
            if rotation:
                require(all(abs(sum(x*x for x in q)-1)<.001 for q in values), "rotation is not normalized")
                changed = any(abs(sum(a*b for a,b in zip(values[0],q))) < .999999 for q in values)
            else:
                changed = any(math.dist(values[0],v) > .0001 for v in values)
            if changed:
                moving.add(joint_names[target["node"]])
            seconds = max(seconds,times[-1]-times[0])
        require(moving and seconds > .1, anim["name"]+" has no articulation")
        clips[anim["name"]] = {"seconds":round(seconds,4), "moving_joints":sorted(moving)}
    return dict(joints=list(joint_names.values()), triangles=triangles, exported_vertices=vertex_count,
                multi_weight_vertices=multi, materials=len(doc["materials"]), clips=clips)


GODOT_CHECK = '''extends SceneTree

func _initialize() -> void:
    call_deferred("verify")

func verify() -> void:
    var packed := load("res://courier.glb") as PackedScene
    if not packed:
        quit(1)
        return
    var actor := packed.instantiate()
    root.add_child(actor)
    var sk := actor.find_children("*","Skeleton3D",true,false)
    var ap := actor.find_children("*","AnimationPlayer",true,false)
    var meshes := actor.find_children("*","MeshInstance3D",true,false)
    if sk.size() != 1 or ap.size() != 1 or meshes.size() != 1 or meshes[0].skin == null:
        quit(2)
        return
    var s: Skeleton3D = sk[0]
    var player: AnimationPlayer = ap[0]
    var motion := {}
    for clip in ["idle","walk","run","crouch","aim","reload","jump","death"]:
        if not player.has_animation(clip):
            quit(3)
            return
        player.play(clip)
        player.seek(0.0, true)
        var before: Array[Quaternion] = []
        for i in s.get_bone_count():
            before.append(s.get_bone_pose_rotation(i))
        player.seek(player.current_animation_length*0.25,true)
        var changed := 0
        for i in s.get_bone_count():
            if absf(s.get_bone_pose_rotation(i).dot(before[i])) < 0.999999:
                changed += 1
        if changed == 0:
            push_error("No moving bone in "+clip)
            quit(4)
            return
        motion[clip] = changed
    print("COURIER_IMPORT "+JSON.stringify({"godot":Engine.get_version_info().string,
        "bones":s.get_bone_count(),"skin_binds":meshes[0].skin.get_bind_count(),"moving_bones":motion}))
    quit(0)
'''


def run(command, env=None):
    result = subprocess.run([str(item) for item in command],capture_output=True,text=True,
                            timeout=180, env=env)
    if result.returncode:
        raise RuntimeError("Command failed: "+" ".join(str(s) for s in command)+"\n"
                           +(result.stdout+result.stderr)[-5000:])
    return result.stdout


def audit_godot(asset, executable):
    with tempfile.TemporaryDirectory(prefix="courier-import-") as temp:
        project = Path(temp)
        (project/"project.godot").write_text('config_version=5\n[application]\nconfig/name="Courier Import"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
        (project/"verify.gd").write_text(GODOT_CHECK)
        shutil.copyfile(asset,project/"courier.glb")
        command = [executable,"--headless","--path",project]
        env = dict(os.environ, XDG_DATA_HOME=str(project/"user"), GODOT_SILENCE_ROOT_WARNING="1")
        run(command+["--editor","--import"],env)
        output = run(command+["--script","res://verify.gd"],env)
        for line in output.splitlines():
            if line.startswith("COURIER_IMPORT "):
                result = json.loads(line.removeprefix("COURIER_IMPORT "))
                require(result["bones"] == result["skin_binds"] == len(PARENTS), "engine skin mismatch")
                return result
        raise RuntimeError("Godot did not report imported animation")


def build_rig(out, blender=None, godot=None):
    out = Path(out).absolute()
    if out.exists() or out.is_symlink():
        raise FileExistsError(out)
    out.parent.mkdir(exist_ok=True,parents=True)
    blender = blender or shutil.which("blender52") or shutil.which("blender")
    if not blender:
        raise FileNotFoundError("Blender is required to build the character")
    godot = godot or shutil.which("godot4") or shutil.which("godot")
    worker = Path(__file__).with_name("blender_rig.py").resolve()
    with tempfile.TemporaryDirectory(prefix=".courier-",dir=out.parent) as temp:
        stage = Path(temp)
        base = [blender,"--factory-startup","--background","--threads","1"]
        args = ["--python-exit-code","1","--python",worker,"--"]
        run(base+args+["build",stage])
        run(base+[stage/"courier.blend"]+args+["inspect",stage])
        native = json.loads((stage/"native-inspection.json").read_text())
        glb = audit_glb(stage/"courier.glb")
        engine = audit_godot(stage/"courier.glb",godot) if godot else {"status":"unavailable"}
        report = {"character":"Switchyard Courier", "source":"Original procedural geometry and animation",
                  "rest_height_m":1.79, "forward_gltf":"+Z", "native":native,"glb":glb,"godot":engine}
        (stage/"rig_report.json").write_text(json.dumps(report,indent=2)+"\n")
        out.mkdir()
        try:
            for name in ("courier.blend","courier.glb","rig_report.json"):
                (stage/name).replace(out/name)
        except BaseException:
            shutil.rmtree(out)
            raise
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--blender",help="Path to Blender")
    parser.add_argument("--godot",help="Path to Godot 4 for native import verification")
    args = parser.parse_args()
    result = build_rig(args.out,args.blender,args.godot)
    print(json.dumps({"out":str(args.out),"joints":len(result["glb"]["joints"]),
                      "animations":list(result["glb"]["clips"]),"godot":result["godot"]}))
