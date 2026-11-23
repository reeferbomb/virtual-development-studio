# Optional two-crew Midnight Shift workflow

This optional mode organizes the **existing six roles**, without changing the normal six-agent default profile or silently spawning any worker.

Run from a Graveforge checkout:

```bash
python3 -m command_center.crew_split --project "Dig It" --output ../studio-private/dig-it-dual-crews.json
```

The output is a **private dispatch export**, not an agent session, checkpoint receipt, test pass, task-board mutation or release approval. The normal `command_center.dispatch.default_profile()` remains unchanged. An authorized AI host must independently claim fresh ready tasks before invoking compatible workers; unavailable slots must be reported honestly.

| Crew | Roles | Responsibility |
| --- | --- | --- |
| Visual Realism | Grimbrush (content lead), Madame Glitch (UI/first-person views), Baron Buildgrave (build and rendering budget) | Terrain/vegetation assets, natural material response, textures, lighting, native before/after captures |
| Real-World Physics | Major Mayhem (gameplay lead), Count Blueprint (architecture), Doctor Doomcheck (independent verification) | Gravity, terrain excavation contacts, character grounding, vehicle traction and impacts |

## Integration gates

- Derive both workstreams from one verified source fingerprint and preserve baseline source/release/rollback checkpoints.
- Develop in separate branches or workspaces; share no modified file path without an explicit handoff.
- Physics cannot claim success from appearance alone. Require actual contact, gravity, shovel/collision and vehicle behavior tests.
- Visuals cannot claim game quality from isolated swatches alone. Require above-ground real-game capture and realistic target comparison. Preserve night/dusk and performance.
- Doctor Doomcheck reviews visual regressions independently, while Baron Buildgrave verifies physics build compatibility and runtime budgets.
- Merge only after native gameplay smokes, source hashes, save/recovery checks and a reversible checkpoint. Windows/device validation is separate.
- No model agents are launched by this CLI. A host must provide their actual execution, logs and test receipts.

Tests: `python3 -m unittest tests.test_crew_split -v` from a checkout with tests importable, or `python3 -m unittest discover -s tests -p 'test_crew_split.py' -v`.

The feature adds `command_center/crew_split.py` and an independent unit test, without affecting the established creative/planning or admin modes.
