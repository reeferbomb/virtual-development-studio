"""Check the exported animation library using only the Python standard library."""
import json
import struct
import sys
from pathlib import Path

CLIPS = {"Idle", "Walk", "Run", "Aim", "Crouch", "Reload"}


def verify(directory):
    blob = (directory / "animated_actor.glb").read_bytes()
    magic, version, length, size, kind = struct.unpack_from("<4sIIII", blob)
    assert (magic, version, length, kind) == (b"glTF", 2, len(blob), 0x4E4F534A)
    doc = json.loads(blob[20:20+size])
    binary = memoryview(blob)[28+size:]
    assert len(doc["skins"][0]["joints"]) == 16
    assert {a["name"] for a in doc["animations"]} == CLIPS
    for clip in doc["animations"]:
        moving = []
        for channel in clip["channels"]:
            if channel["target"]["path"] != "rotation":
                continue
            sampler = clip["samplers"][channel["sampler"]]
            acc = doc["accessors"][sampler["output"]]
            view = doc["bufferViews"][acc["bufferView"]]
            assert acc["componentType"] == 5126 and acc["type"] == "VEC4"
            offset = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            qs = [struct.unpack_from("<4f", binary, offset+i*view.get("byteStride", 16))
                  for i in range(acc["count"])]
            if any(abs(sum(x*y for x, y in zip(qs[0], q))) < .999999 for q in qs[1:]):
                moving.append(doc["nodes"][channel["target"]["node"]]["name"])
        assert len(set(moving)) >= 2, clip["name"]
        print(clip["name"], len(moving), "moving rotation channels")
    assert (directory / "animated_actor.blend").stat().st_size > 1024


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
