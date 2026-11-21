"""Read-only inventory and provenance checks for an asset directory.

Place provenance.json at the asset root. Its top-level array contains one
object per regular file (excluding the manifest), with string fields:
path (exact relative POSIX path), source (URL, creator or creation record),
license (usage terms or identifier), and attribution (credit line or an
explicit "not required" when supported by the license).
"""
import argparse
import json
import os
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


def audit(root, max_file_bytes=None, max_total_bytes=None):
    report = {"files": [], "total_bytes": 0, "errors": [], "warnings": []}

    def issue(level, code, path):
        report[level].append({"code": code, "path": str(path)})

    root = Path(root).absolute()
    names = {}
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        issue("errors", "secure_directory_traversal_unavailable", root)
        return report
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    def walk(directory, fd):
        try:
            entries = sorted(os.listdir(fd))
        except OSError:
            issue("errors", "unreadable_directory", directory)
            return
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
                    walk(entry, child)
                finally:
                    os.close(child)
            elif not stat.S_ISREG(info.st_mode):
                issue("warnings", "skipped_special_file", relative)
            elif relative != "provenance.json":
                category = next((group for group, exts in FORMATS.items()
                                 if entry.suffix.lower() in exts), "other")
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
            for component in root.parts[1:]:
                if stat.S_ISLNK(os.stat(component, dir_fd=root_fd, follow_symlinks=False).st_mode):
                    issue("errors", "symlink_root", root)
                    return report
                root_fd = os.open(component, directory_flags, dir_fd=root_fd)
                stack.callback(os.close, root_fd)
        except OSError:
            issue("errors", "invalid_root", root)
            return report
        walk(Path("."), root_fd)
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
