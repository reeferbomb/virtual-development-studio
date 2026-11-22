# Graveforge Living World Lab — v39

Six original, independently reusable Godot 4 fixtures demonstrate decision
making, squad coordination, procedural missions, reactive encounters, living
NPC schedules and mission presentation. They are a development laboratory,
not a complete connected open-world game. Each fixture owns its small scene
and its state, with a distinct set of scripted runtime checks.

From the Studio checkout on a Linux workstation:

```sh
python3 -m gameplay.world_lab.runner --output ../living-world-lab --engine
```

Choose a new private output directory whose parent already exists, outside the
public checkout. Omit `--engine` to export only; that is not runtime proof.
The explicit execution mode requires local Godot 4 and Linux network
isolation. The original scripts can also be studied in Godot on Windows;
automated execution is verified on Linux only.

| Fixture | Production pattern |
| --- | --- |
| Decision | Competing goals, bounded observations, route cost, hysteresis and safety preemption |
| Squad | Shared observations with expiration, distinctive roles, unique cover slots, movement and reassignment |
| Encounters | Seeded selection, warning, eligible spawns, wave budget and cooldown |
| Journal | Discovered objectives, branch gating, optional goals, focus, retry and readable interface state |
| Citizens | Day/night routines, routed commutes, service capacity, weather disruption and recovery |
| Missions | Seeded dependency graph, route/resource validation, progression and bounded recovery |

The runner exports only the reviewed fixed template; no arbitrary scene,
project, script, names, assets, or plugins are accepted. It runs two separate
isolated Godot processes with bounded time and output. The two runs must both
pass every exact check, use the same engine version, and return equal structured
reports (including observations and metrics) before the lab reports `passed`.
Original source files are checked after each run. The source inventory and
repeat digest bind the results but are not signatures or authentication. Each
fixture must return the root scene-tree child count to its original value.

Private output:

- `reports/report.json`: machine-readable source identity, each run's checks,
  metrics, log hash and repeat identity when verified.
- `reports/qa.log` and `reports/qa-repeat.log`: separate bounded engine outputs.

Exit code 0 means successful export or successful repeated runtime QA; 1 means
failed or inconsistent runtime QA; 2 means unavailable export or engine
prerequisites. A missing repeat cannot become a pass. A deterministic result
on this fixture and this Godot version is not a guarantee across engines,
platforms, arbitrary seeds or scenarios.

For production, choose a policy appropriate to the game, integrate it into the
authorized project, test navigation and collision in the real world geometry,
profile target hardware, test the actual controller interface, and review with
consenting players. Do not treat scripted behavior as evidence of fun, fair
difficulty, rendered quality or release readiness. No human telemetry or
commercial game data is collected. Keep generated projects and logs private.
