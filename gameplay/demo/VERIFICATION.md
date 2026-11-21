# Gameplay factory v5 verification

Godot 4.7.2 Linux, headless physics. The source asset batch and v4 level
passed inventory verification; the two new projects built, imported, launched,
and passed package integrity checks. The Python regression suite passed 30/30.

Combat, mission/persistence, and pathfinding GDScript module suites passed for
both projects. The encounter generator is deterministic for the same seed and
produces different guard placement/patrol configurations for different seeds.

## Fixed combat yard: 11/11 integrated checks

- Two actual collision-bearing AI guards spawned; extraction initially locked.
- Autonomous guard patrol moved; another detected the player and inflicted damage (100 to 88 HP).
- Physical wall blocked a shot; unobstructed hitscan reduced guard health.
- Two hits eliminated a guard and advanced the objective.
- Checkpoint wrote successfully and restored health, ammo, actor position and defeated guard.
- All targets defeated; extraction remained incomplete until physical traversal.
- Player reached extraction under the real first-person physics controller.

The build caught a JSON number-type incompatibility. A separate failing
combat round-trip regression test was added, then passed after the fix.
Machine-readable integrated evidence: `combat_yard/reports/gameplay-qa.json`.

## Generated encounter: seed 238

Three guards with unique positions and patrols, validated against the source
level. Import, headless launch and all three module suites passed. Full
mission traversal was not tested for this generated layout.

## Acceptance boundaries

This is an offline, single-player gameplay starter, not a finished shooter.
The bot visuals are capsule placeholders; the weapon is a raycast mechanic,
not a modeled and animated firearm. No hardware rendering, interactive input
feel, network multiplayer or physical device performance acceptance.
