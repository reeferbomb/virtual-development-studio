# Cinematic factory v7 — verification

Blender 5.2.4 LTS and Godot 4.7.2 headless on Linux. All visuals and sound
assets are original procedural outputs, with editable Blender sources.

## Art and animation

- City seed 237: 24 × 30 m set, six facades, eight lanterns, 17 batched meshes,
  14 materials, 9,588 triangles. Blender-side GLB validation passed.
- Character: 16 joints, skinned geometry, six exported actions. Actual moving
  quaternion channels by clip: Idle 2, Walk 9, Run 9, Aim 2, Crouch 7, Reload 6.
- Godot imported all six clips by name, and observed bone rotations changing
  between timeline samples.
- CPU-rendered Blender preview: 960 × 540, mean luminance 122.17 and standard
  deviation 53.34 (8-bit grayscale). Automated nonblank raster check passed.
  The visual review shows a stylized street and mannequin; art polish,
  building interiors, distant backdrop and character gear remain limited.

## Audio

| Original sound | Duration | Peak (normalized) | RMS |
|---|---:|---:|---:|
| Ambience | 5.00 s | 0.445 | 0.135 |
| Footstep | 0.42 s | 0.634 | 0.089 |
| Thunder | 3.00 s | 0.673 | 0.078 |

22,050 Hz mono PCM16; deterministic generation, clipping, repeatability,
loop boundary and WAV structure checks passed. Godot loaded the audio into
3D spatial sources. Actual audible playback is not asserted in headless QA.

## Sequence and regression

39/39 Python tests passed. Godot import and launch passed; all 11 fixture
checks passed: city, skeleton, clip list, animated bone motion, camera dolly,
actor movement, shot cut, weather, spatial sound, endpoint, and rewind.

The full Godot QA record, Blender asset validation and CPU render logs are in
`nightfall_patrol/reports/`. Package inventory verification passed. The v6
multiplayer, v5 fixed gameplay, and v4 world packages also verified unchanged.

This is not a live Godot screenshot, real-time hardware benchmark, final
animation quality review, or production-ready gameplay level.
