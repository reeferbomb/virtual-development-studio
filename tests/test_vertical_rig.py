import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vertical.rig import BinaryGltf, CLIPS, PARENTS, audit_glb, build_rig


class RigOutputTests(unittest.TestCase):
    def test_existing_output_keeps_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)
            sentinel = dest/"work.blend"
            sentinel.write_text("keep")
            with self.assertRaises(FileExistsError):
                build_rig(dest)
            self.assertEqual(sentinel.read_text(),"keep")

    def test_worker_failure_does_not_publish_output(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                build_rig(Path(temp)/"result",str(Path(temp)/"missing-blender"))
            self.assertEqual(list(Path(temp).iterdir()),[])


@unittest.skipUnless(shutil.which("blender52") or shutil.which("blender"), "requires Blender")
class RigIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.out = Path(cls.temp.name)/"build"
        cls.report = build_rig(cls.out)

    def test_reopened_native_mesh_and_animation(self):
        native = self.report["native"]
        self.assertEqual(native["bones"],len(PARENTS))
        self.assertGreater(native["multi_weight_vertices"],100)
        self.assertEqual(set(native["peak_vertex_motion_m"]),set(CLIPS))
        self.assertTrue(all(v>.001 for v in native["peak_vertex_motion_m"].values()))
        self.assertEqual(self.report,json.loads((self.out/"rig_report.json").read_text()))
        self.assertTrue((self.out/"courier.blend").exists())

    def test_exported_skin_and_moving_clips(self):
        glb = audit_glb(self.out/"courier.glb")
        self.assertEqual(set(glb["joints"]),set(PARENTS))
        self.assertGreater(glb["triangles"],1000)
        self.assertGreater(glb["multi_weight_vertices"],100)
        self.assertEqual(set(glb["clips"]),set(CLIPS))
        for clip in glb["clips"].values():
            self.assertGreater(len(clip["moving_joints"]),0)
            self.assertGreater(clip["seconds"],.5)

    @unittest.skipUnless(shutil.which("godot4") or shutil.which("godot"), "requires Godot 4")
    def test_godot_editor_import_and_playback(self):
        engine = self.report["godot"]
        self.assertEqual(engine["bones"],len(PARENTS))
        self.assertEqual(engine["skin_binds"],len(PARENTS))
        self.assertEqual(set(engine["moving_bones"]),set(CLIPS))
        self.assertTrue(all(count>0 for count in engine["moving_bones"].values()))

    def test_reject_zero_weights_on_disk(self):
        path = self.out/"courier.glb"
        glb = BinaryGltf(path)
        doc = glb.doc
        weights = doc["meshes"][0]["primitives"][0]["attributes"]["WEIGHTS_0"]
        accessor = doc["accessors"][weights]
        self.assertEqual(accessor["componentType"],5126)
        view = doc["bufferViews"][accessor["bufferView"]]
        raw = bytearray(path.read_bytes())
        json_chunk_size = struct.unpack_from("<I",raw,12)[0]
        address = 28+json_chunk_size+view.get("byteOffset",0)+accessor.get("byteOffset",0)
        struct.pack_into("<4f",raw,address,0,0,0,0)
        tampered = Path(self.temp.name)/"incorrect-weights.glb"
        tampered.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,"weights must sum to one"):
            audit_glb(tampered)

    def test_reject_missing_clip(self):
        path = self.out/"courier.glb"
        raw = path.read_bytes()
        doc = BinaryGltf(path).doc
        doc["animations"][0]["name"] = "bogus"
        chunk = json.dumps(doc,separators=(",",":")).encode()
        chunk += b" " * (-len(chunk) % 4)
        binary = raw[20+struct.unpack_from("<I",raw,12)[0]:]
        tampered = Path(self.temp.name)/"incorrect-clips.glb"
        tampered.write_bytes(struct.pack("<4sIII4s",b"glTF",2,20+len(chunk)+len(binary),
                                         len(chunk),b"JSON")+chunk+binary)
        with self.assertRaisesRegex(ValueError,"animation clips"):
            audit_glb(tampered)


if __name__ == "__main__":
    unittest.main()
