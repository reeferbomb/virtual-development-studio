# Studio v3.0 acceptance — 2026-11-20

Blender 5.2.4 LTS executed all four recipes from the normalized batch JSON.
Godot 4.7.2 imported the real GLB files and instantiated the meshes.

| Asset | Triangles (Godot) | Materials | Bones | Animation |
|---|---:|---:|---:|---|
| supply_crate | 792 | 3 | — | — |
| industrial_barrel | 1408 | 3 | — | — |
| road_barricade | 704 | 3 | — | — |
| training_mannequin | 3096 | 2 | 16 | Idle |

- All four imported bounds have foot/base minimum Y = 0.
- Character import: one skinned mesh, one Skeleton3D, 16 bones, height 1.7m,
  one nonempty imported Idle animation.
- Forced 1-triangle limit on the crate: QA rejected with exit code 1 and
  "Triangle budget exceeded." as expected.
- 19 automated regression tests passed, including unsafe IDs, duplicate
  IDs, invalid recipe/budgets, output collisions, and tampered package bytes.
- Batch inventory, license-record coverage, and SHA-256 integrity: passed.
- Three Astra specialists contributed code: procedural prop recipes,
  character and animation recipe, and independent engine-side validation.
- The actual four exported GLBs were imported back into Blender and
  rendered in a CPU Cycles preview. The lead visually inspected the image:
  recognizable starter assets, grounded with distinct silhouettes.
- Art-direction approval, animation deformation during gameplay, collision
  behavior, and real target-device performance are pending. No existing
  game was changed.

The task dashboard is a historical snapshot. Corresponding run logs:

- evidence/regression.log: 24890c4d4088d033fd46c89eb395440962d53f3ac7085af66a1634b5c96218df
- evidence/integrity.log: 3602f8e345b01d8dc18764e794d601c5e0cf074466a1baa9058af12386117abf

The original batch reports are under first-batch/reports/ and its manifest
records the complete inventory. Verify with
`python3 factory/build.py --verify demo/first-batch` from the toolkit root.
