"""Catalog locally shipped studio packages and their reviewed media files."""
import json
import struct
import wave
from pathlib import Path

from advanced.build import verify as verify_advanced
from factory.build import verify_package
from frontline.build import verify as verify_frontline
from vertical.build import verify as verify_vertical

PACKAGES = (
    ("demo/first-batch", "Asset batch", "assets"),
    ("world/demo/training_yard", "Training Yard", "world"),
    ("gameplay/demo/combat_yard", "Combat Yard", "gameplay"),
    ("gameplay/demo/seed_238", "Seed 238", "gameplay"),
    ("gameplay/demo/tactical_yard", "Tactical Yard", "gameplay"),
    ("multiplayer/demo/network_arena", "Network Arena", "multiplayer"),
    ("cinematic/demo/nightfall_patrol", "Nightfall Patrol", "cinematic"),
    ("simulation/demo/expedition_world", "Relay Basin", "world"),
    ("simulation/demo/expedition", "Expedition", "simulation"),
    ("openworld/demo/frontier", "Frontier Lab", "openworld"),
    ("unified/demo/expedition", "Unified Expedition", "unified"),
    ("living/demo/frontier", "Living World", "living"),
    ("city/demo/metropolis", "Metropolis", "city"),
    ("vertical/demo/connected_city", "Vertical City", "vertical"),
    ("advanced/demo/advanced_city", "Advanced City", "advanced"),
    ("frontline/demo/frontline_city", "Frontline City", "frontline"),
)

BATCH = "demo/first-batch"
FILM = "cinematic/demo/nightfall_patrol"
MODELS = (
    (BATCH, "supply_crate", "prop"),
    (BATCH, "industrial_barrel", "prop"),
    (BATCH, "road_barricade", "prop"),
    (BATCH, "training_mannequin", "character"),
    (FILM, "animated_actor", "character"),
    (FILM, "city", "environment"),
)


def label(identifier):
    return identifier.replace("_", " ").title()


def animation_names(path):
    with path.open("rb") as stream:
        header = stream.read(20)
        if len(header) != 20:
            return []
        magic, version, total, length, chunk = struct.unpack("<4sIII4s", header)
        if (magic != b"glTF" or version != 2 or total != path.stat().st_size
                or chunk != b"JSON" or length > total - 20):
            return []
        try:
            document = json.loads(stream.read(length))
        except (UnicodeError, ValueError):
            return []
        if not isinstance(document, dict) or not isinstance(document.get("animations"), list):
            return []
        return [clip["name"] for clip in document["animations"]
                if isinstance(clip, dict) and isinstance(clip.get("name"), str) and clip["name"]]


def catalog(root: Path) -> dict:
    root = root.resolve()
    packages = []
    verified = set()
    verifiers = {"vertical": verify_vertical, "advanced": verify_advanced, "frontline": verify_frontline}
    for relative, title, kind in PACKAGES:
        directory = root / relative
        verifier = verifiers.get(kind, verify_package)
        passed = directory.resolve() == directory and not verifier(directory)
        identifier = {"unified": "unified_expedition", "living": "living_world",
                      "vertical": "vertical_city"}.get(kind, directory.name)
        packages.append({"id": identifier, "label": title, "kind": kind,
                         "path": relative, "verified": passed})
        if passed:
            verified.add(relative)

    assets, names, audio = [], set(), []
    for relative, ident, kind in MODELS:
        if relative not in verified:
            continue
        directory = root / relative
        glb = directory / "assets" / (ident + ".glb")
        if not glb.is_file():
            continue
        sources = directory / ("assets" if relative == BATCH else "source")
        files = []
        for path in (glb, sources / (ident + ".blend"), directory / "assets/provenance.json"):
            if path.is_file():
                files.append({"name": path.name, "path": path.relative_to(root).as_posix(),
                              "bytes": path.stat().st_size})
        asset = {"id": ident, "label": label(ident), "kind": kind, "files": files}
        preview = root / "demo/asset-preview.png" if relative == BATCH else directory / "preview.png"
        if preview.resolve() == preview and preview.is_file():
            asset["preview"] = preview.relative_to(root).as_posix()
        assets.append(asset)
        names.update(animation_names(glb))

    if FILM in verified:
        for ident in ("ambience", "footstep", "thunder"):
            path = root / FILM / "assets" / (ident + ".wav")
            try:
                with wave.open(str(path), "rb") as wav:
                    seconds = wav.getnframes() / wav.getframerate()
            except (OSError, EOFError, wave.Error, ZeroDivisionError):
                continue
            audio.append({"id": ident, "label": label(ident), "seconds": seconds,
                          "path": path.relative_to(root).as_posix()})

    return {"assets": assets, "packages": packages,
            "animations": [{"id": name, "label": name} for name in sorted(names)], "audio": audio}
