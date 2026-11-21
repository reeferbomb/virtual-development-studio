"""Read-only inventory and provenance checks for an asset directory.

Place provenance.json at the asset root. Its top-level array contains one
object per material file, with string fields:
path (exact relative POSIX path), source (URL, creator or creation record),
license (usage terms or identifier), and attribution (credit line or an
explicit "not required" when supported by the license).

Verified Godot 4 GLB and WAV import sidecars use their source file's record.
They remain in the inventory and count toward both file and total budgets.
Other import formats require explicit records.
"""
import argparse
import configparser
import hashlib
import json
import os
import re
import stat
from contextlib import ExitStack
from pathlib import Path, PurePosixPath

FORMATS = {
    "scene": {".glb", ".gltf", ".fbx", ".obj", ".dae", ".tscn", ".scn"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".svg", ".exr", ".tga", ".ktx"},
    "audio": {".ogg", ".wav", ".mp3"},
    "source": {".blend", ".kra", ".psd"},
    "companion": {".bin", ".mtl", ".tres", ".res"},
}

GODOT_IMPORT_FORMATS = {".glb": ("scene", "PackedScene", "scn"),
                        ".wav": ("wav", "AudioStreamWAV", "sample")}
MAX_IMPORT_METADATA_BYTES = 64 * 1024


def has_godot_project(fd):
    try:
        info = os.stat("project.godot", dir_fd=fd, follow_symlinks=False)
        return stat.S_ISREG(info.st_mode)
    except OSError:
        return False


def matches_godot_import(directory_fd, name, project_source):
    """Recognize the single-destination Godot 4 layouts used by the Studio."""
    layout = GODOT_IMPORT_FORMATS.get(project_source.suffix.lower())
    if layout is None:
        return False
    importer, resource_type, extension = layout
    source_uri = "res://" + project_source.as_posix()
    config = configparser.ConfigParser(delimiters=("=",), interpolation=None)
    config.optionxform = str
    try:
        # Godot uses the MD5 of the project URI as a cache filename discriminator.
        cache_id = hashlib.md5(source_uri.encode(), usedforsecurity=False).hexdigest()
        destination = f"res://.godot/imported/{project_source.name}-{cache_id}.{extension}"
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(name, flags, dir_fd=directory_fd), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return False
            raw = stream.read(MAX_IMPORT_METADATA_BYTES + 1)
        if len(raw) > MAX_IMPORT_METADATA_BYTES or b"\x00" in raw:
            return False
        config.read_string(raw.decode("utf-8"))
        if set(config.sections()) != {"remap", "deps", "params"} or config.defaults():
            return False
        # Only recognize the JSON-compatible property values emitted by these
        # importers. More complex Godot variants can have explicit records.
        properties = {section: {key: json.loads(value) for key, value in config[section].items()}
                      for section in config.sections()}
        remap = properties["remap"]
        uid = remap.get("uid")
        return (isinstance(uid, str) and re.fullmatch(r"uid://[a-z0-9]+", uid) is not None and
                remap.get("importer") == importer and remap.get("type") == resource_type and
                remap.get("path") == destination and
                properties["deps"] == {"source_file": source_uri, "dest_files": [destination]} and
                bool(properties["params"]))
    except (OSError, ValueError, KeyError, RecursionError, configparser.Error):
        return False


def audit(root, max_file_bytes=None, max_total_bytes=None):
    report = {"files": [], "total_bytes": 0, "errors": [], "warnings": []}

    def issue(level, code, path):
        report[level].append({"code": code, "path": str(path)})

    root = Path(root).absolute()
    names = {}
    import_sources = {}
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        issue("errors", "secure_directory_traversal_unavailable", root)
        return report
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    def walk(directory, fd, project_root):
        try:
            entries = sorted(os.listdir(fd))
        except OSError:
            issue("errors", "unreadable_directory", directory)
            return
        if "project.godot" in entries and has_godot_project(fd):
            project_root = root / directory
        for name in entries:
            entry = directory / name
            relative = entry.as_posix()
            key = relative.casefold()
            if key in names:
                issue("errors", "case_collision", relative)
            names.setdefault(key, relative)
            try:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except OSError:
                issue("errors", "unreadable_entry", relative)
                continue
            if stat.S_ISLNK(info.st_mode):
                issue("warnings", "skipped_symlink", relative)
            elif stat.S_ISDIR(info.st_mode):
                try:
                    child = os.open(name, directory_flags, dir_fd=fd)
                except OSError:
                    issue("errors", "unreadable_directory", relative)
                    continue
                try:
                    walk(entry, child, project_root)
                finally:
                    os.close(child)
            elif not stat.S_ISREG(info.st_mode):
                issue("warnings", "skipped_special_file", relative)
            elif relative != "provenance.json":
                category = next((group for group, exts in FORMATS.items()
                                 if entry.suffix.lower() in exts), "other")
                if entry.suffix == ".import" and project_root is not None:
                    source = entry.with_suffix("")
                    project_source = (root / source).relative_to(project_root)
                    if matches_godot_import(fd, name, project_source):
                        category = "godot_import"
                        import_sources[relative] = source.as_posix()
                report["files"].append({"path": relative, "bytes": info.st_size,
                                        "category": category})
                report["total_bytes"] += info.st_size
                if category == "other":
                    issue("warnings", "unclassified_format", relative)
                if max_file_bytes is not None and info.st_size > max_file_bytes:
                    issue("errors", "file_budget_exceeded", relative)

    with ExitStack() as stack:
        try:
            root_fd = os.open(root.anchor, directory_flags)
            stack.callback(os.close, root_fd)
            ancestor = Path(root.anchor)
            project_root = None
            for component in root.parts[1:]:
                if has_godot_project(root_fd):
                    project_root = ancestor
                if stat.S_ISLNK(os.stat(component, dir_fd=root_fd, follow_symlinks=False).st_mode):
                    issue("errors", "symlink_root", root)
                    return report
                root_fd = os.open(component, directory_flags, dir_fd=root_fd)
                stack.callback(os.close, root_fd)
                ancestor /= component
        except OSError:
            issue("errors", "invalid_root", root)
            return report
        walk(Path("."), root_fd, project_root)
        if max_total_bytes is not None and report["total_bytes"] > max_total_bytes:
            issue("errors", "total_budget_exceeded", ".")
        manifest = root / "provenance.json"
        try:
            if not stat.S_ISREG(os.stat(manifest.name, dir_fd=root_fd, follow_symlinks=False).st_mode):
                raise ValueError()
            manifest_fd = os.open(manifest.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                  dir_fd=root_fd)
            with os.fdopen(manifest_fd, encoding="utf-8") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError()
                rows = json.load(stream)
            if not isinstance(rows, list):
                raise ValueError()
        except (OSError, ValueError, RecursionError):
            issue("errors", "missing_or_invalid_manifest", manifest.name)
            return report
    files = {item["path"] for item in report["files"]}
    seen = set()
    for index, row in enumerate(rows):
        path = row.get("path") if isinstance(row, dict) else None
        if not isinstance(path, str) or not path or path.startswith("/") or (
                "\\" in path or ".." in PurePosixPath(path).parts or
                PurePosixPath(path).as_posix() != path or path == "."):
            issue("errors", "invalid_manifest_path", f"row {index + 1}")
            continue
        if path in seen:
            issue("errors", "duplicate_record", path)
        seen.add(path)
        if path not in files:
            issue("warnings", "stale_record", path)
        for field in ("source", "license", "attribution"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                issue("errors", f"missing_{field}", path)
    for path in sorted(files - seen):
        source = import_sources.get(path)
        if source in files and source in seen:
            continue
        issue("errors", "missing_provenance", path)
    return report


def budget(value):
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("expected nonnegative bytes")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    parser.add_argument("--max-file-bytes", type=budget)
    parser.add_argument("--max-total-bytes", type=budget)
    args = parser.parse_args()
    result = audit(args.root, args.max_file_bytes, args.max_total_bytes)
    print(json.dumps(result, indent=2))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
