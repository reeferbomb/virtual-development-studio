#!/usr/bin/env bash
set -euo pipefail

kit="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
blender_bin="${STUDIO_BLENDER:-}"
if [[ -z "$blender_bin" ]]; then
  if command -v blender52 >/dev/null; then
    blender_bin=blender52
  else
    blender_bin=blender
  fi
fi
godot_bin="${STUDIO_GODOT:-godot}"
command -v "$blender_bin"
command -v "$godot_bin"
"$blender_bin" --version | head -n 1
"$godot_bin" --version
probe="$(mktemp -d)"
cp "$kit/probe/"* "$probe/"
printf 'Scratch proof: %s\n' "$probe"
"$blender_bin" -b --factory-startup --python "$probe/export_probe.py" -- "$probe/probe.glb"
"$godot_bin" --headless --path "$probe" --editor --import
"$godot_bin" --headless --path "$probe" --script res://test_import.gd
printf 'STUDIO_SMOKE_PASS\n'
