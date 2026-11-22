# Integrated Game Lab — v40

The Morning Crossing is a small original, turn-based top-down playable
glassworks scene. Discover the mission at the junction, choose the winch or
the back stairs, and deliver the route chart. A platform affects travel for
workers as well as the player; weather changes its availability. Optional
crate work has its own consequence. Gameplay, the yard and HUD agree on one
authoritative session rather than independent mission flags.

## Run locally

From the checkout, export to a new private path outside the repository:

```sh
python3 -m gameplay.integrated_lab.runner --output ../morning-crossing
```

Open `project.godot` in the exported directory in Godot 4 and run the main
scene, or from that directory run `godot --path .`. No external assets, accounts
or paid services are required. The exported project is a standalone example.

| Control | Keyboard | Controller |
| --- | --- | --- |
| Move one tile | WASD / arrows | D-pad |
| Interact | E / Space | South face button |
| Wait one turn | Q | West face button |
| Journal | J / Tab | North face button |
| Close journal | Esc | East face button |
| Retry (confirm or cancel) | R | Start |

Each accepted action advances simulation time. Rain closes the platform on
turns 8–11 of each twelve-turn cycle; a courier on the closing crossing is
returned to their entry bank. Workers move one grid step per accepted turn.
A cart warns before arrival and cancels if its destination is occupied.
The optional dry-rack task earns 3 credits and chart delivery earns 10, once
each. The stairs remain open throughout. The journal is modal and does not
advance time; it also offers a large-text setting and safe retry confirmation.
Retry resets the scenario and rejects commands from the old session.
Readable environmental landmarks and the HUD support both approaches.

## Repeatable engine verification

```sh
python3 -m gameplay.integrated_lab.runner --output ../crossing-qa --engine
```

The explicit option uses local Godot 4 and Linux network isolation, with two
bounded, separate process runs. It checks real scene and input behavior using
the game's dispatch, exact check coverage, equal structured observations, and
unchanged source files. Export-only is not runtime proof. Reports and both
logs live privately below `reports/`; never commit generated projects or logs.
This is a fixed original scene, not an arbitrary game execution service.

The synthetic traces do not prove enjoyment, visual quality, accessible
experience, frame performance on physical hardware or release readiness.
Review a rendered build, physical controller input, and consenting human play
separately before making production claims.
