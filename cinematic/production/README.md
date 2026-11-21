# Engine-backed cinematic production

This is the bridge between a Cutscenes Academy exercise and an editable Godot
4 scene. It is independent of the original `cinematic/build.py` factory. The
existing timeline format, sealed demo package, Lab rubric and historical
practice assessments are unchanged.

## First run

From the Graveforge source directory, with Python 3.11+ and Godot 4 installed:

```bash
python3 -m cinematic.production.runner \
  cinematic/production/examples/nightfall_plan.json \
  cinematic/production/examples/nightfall_bindings.json \
  --output ../nightfall-production --engine
godot --path ../nightfall-production
```

Choose a new output directory outside the source checkout for every revision.
The runner never replaces an existing directory. Without `--engine`, it only
exports the project. An export must be imported in Godot before interactive
playback (`godot --headless --path ../nightfall-production --editor --import`).
To change the scene, copy the two example JSON files to your own private
workspace, edit them, and export into a fresh destination.

Press Enter to trigger the cutscene, Space to pause or resume, S to skip and
Escape to interrupt. Arrow keys move the gameplay viewpoint when the cinematic
does not own input. Complete and skip advance the guarded story state;
interruption preserves the initial state and allows retry. Restart the entire
Godot project to watch again after completing or skipping. This is an in-memory
handoff demonstration, not a save system or complete game controller.

## Authoring inputs

1. A Cutscenes Lab submission with integer fps, total frames, duration in ms,
   actor/camera IDs, ordered shots, blocking, dialogue, subtitles, trigger and
   three exits. Validate it with `python3 -m command_center.training_lab_cli
   assess cutscenes path/to/plan.json` before building.
2. A binding document with one entry per declared camera and actor. Match IDs
   exactly. Coordinates are Godot world meters (Y up), and angles are degrees.

```json
{
  "cameras": {
    "wide": {"position": [0, 1.8, 5], "look_at": [0, 1, 0], "fov": 45},
    "close": {"position": [1.5, 1.7, 2], "look_at": [0, 1.3, 0], "fov": 35}
  },
  "actors": {
    "hero": {"position": [0, 0, 0], "rotation_y": 0}
  }
}
```

The above binding fragment requires a matching plan; use the complete
[Third Door](examples/README.md) sample for a first run. The production subset
supports up to 7,200 frames, 120 seconds, eight actors and sixteen cameras.
The `gameplay` camera ID is reserved. The actor library has `idle`, `walk`,
`run`, `aim`, `crouch` and `reload`, bound to real imported clips. The shared
caption and scratch-audio channel permits only one dialogue window at a time;
an actor's blocking windows cannot overlap. Camera and blocking intervals are
start-inclusive/end-exclusive. Placements are static; this slice does not
generate walking paths, dynamic camera splines, props, recorded dialogue or
facial animation. Check the intended scale and composition yourself.

## Evidence and privacy

The fixed runner uses only the original Studio assets and trusted project
templates, not a user-supplied script, plugin or arbitrary GLB. The compiled
plan is data only. Keep plans, generated files and reports outside the public
checkout. Do not upload private cutscene scripts or runtime logs.

The CLI prints a JSON report and saves it to `reports/report.json` in the
generated output. It records the exact source JSON digests, compiled and
copied file inventory, pinned source manifest, separately scoped runtime
status, and (when measured) the engine version and digest-bound QA checks.
The original bytes are checked again after engine execution. Derived Godot
imports and private logs are not source inventory entries.

| Report status | Exit code | Meaning |
| --- | --- | --- |
| `exported` | 0 | Output created; engine QA not requested. |
| `passed` | 0 | Explicit isolated import and runtime checks passed. |
| `failed` | 1 | Runtime or generated-file integrity failed. |
| `unavailable` | 2 | Godot 4 or Linux user/network isolation could not run. |

Input/preflight errors also exit 2 and do not create an output. Failed or
unavailable engine runs retain the private export and diagnostic report.
There is no unisolated fallback for `--engine`. A report is an observation,
not a signed certificate, an authenticated identity, or a full sandbox.

Run the separate, repository-owned caption layout probe against a disposable
generated project, from the repository directory:

```bash
godot --headless --path ../nightfall-production \
  --script "$PWD/cinematic/production/tests/caption_overlay_qa.gd"
```

It checks actual Control-node bounds, literal text, caption clearing and input
pass-through at five viewport sizes; it is not a rendered-font review.

The offline Lab remains a structural assessment. The engine-backed QA uses
actual scene nodes, imported animation, audio-player state and gameplay handoff.
Headless playback does not verify framing, physical-device performance,
recorded dialogue clarity or listener experience. The footstep scratch sample
loops during an active caption window as a playback timing signal, not a human
voice. Export and runtime evidence
are distinct from practice coverage, release readiness and human approval.

The original asset credits and MIT license are retained with the output.
See the [security policy](../../SECURITY.md) and [existing cinematic factory](../../README.md#new-in-v7--original-cinematic-production).

## Reproduce the verification

```bash
python3 -m unittest discover -s tests -p 'test_cinematic_production_*.py' -v
```

The v32 Nightfall sample ran through a clean Godot 4.7.2 import and passed all
14 runtime checks, including 62 sampled timeline frames and comparisons with
a separately evaluated imported skeleton. The focused suite also runs a
minimal alternate plan with reordered, adjacent equal-text cues, unused actor
bindings and empty cue ranges. Engine tests explicitly skip if the local
engine or Linux network isolation is unavailable; absence of those tests is
not a passing runtime report.
