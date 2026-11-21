# World factory v4 — verification

Environment: Godot 4.7.2, Linux x86-64, headless physics. No exposed GPU.

- Studio regression suite: 25 tests passed.
- Level build, asset import, native scene bake, and headless launch: passed.
- Level manifest inventory and SHA-256 verification: passed.
- Training yard runtime QA: 10/10 checks passed.

| Runtime check | Observed result |
|---|---|
| Placed props | 5 |
| Meshes and colliders | 5 mesh placements, 4/4 expected collider placements |
| Ground contact | 0.00012 m settled feet error |
| Terrain height collision | 0.133 m surface elevation at x=14 |
| Prop physics collision | Barrel collider top at 0.940 m |
| Walking | 2.0 m in 0.5 s (4 m/s) |
| Sprinting | 3.5 m in 0.5 s (7 m/s) |
| Jump and landing | 1.424 m peak; returned to ground |
| Wall collision | Blocked at z=3.450 m with opposing collision normal |
| Goal traversal | Goal triggered at 0.867 m distance |

The machine-readable results are in `training_yard/reports/qa.json`; engine
logs are alongside them. The example uses the original v3 factory assets.
This establishes tested fixture behavior, not universal level correctness.
Rendered appearance, mouse input feel, animation quality, and GPU/device
performance require further human or hardware acceptance.
