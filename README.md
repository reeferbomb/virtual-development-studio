# Graveforge Studios — Production Intelligence v37.0

**A free, open-source game development studio toolkit.**

## What is Graveforge Studios?

Imagine having a small game studio inside your computer. You are the creative
director: you decide what kind of game you want to make. Graveforge helps you
organize the work, create starting assets and playable prototypes, build
projects, spot problems and keep track of what has actually been finished.

It is designed for solo developers, small teams, beginners learning game
development, and people working with AI coding assistants.

Graveforge (formerly Virtual Development Studio) works alongside tools such as
Godot (a game engine) and Blender (a 3D modeling and animation program).
It is **not** a replacement for either tool, nor a button that instantly turns
an idea into a finished commercial game. Think of it as a workshop, project
manager and production checklist in one place.

### What can I do with it?

- **Start a game:** choose a built-in template for an environment, gameplay
  prototype, multiplayer arena, cinematic, city or other supported project.
- **Make assets:** use built-in generators to create sample models,
  materials, animations, sounds and environments. You can refine them in
  your normal game development tools.
- **Plan development:** break a game into smaller jobs, decide what comes
  first, assign jobs to specialists and keep track of unfinished work.
- **Build and test:** generate a project, read its build logs, check assets
  and record bugs. A build is a generated set of game or asset files.
- **Learn game development:** study forty training topics and try practical
  exercises in the Academy and Lab, including game design, coding, 3D
  modeling, textures, storytelling, animation, testing, fun, replayability
  and visual quality.
- **Keep progress organized:** save checkpoints, review completed work and
  maintain a history of verified builds and release candidates.

## Getting started — no coding required to explore

### 1. Download Graveforge

On the [GitHub repository](https://github.com/reeferbomb/virtual-development-studio),
select the green **Code** button, then **Download ZIP**. Extract the ZIP into
a folder of your choice. If you already use Git, you can instead run:

```bash
git clone https://github.com/reeferbomb/virtual-development-studio.git
cd virtual-development-studio
```

### 2. Get the tools you need (Linux)

The documented local setup uses Linux and **Python 3.11 or newer**. Python runs
the dashboard. Install [Godot 4](https://godotengine.org/) and
[Blender](https://www.blender.org/) separately if you want to generate and run
game projects or assets. Some factories require particular versions or extra
dependencies; see the technical instructions below for each factory.
The command center looks for the `godot` executable and either `blender52`
or `blender` on your command path (PATH).

You can explore the dashboard, planning tools and Lab without an AI account,
API key or game-engine build. Native Windows and macOS support is not
established by this Linux quick start.

### 3. Open the studio

Open a terminal in the extracted Graveforge folder (the one containing this
README). Type the following command and press Enter:

```bash
python3 -m command_center.server --workspace ../studio-workspace
```

Keep that terminal open. In your web browser, visit
[http://127.0.0.1:8765](http://127.0.0.1:8765).

This opens the **Command Center**, the studio's local dashboard.
It runs on your own computer, not on a public website. The new
`studio-workspace` folder sits next to the downloaded source folder and
holds your saved projects and build output. When you finish, let running
builds finish and press Ctrl+C in the terminal to stop the dashboard.

### 4. Try your first project

For example, suppose you want to make a small first-person exploration game.

1. Open **Projects**, select **+ New project**, enter a name such as
   `My First Game`, select a World project type and choose **Create project**.
2. Open **Workspace** to inspect the starting level template and its settings.
   The specification (spec) is a file of settings that describes what to build.
   World and cinematic templates also offer visual editing controls.
3. When the settings are saved and the required tools are installed, choose
   **Queue build**. Visit **Build queue** to see progress, logs and the result.
   Generated files are stored in the separate workspace under
   `jobs/<job-id>/output/`.
4. Open **Planning** to review a proposed series of development tasks.
   Apply the plan only if it fits your idea. Use **Team** to track and
   assign work.
5. Open **Supervisor** and **Quality** to see what passed, what failed and
   what still needs checking. Open the generated Godot project and playtest
   it yourself before treating it as a finished game.
6. Use **Releases** to keep a verified build as an active local release
   candidate when ready. This does not publish your game to the internet.

This produces a starting point for development, not a complete custom FPS.

### Just want to learn?

Open **Training** to read the forty learning tracks. Open **Lab**, choose an
exercise, select **Use example**, then **Assess submission**. The studio shows
which checks passed and why. Change the example to try your own solution,
and use **Download assessment JSON** to save the result if you want to keep it.
JSON is a text format for structured data. The Lab checks measurable properties;
passing an exercise is not the same as mastering a skill or training an AI model.

Have a 3D model or texture you want to check? The asset validation commands
below generate a report of measurable properties and any failed limits. In
the Lab, open the artifact report viewer and select the saved JSON file to
read the results without uploading it. A passing report is one step toward
using an asset in a game, not a substitute for looking at it and playtesting.

With v29, you can also explicitly record an assessed submission under a
specialist role, keep its original data and review it later from the Lab's
private practice history. A different role can accept a passing new submission
or reject it with a note. A teaching example cannot earn reviewed practice
coverage. Nothing is recorded simply by choosing an exercise or assessing it.

## Meet the Midnight Shift — your optional AI-assisted team

Graveforge defines six specialist roles so a lead developer can divide a
project into manageable jobs.

| Specialist | Plain-English role |
| --- | --- |
| Count Blueprint | Plans how the game and its systems fit together. |
| Major Mayhem | Works on gameplay, controls, rules and mechanics. |
| Doctor Doomcheck | Tests features, looks for bugs and checks evidence. |
| Madame Glitch | Works on menus, HUDs and player-facing interfaces. |
| Grimbrush | Works on models, art, animation, textures and other content. |
| Baron Buildgrave | Manages builds, packaging and production operations. |

The default dispatch profile requests five GPT-6.2 Astra Ultra workers and
one GPT-6.2 Sol Max worker in parallel on a compatible host.

**How do I activate the AI team?** You need an AI development environment
that can read the repository, work on your files and launch the supported
agents. Give it the Graveforge repository and your project, have it read
[AGENTS.md](AGENTS.md), and say something like:

> Activate Graveforge Studios. Help me build a small first-person exploration
> game. Plan the work, use the Midnight Shift for independent tasks, test
> each feature and show me the results. Preserve my existing work.

For an existing project, provide its actual folder or repository and describe
what you want improved. The lead can use Team's dispatch exports to send
precise assignments to an authorized external host.

The dashboard itself **does not run AI models, contact a model API or
automatically spawn agents**. Its local tools work independently. AI model
access, parallel worker availability, costs and session limits depend on
your external host. Private API keys and project files are not included in
this public repository. Keep your own credentials and workspace separate;
see [SECURITY.md](SECURITY.md).

## Where do I go in the dashboard?

| Tab | What it means |
| --- | --- |
| Projects / Workspace | Create projects and edit their starting settings. |
| Asset catalog | Browse sample assets and their source information. |
| Build queue / Releases | Generate files, track build results and manage verified local packages. |
| Planning / Sprint | Decide what needs to be done next. |
| Team / Operations | Assign jobs and review work handed back by specialists. |
| Coordination / Portfolio | See dependencies and workloads across projects. |
| Supervisor / Quality | Investigate problems and see what still needs to be verified. |
| Training / Lab | Read production lessons and try measured exercises. |

## Technical reference

The remaining sections document the version history, commands, supported
factories, integration interfaces and verification procedures. Original Studio
code and bundled original test assets are MIT-licensed; see [LICENSE](LICENSE).
Godot, Blender and other external assets retain their respective licenses.
For contributions see [CONTRIBUTING.md](CONTRIBUTING.md), and for release
history see [CHANGELOG.md](CHANGELOG.md).

## New in v37 — production intelligence

The Studio now has six offline production diagnostics and a private report
viewer in the **Intelligence** tab. Analyze measured build/encounter balance,
anonymous aggregate playtest observations, frame pacing, localized interface
geometry and focus, audio mix/cues, and build footprint before deciding on
iterations. See the [Production Intelligence guide](command_center/PRODUCTION_INTELLIGENCE.md)
for input schemas, examples, workflow and limits.

```sh
python3 -m command_center.production_intelligence_cli example > ../capture-example.json
python3 -m command_center.production_intelligence_cli analyze ../capture-example.json > ../intelligence-report.json
```

These are advisory observations, not release gates or automatic telemetry.
Missing domains are reported explicitly. Keep all real captures and reports
outside this public checkout. All 40 Academy exercises and prior production
capabilities remain unchanged.

## New in v36 — game feel and presentation

Six additional disciplines teach studio specialists to design, compare and
verify distinct playstyles, HUD/menu styles, polished startup and recovery,
art and visual styles, sound/music, and effects. Fallout 3, Fallout: New Vegas
and Fallout 4 are studied separately as public references for original RPG
systems. Read the [Game Feel Academy](command_center/GAME_FEEL_ACADEMY.md)
and six linked production studies for the practical workflow and sources.

- Combat, stealth, social, exploration, crafting and hybrid routes.
- Minimal, tactical, diegetic, retro, RPG and strategy interface approaches.
- Responsive startup, accessibility settings, safe save and recovery states.
- Cohesive realistic, stylized, retro and other visual languages.
- Original or licensed SFX, spatial audio, dynamic music and mix priority.
- Readable and bounded VFX with timing, budgets and accessibility review.

All 34 previous exercises, private evidence and production capabilities remain
intact. Actual quality, accessibility and performance require real review;
the structured Academy does not upload recordings or train model weights.

## New in v35 — reference games and interface excellence

Six new tracks and original structured exercises study the Mass Effect trilogy,
The Darkness, Soul Reaver, Call of Duty, Battlefield, Naughty Bear, GTA, Shenmue,
Majora's Mask, Mario, Sonic, Ocarina of Time, From Dust and Civilization
Revolution, plus advanced HUD and UI design. See the [reference syllabus and
interface acceptance guide](command_center/REFERENCE_GAME_ACADEMY.md), including
title-specific primary sources, original design prompts and production checks.

- Narrative continuity, context-dependent abilities and dual-state exploration.
- Combat responsiveness, combined arms and systemic NPC reactions.
- Living world schedules, escalation and time resets.
- Traversal, momentum, item-gated exploration and puzzle progression.
- Terrain simulation, consequences and strategic choices.
- Game HUD and menu readability, handheld/controller support, feedback,
  interface accessibility, visual hierarchy and recovery states.

These are original instructional exercises, not cloned game assets or model
weights. All 28 previous exercises and production capabilities remain intact.
Earlier practice records remain historical; no personal data, new provider
credentials, or paid dependencies are required.

## New in v34 — story and performance academy

Six original practice exercises extend the previous twenty-two:

| Discipline | What specialists practice |
| --- | --- |
| Motion design | Locomotion, transitions, contact, root motion and action timing |
| Character performance | Facial acting, gesture, gaze and retargeting |
| Environmental storytelling | Physical clues, chronology, inference and alternate routes |
| Diegetic narrative | Layered visual and audible clues, discovery and accessibility |
| Voice direction | Casting, delivery, pronunciation, rights and take selection |
| Voice integration | Reactive speech, interruptions, synchronization and localization |

Study developer-documented methods and original production checklists in the
[Story and Performance field guide](command_center/STORY_AND_PERFORMANCE.md).
Training dispatch supplies role-specific workflows; Lab accepts original
bounded JSON practice, not source recordings, game files or personal data.
Actual motion, storytelling comprehension and voice quality require separate
engine playback, listening and human review. All previous exercises remain
intact; older records remain historical. No new dependencies or permissions.

## New in v33 — player experience academy

The studio now teaches designing for enjoyable and memorable play, not just
working features. Six new subjects supplement the existing sixteen:

| Discipline | What specialists practice |
| --- | --- |
| Player enjoyment | Meaningful choices, understandable goals, feedback and challenge |
| Replayability | Distinct viable approaches and meaningful variation without forced grind |
| Player research | Evidence-based diagnosis of enjoyment, boredom and frustration |
| Visual direction | Coherent style, reference targets and actual gameplay review |
| Visual readability | Clear hierarchy, contrast, cues and accessible composition |
| Experience iteration | Compare performance, responsiveness and quality regressions |

Learn more in the [Player Experience field guide](command_center/PLAYER_EXPERIENCE.md).
Open Training, filter by specialist, then practice a new subject in Lab.
To run the synthetic teaching examples offline:

```bash
python3 -m command_center.training_lab_cli examples
```

Dispatch includes applicable workflows automatically; exercises are only run
when explicitly assigned. The exercises check structured evidence and
simulated scenarios. Real fun, aesthetic quality and player responses require
real playtesting and visual review; no telemetry is automatically collected.
Lab v3 preserves all previous exercises but older practice records stay
historical, not current coverage. No new dependencies or permissions.

## New in v32 — engine-backed cinematic production

Turn a cutscene Lab plan into an editable Godot project with the new local
production runner. The Lab verifies your edit on paper; the runner adds real
camera and actor placements and exercises the imported animation, captions,
audio cue timing and handoff to a small gameplay control demonstration.
The established cinematic factory, all sixteen Academy tracks and the
Midnight Shift dispatch profile remain unchanged.

Try the original Nightfall production example from the repository directory:

```bash
python3 -m cinematic.production.runner \
  cinematic/production/examples/nightfall_plan.json \
  cinematic/production/examples/nightfall_bindings.json \
  --output ../nightfall-production --engine
godot --path ../nightfall-production
```

Use Enter to begin, Space to pause/resume, S to skip and Escape to interrupt.
The arrow keys move the gameplay viewpoint before and after the edit.
Interruption preserves the starting story state so you can try again; completion
and skip advance the state and prevent the same trigger from firing twice.
The generated scene uses original bundled city and mannequin assets, real
animation clips and a placeholder audio cue, not recorded dialogue or lip sync.
The v32 workstation exposes Godot 4.7.2 and Blender 4.3.2; this runner does not
need to regenerate the bundled assets in Blender.

Without `--engine`, the runner exports the project only. The runtime report
is separate from the original data-only Lab assessment and does not record
Academy practice, approve a release, or replace a human visual/audio review.
The Lab's Cutscenes exercise links to these instructions. See the
[production guide](cinematic/production/README.md) for the binding format,
private output and evidence limitations.

## New in v31 — cinematic and development workflow academy

The Academy now contains sixteen production playbooks and corresponding
hands-on JSON exercises, including six new specialist disciplines:

| Discipline | Production skills |
| --- | --- |
| Cutscenes | Script, storyboard, blocking, camera coverage, timed cues, editing, subtitles, and safe exit to gameplay |
| Game audio | Sound events, mixer buses, headroom, dialogue, ducking, loops, interruption and provenance |
| Multiplayer | Authority, command validation, replication, recovery, latency and adversarial inputs |
| Persistence | Save schemas, state invariants, migration, checkpoints, death/retry and corruption recovery |
| AI encounters | Perception, behavior states, navigation, encounter pacing, recovery and fairness |
| Production pipeline | Dependency scheduling, prototype-to-vertical-slice integration, versioned builds, review and rollback |

Open **Training** to see the role-specific workflows, deliverables and evidence
targets; the same applicable instructions are included in specialist dispatch
and work-order exports. Open **Lab** to inspect the corresponding exercise,
edit its example or author a new submission, then run the measured rubric.
JSON checks exercise the submitted design and simulation, not a finished game.

### Your first cutscene workflow

1. Write a short beat sheet with the scene's entry trigger, what the player
   learns, and the gameplay state that must be true at the end.
2. Storyboard the establishing shot, action and reaction shots. Choose a frame
   rate, define shot ranges, block actors, and plan camera motion and focal point.
3. Edit a timeline with animation, sound, dialogue and subtitle cues; check
   continuity, readability and interruption paths with the cutscenes Lab.
4. Implement the intended timeline in the target engine. Graveforge's existing
   Nightfall Patrol cinematic demo has a three-shot, ten-second timeline with
   imported character animation, camera motion, weather, lighting and spatial audio.
   See [Original cinematic production](#new-in-v7--original-cinematic-production)
   for the original Godot factory and build commands. The Lab's richer teaching
   submission is not the factory's `sequence.json` format. Use the separate
   v32 production runner with explicit scene bindings, or translate the design
   into the original engine timeline rather than feeding it directly to the builder.
5. Verify normal completion, skip, replay, pause, interruption, control and
   camera restoration, and persistence in the actual project. Separately review
   framing, performance, voice clarity, pacing and player experience.

Run the versioned practice catalog and all teaching fixtures offline:

```bash
python3 -m command_center.training_lab_cli catalog
python3 -m command_center.training_lab_cli examples
python3 -m command_center.training_lab_cli assess cutscenes ../my-cutscene-plan.json
```

The curriculum and Lab are now version 2. The original ten exercises remain;
older practice records keep their original report, review and digest as historical
evidence. They do not silently count toward current rubric coverage. The private
ledger format and explicit review rules are unchanged. Nothing here fine-tunes
model weights, generates a finished cinematic automatically, or authorizes
release promotion.

## New in v30 — production asset validation

Use the new local inspectors to check real files produced by your art and
animation tools. They report precisely what they measured, including SHA-256
of the inspected bytes. Run these commands from the Studio source directory:

| What to check | Command |
| --- | --- |
| Static mesh | `python3 -m command_center.lab_artifact path/to/prop.glb` |
| Character skeleton and skin weights | `python3 -m command_center.lab_rig path/to/character.glb` |
| Animation clips and keyframes | `python3 -m command_center.lab_animation path/to/character.glb` |
| Supported PNG texture | `python3 -m command_center.lab_texture path/to/texture.png` |
| Actual Godot import | `python3 -m command_center.lab_engine_import path/to/character.glb` |

The rig profile checks one untextured, single-scene skinned character GLB:
joint references, hierarchy, inverse-bind matrices, normalized skin weights,
vertex attributes and triangle indices. Its practice budget is 4 MiB,
20,000 triangles, 64 primitives, 16 materials, 128 joints per skin and four
influences per vertex. Visual skin deformation still needs a separate review.

PNG inspection reconstructs the actual pixels, measures the decoded size and
estimated uncompressed mip-chain storage, and checks a single-texture practice
budget (1024-pixel maximum edge, power-of-two dimensions, up to 4 MiB on disk
and in the estimated mip chain). It supports non-interlaced 8-bit grayscale,
grayscale-alpha, RGB and RGBA images. Indexed PNGs, animation, and implicit
transparency require a different workflow. Specify an optional declared
texture role with `lab_texture --role base_color` (or `normal`, `roughness`,
`metallic`, `occlusion`, `orm`, `emissive`, `height`, `opacity`); it is not
inferred from the file. A non-power-of-two screenshot can be valid PNG and
still fail this game-texture budget.

Animation inspection reads binary key times and transform values, checks
finite values, channel targets, sampler counts and unit rotation quaternions.
The supported subset includes dense FLOAT translation, rotation and scale
tracks with LINEAR, STEP or CUBICSPLINE interpolation. Its practice budget is
2 MiB per file, 32 clips, 1024 channels, 100,000 channel-keyframes and 300 seconds
per clip's keyed span. It does not judge motion, loop continuity or poses.

Or run a combined character pipeline, collecting rig and animation reports:

```bash
python3 -m command_center.artifact_pipeline --profile character vertical/demo/character/courier.glb
python3 -m command_center.artifact_pipeline --profile character --engine vertical/demo/character/courier.glb
```

Use `--profile static` for a static prop or `--profile texture` for a PNG.
`--engine` is optional and only runs after structural preflight; it is not
available for textures. Each component must observe exactly the same asset
digest, or the combined result is unavailable. The engine probe requires a
compatible local Godot 4 installation plus Linux util-linux `unshare` and
permitted user/network namespaces. It uses a disposable project, a fixed probe
script, a minimal environment and bounded process time/output; it does not
launch a supplied project or user script. If prerequisites are unavailable,
it does not pretend an import passed. This is network isolation, not a complete
filesystem or process sandbox: inspect only trusted local assets with a trusted
Godot installation. It observes an instantiated mesh/skeleton/animation
inventory, not whether animation playback or rendering looks correct.
The supported import candidates are untextured static props and skinned
characters with or without supported animations, not general GLB scenes or
unskinned animated props. The probe refuses scenes above 4096 declared nodes
or 1024 declared mesh instances before running the editor.

Save a report to a private file (outside this repository), then open **Lab**
and use the local artifact report viewer to read it. For example:

```bash
python3 -m command_center.artifact_pipeline --profile character vertical/demo/character/courier.glb > ../courier-report.json
```

The viewer reads selected JSON in the browser only; it is not an authenticated
review or an automatic Academy record. Reports may contain asset details and
must be kept private when examining private projects. Supported profiles are
bounded subsets, not full glTF or PNG conformance validators. Exit 0 means
measured checks passed, 1 means a check failed, and 2 means unavailable.
No report evaluates artistic merit, human playability, game performance,
material color-space intent, or final release readiness.

## New in v29 — Academy practice history and real artifact inspection

The Lab now separates assessment from evidence recording. An assessment remains
stateless; an explicit record action recomputes it and saves the original
submission, measured report, declared specialist role, exact rubric identity,
and review state in the private workspace. A distinct reviewer role (including
the lead) records one acceptance or rejection with a note. Only a current,
passing, non-reference submission is eligible for acceptance. Exact teaching
examples cannot count as independent practice; a modified example is not proof
of originality either. Role names are declarations by the operator, not logins
or authenticated model identities.

Records survive restarts. A revision check prevents overwriting newer actions;
refresh after a conflict and explicitly retry. Historical rubric records remain
visible but cannot be reviewed or count toward current practice coverage. The
ledger is bounded to 800 records (increased in v36) and 32 MiB, shared across current and historical
role-and-exercise assignments and retries. It fails closed on invalid persisted
data and refuses additional records rather than deleting old evidence.
Do not place the ledger or exports in the public source checkout.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/training-records` | Read private practice history and current revision |
| `POST /api/training-records` | Explicit revision-bound record or review |
| `GET /api/training-progress` | Read current per-role practice coverage without submission contents |

Write requests use the existing same-origin guard and `X-Studio-Request: 1`.
Record action fields are `op: "record"`, `exercise_id`, `role`, and
`submission`; review action fields are `op: "review"`, `record_id`,
`reviewer_role`, `decision` (`accepted` or `rejected`), and `note`. Wrap the
action with the latest `expected_revision` and `action` fields. When recording
an already displayed assessment, include its `expected_assessment_sha256`
in the record action; a changed assessment is rejected before persistence.
The Lab supplies this automatically. The progress
report deduplicates identical accepted submission digests per role and exercise;
it excludes failed, unreviewed, rejected, teaching-example and historical
records from qualifying coverage. It never establishes competency or release
readiness.

The same actions are available offline for an existing external workspace:

```bash
python3 -m command_center.training_records_cli --workspace ../studio-workspace list
python3 -m command_center.training_records_cli --workspace ../studio-workspace progress
python3 -m command_center.training_records_cli --workspace ../studio-workspace record interface ui submission.json --expected-revision 0
```

Use the actual latest revision instead of `0` for a populated ledger. Run the
CLI with `--help` to see the review command. Treat the history JSON and original
submissions as private project data.

For an actual 3D export, the new offline GLB inspector reads self-contained,
uncompressed static triangle meshes with untextured materials. It verifies
supported mesh layouts, positions and index bounds and measures resource budgets:

```bash
python3 -m command_center.lab_artifact path/to/prop.glb
python3 -m command_center.lab_artifact demo/first-batch/assets/supply_crate.glb
```

It reads the file without executing asset code or fetching external resources.
The fixed practice budget is 1 MiB, 10,000 triangles, 64 mesh primitives and
8 materials. Counts are before scene instancing, not runtime draw calls.
Unsupported or malformed files are reported as unavailable, not as passing.
Exit 0 means the supported measured checks passed, 1 means a measured check
failed, and 2 means the file could not be assessed. This is not an engine
import, visual review, animation check, or proof of playability.

## New in v28 — practical production lab

At v28, **Lab** introduced ten structured practice exercises, one per Academy curriculum
track. Each has a brief, rubric, role coverage and editable reference example.
Submit a JSON artifact explicitly to compute pass/fail observations against
the rubric. The labs inspect actual proposed data (such as mesh topology,
UV coordinates, quest connections, traversal routes, gameplay traces, HUD
geometry and measurement samples), rather than accepting a checklist of
self-reported completions.

The assessment is deterministic and read-only with respect to the workspace.
The catalog, submission and result have SHA-256 identities. Reports describe
only the measured criteria. The assessment endpoint alone does not persist them;
they are not signed, a human playtest,
model fine-tuning, a certification of specialist ability, or release approval.
The reference examples are teaching fixtures; customize a new submission to
practice independently. No arbitrary code, file paths or commands are executed
by the HTTP assessment endpoint.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/training-lab` | Versioned lab catalog and reference submissions |
| `POST /api/training-lab/assess` | Assess `{exercise_id, submission}` against a named bounded rubric |

The CLI runs the same checks offline:

```bash
python3 -m command_center.training_lab_cli catalog
python3 -m command_center.training_lab_cli examples
python3 -m command_center.training_lab_cli assess interface submission.json
```

Exit 0 means all selected checks pass; 1 means at least one criterion failed;
2 means the submission could not be assessed. The caller must explicitly save
any desired results outside the public source checkout. The CLI and HTTP
interface use the same evaluator. Assessing a reference example does not
constitute completed training.

Asset auditing now recognizes validated Godot 4 GLB/WAV import sidecars
only when they reference a real, provenance-recorded source and the expected
cache destination. Sidecars still count toward asset budgets; malformed,
orphaned or unrecognized imports still require explicit provenance. The
original Nightfall Patrol asset provenance and package manifest also carry
the existing MIT-license and attribution records.

## New in v27 — game production academy and quality engineering

Open **Training** to review the original, versioned Studio curriculum. Each
track defines a production workflow, deliverables, verification criteria,
and a practical exercise. Specialist dispatch exports and claimed work orders
automatically include the applicable tracks for the assigned role.

| Track | Practice focus |
| --- | --- |
| Game design | Core loops, systems, balance, playtesting |
| Game development | Architecture, gameplay logic, testing, integration |
| Modeling | Topology, scale, LODs, collisions, engine imports |
| Textures | UVs, PBR maps, materials, compression, memory |
| Storytelling | Character arcs, quest beats, dialogue, narrative continuity |
| Animation | Rigging, motion, state transitions, deformation |
| Level design | Blockouts, traversal, encounters, navigation |
| Interface | HUD, control schemes, accessibility |
| Quality assurance | Regression tests, defects, acceptance evidence |
| Build performance | Profiling, provenance, reproducible packages |

The curriculum is instructional context, not fine-tuned model weights or a
certification. Exercises are optional proposals, not completed tasks.
Instructional guidance never overrides the approved project specification,
task scope, permissions, or evidence requirements.

Open **Quality** to inspect current release gates, changes against the latest
matching captured audit, and reviewed specialist handoff statistics. Review
latency is elapsed time between submission and review, not agent runtime or
a skill rating. Unknown, missing, stale, and invalid evidence cannot pass a
gate. The dispatch-cycle preview identifies the next eligible task claims
across the shared roster and blocks new exports on role contention. Refresh
after each claim; a preview is not a global reservation or launch operation.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/training` | Versioned curriculum and content digest |
| `GET /api/projects/{id}/quality-matrix` | Current gate status and suggested next action |
| `GET /api/projects/{id}/quality-trends` | Current gates compared with matching captured evidence |
| `GET /api/projects/{id}/specialist-analytics` | Current-specification handoff review statistics |
| `GET /api/dispatch-cycle` | Revision-bound claims preview from one portfolio snapshot |

Check current quality from the CLI with the loopback service running:

```bash
python3 -m command_center.quality_cli PROJECT_ID --port 8765
```

Exit codes: 0 ready, 1 pending or blocked, 2 unavailable. All five endpoints
are read-only; none can claim, execute, or promote work.

## New in v26 — specialist coordination and recovery

Open **Coordination** to inspect four read-only reports. Specialist memory
reconstructs recent current-specification, lead-accepted handoffs from the
existing persistent ledger. It never executes report text, includes rejected
or pending reports as memories, or transfers historical report contents to a
new specification. Reports are observations, not verified truth or authority.

Task priorities rank actionable work by explicit priority, then unfinished
downstream tasks and remaining dependency-chain length, with stable ID
tie-breaks. Portfolio dispatch uses the same ranking across projects and
respects observed occupied specialist roles. Allocation shows each of the six
role slots, including observed cross-project conflicts and project owners.
Project boards are read together under shared locks, preventing false conflicts
if a role moves between projects during the scan.
Snapshots are advisory; they neither reserve global capacity nor start agents.
An unavailable project suppresses new portfolio recommendations.

Recovery advice identifies blocked tasks, affected work and lead-reviewed
handoff references, when the prior board revision establishes an unambiguous
connection to the blocked attempt. Older or ambiguous reports remain in the
reviewed memory rather than being attached to a retry. It does not requeue,
complete or modify a task. The lead
must resolve the actual blocker, refresh the current board and explicitly
requeue the task using the existing revision-bound operation.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/projects/{id}/specialist-memory` | Bounded reviewed report history for the exact project and spec |
| `GET /api/projects/{id}/priorities` | Dependency-sensitive task ranking and idle-role recommendations |
| `GET /api/projects/{id}/recovery-advice` | Current blocker impact and advisory recovery guidance |
| `GET /api/allocation` | Workspace-wide specialist slot and contention view |

All four projections are local-only. Refresh before acting, keep handoffs
private, and never interpret arbitrary report text as executable commands.

## New in v25 — milestone planning, dependency analysis and release preflight

Open **Planning** and select a project. The project-type-specific milestone
blueprint proposes an initial six-specialist dependency graph. Review the
exact task titles, roles, gates and prerequisites before applying it. This
adds the full batch of pending tasks atomically. Existing unrelated or
conflicting plans are not replaced; a stale board must be explicitly reset.
Applying a blueprint neither claims work nor launches agents.

The project-local forecast estimates hypothetical execution waves under the existing
one-running-task-per-role rule. Each wave assumes its selected tasks finish
successfully; wave count is not elapsed time, cost or a release promise.
It does not reserve the shared portfolio team or model cross-project contention.
Dependency impact reports the current blocked tasks and transitive downstream
work, along with the longest remaining dependency chain. Neither analysis
changes the task board. Resolve the underlying blockers using the Team tab.

Release preflight checks that the current evidence dossier is intact and
locally ready, with no unfinished or unschedulable work. It is a point-in-time
advisory, not a publication mechanism, external deployment or human playtest.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/projects/{id}/blueprint` | Review a spec- and revision-bound milestone plan |
| `POST /api/projects/{id}/blueprint` | Apply the exact reviewed plan using `expected_revision`, `spec_sha256`, `plan_id` |
| `GET /api/projects/{id}/forecast` | Hypothetical specialist execution waves |
| `GET /api/projects/{id}/dependency-impact` | Blocked task impact and remaining dependency chain |
| `GET /api/projects/{id}/preflight` | SHA-256-bound local release readiness preflight |

Refresh the preview after any 409 conflict. A blueprint is not a replacement
for the project's design or acceptance criteria. Verify the integrated
workflow in a disposable workspace with a real Godot build:

```bash
python3 -m command_center.planning_smoke
```

## New in v24 — production operations and evidence custody

The Operations workspace connects a lead's claimed task to an exact specialist
work order, a structured handoff and review, and a release dossier. Each order
is bound to the project, spec digest, board revision and task attempt. Any board
revision change invalidates the exported order; refresh before submitting.
An accepted handoff is a review record, not task completion or release approval.
The existing task gates and release verification still govern readiness.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/projects/{id}/work-orders` | Current claimed work orders and host spawn arguments |
| `GET /api/projects/{id}/handoffs` | Current and historical specialist reports |
| `POST /api/projects/{id}/handoffs` | Submit or review with expected revision and spec digest |
| `GET /api/projects/{id}/dossier` | Cross-checked, SHA-256-bound readiness report |
| `GET /api/projects/{id}/recovery` | Integrity-checked snapshot of project records |

For a submission, send `expected_revision`, `spec_sha256`, and an `action`
with `op: "submit"`, `task_id`, `order_id`, `outcome` (`progress`, `blocked`, or
`completed`), `summary`, `evidence` (nonempty list), `changed_paths` (relative
paths), and `next_action`. For lead review, use `op: "review"`, `handoff_id`,
`decision` (`accepted` or `rejected`), and `note`. Reload after conflicts;
never automatically reapply a stale report. Previous-spec reports are read-only.

Export dossier or recovery JSON directly, without reserialization. Verify a
downloaded recovery file offline using:

```bash
python3 -m command_center.recovery verify recovery.json
python3 -m command_center.operations_smoke
```

Recovery is intentionally limited to project records; it is not a complete
backup of job outputs, imported assets or the workspace, and cannot auto-restore
or overwrite anything. Dossier handoff coverage is advisory. Neither digest is
a digital signature. Store these exports privately: reports may contain project
identifiers, evidence and paths. The local service is a loopback development
tool, not a multi-tenant or Internet-facing agent hosting service.

The Midnight Shift activation profile remains five Astra Ultra and one Sol Max,
with parallel execution supported by the host. The local studio exports
dispatch instructions; authorized host agents perform the work.

Engine availability varies by workstation. This release detects `blender52`
when installed and falls back to `blender`; the current v24 environment has
Blender 4.3.2 and Godot 4.7.2. This is not a fresh Blender 5.2 acceptance claim.

## New in v23 — Sprint planning, evidence history and acceptance

The Midnight Shift can turn the Production Supervisor's recommendations into
an explicit, dependency-aware sprint preview. Open **Sprint**, select a project,
review its proposed tasks and source evidence, then apply the preview if it is
appropriate. Applying a preview adds pending tasks in one revision-checked
transaction; it never claims tasks, launches specialists, or replaces completed
work. Use the Team tab to claim and complete work in the usual way.

### Sprint API

`GET /api/projects/{id}/sprint` returns `project_id`, `spec_sha256`,
`board_revision`, `plan_id`, `status`, `reason`, `tasks`, and `rationale`.
The tasks are normal task-board definitions. Rationale entries identify the
task and the supervisor evidence motivating it. `ready` means the preview can
be applied; `empty` means it proposes no additional tasks; `blocked` means
the planner cannot safely propose work. Existing matching task IDs are not
duplicated, even after completion. Recurring issues require fresh review.

`POST /api/projects/{id}/sprint` accepts exactly `expected_revision`,
`spec_sha256`, and `plan_id` from the preview, and returns the updated task
board. The service recomputes the proposal and rejects stale or changed plans
with HTTP 409. Batch mutation uses the task board's existing exclusive lock
and validates the entire dependency graph before writing any task.
An approval or capture also checks the project records and observed job
history again under the exclusive project write lock. A competing writer's
new defect or changed board therefore causes a conflict rather than committing
the stale observation. Background build state is observational; refresh after
new build results appear.

### Historical evidence and current readiness

`GET /api/projects/{id}/evidence-history` returns a revisioned ledger of
explicitly captured supervisor observations, newest first. Each observation
records its identity, creation time, specification digest, audit status,
checks, and operator note. `POST` accepts `expected_revision`, `spec_sha256`,
and a nonblank `note` of up to 512 characters. The server captures the live
audit itself; callers cannot submit a substitute audit. Prior specification
snapshots remain historical evidence after edits and restarts. The ledger
accepts up to 100 captures. No capture occurs automatically or on GET.

`GET /api/projects/{id}/acceptance` returns a read-only overall status,
individual gates, and evidence summary. This stricter advisory readiness
report requires the current supervisor checks to pass, no current open
defects, completed board evidence, and a passing most recent capture for the
current specification. A historical pass cannot overcome a current failure;
after a failed capture, recapture the improved audit instead of relying on an
older passing observation.
`ready` is local production evidence only; it is not runtime/gameplay quality,
device acceptance, external release approval, or automatic deployment.

All POST requests require `Content-Type: application/json` and the usual
`X-Studio-Request: 1` header. Read the latest projection before submitting and
refresh on 409 conflicts. The five-hour sustained-work goal remains bounded
by authorization and host execution limits.

### Verify v23

Run the independent acceptance smoke in a disposable workspace with Godot
available:

```bash
python3 -m command_center.sprint_smoke
```

The smoke tests deterministic previews, changed-evidence rejection, atomic
application, captured history and restart, a real verified Godot build, and
historical evidence isolation after editing a project specification.

Verified v23: 303 Python tests passed in the full regression run, followed
by 16 focused tests passing after the final non-object-spec guard (including
the additional corruption regression). All five Node DOM suites and 16 of 16
bundled package integrity checks passed. The real HTTP/Godot acceptance smoke
is recorded in `command_center/demo/sprint-smoke.json`. Live Chromium visual
rendering remained unavailable because the workstation denied its startup
socket; the UI was exercised with its DOM handlers and the local HTTP API.

The restored v23 workstation exposed Godot 4.7.2 and Blender 4.3.2;
the previously installed `blender52` executable was not present. An explicit
`STUDIO_BLENDER=blender bash verify-workstation.sh` run passed the headless
Blender-to-Godot export/import smoke on the available versions. This does not
verify Blender 5.2 in the restored environment.

## New in v22 — Production Supervisor

Run from the extracted Studio directory. Keep the same workspace path
across restarts so the Command Center can recover your projects and records.
[Open the local Command Center](http://127.0.0.1:8765)

```bash
python3 -m command_center.server --workspace ../studio-workspace
```

### Review production evidence

Open **Supervisor**, select a project in **Active project**, and use
**Refresh supervisor** after a build or record changes.
The **Production checks** section reviews the latest build submitted for the saved
specification, active release integrity, task board, manual review evidence,
open defects, and build performance. The **Recommendations** section shows
the evidence behind each proposed action and the relevant specialist role.
The audit is read-only. The lead applies fixes, task changes, and
release promotions through the corresponding Command Center controls.

`GET /api/projects/{id}/supervisor` returns `project_id`, `spec_sha256`,
`status`, `checks`, and `recommendations`. Checks carry `id`, `label`, `status`,
and a text `evidence` field. Each check has status `fail`, `warn`, `pending`,
or `pass`. The manual review check passes when the current task board has at
least one manual task and all manual tasks are complete with recorded
evidence. Recommendations carry `id`, `severity`, `title`, `detail`, `role`,
and an `evidence` list. The overall status is the first applicable row below.

| Overall `status` | Evidence |
| --- | --- |
| `blocked` | At least one check failed, for example when a source is unreadable or a current critical or high defect is open. |
| `attention` | At least one check raised a warning. Current medium or low defects and measured build regressions can trigger warnings. |
| `pending` | At least one check is waiting for evidence. |
| `pass` | All checks passed. |

### Interpret build performance

**Build performance** reports seconds measured for each job. Queue time is
the elapsed time from job creation to start. Build and verification times
come from their respective pipeline commands. The total is build plus
verification. Use separate runtime profiling to assess game performance.

`GET /api/projects/{id}/performance` returns `project_id`, `spec_sha256`,
`scope`, `counts`, `samples`, `summary`, and `regression`. The scope is
`current_spec`. `counts` includes `total`, `queued`, `running`, `passed`,
`failed`, and `canceled`. `samples` lists up to 50 newest matching jobs across
all statuses, with `job_id`, `status`, `created_at`, `queue_seconds`,
`build_seconds`, `verify_seconds`, and `total_seconds`. Missing measurements
are `null`.

`median_build_seconds`, `median_verify_seconds`, and `median_total_seconds`
use every passed, verified job with both stages measured for the current spec.
Regression compares the latest dated qualifying run against the median of
at least two earlier qualifying runs. It flags a slowdown only when the
increase is at least 25% and at least one second. `regression` is `null` when
a comparison is unavailable or the baseline is zero. The summary includes
`latest_total_seconds`, `baseline_total_seconds`, and `regression_percent`.

### Track defects across specifications

In **Defect ledger**, use **Record defect** to add an issue with a title,
severity, description, and evidence. Enter one evidence note per line. Use
**Resolve defect** on an open issue after recording the result of a check,
or **Reopen defect** on a resolved issue when new evidence warrants it. Each
transition appends its evidence to the record. Defects for other saved spec
digests are read-only under **Earlier specifications**. Record a new defect
for the current spec if the issue still occurs there.

`GET /api/projects/{id}/defects` returns the live `spec_sha256`, `project_id`,
`revision`, `items`, and a `summary` with `current_open`, `current_resolved`,
`historical_open`, and `historical_resolved` counts. Each item includes `id`,
`title`, `severity`, `description`, `status`, its recorded `spec_sha256`,
`created_at`, `updated_at`, and `evidence`. The server generates a 32-character
lowercase hexadecimal ID for each defect. The ledger persists in
`projects/PROJECT_ID/defects.json` inside the workspace.

`PUT /api/projects/{id}/defects` requires `expected_revision`, the current
`spec_sha256`, and one `action`. A successful write matches the revision and
digest, applies the action, and returns the updated snapshot. For HTTP 409,
refresh the ledger and verify the current spec, revision, and defect before
retrying. Invalid actions, unknown defect IDs, and invalid transitions return
HTTP 400.

| Operator action | JSON `action` |
| --- | --- |
| Record | `{"op":"add","title":"Fallback prompt clips","severity":"medium","description":"The prompt clips at the small layout width.","evidence":["Observed at 390 px in a layout check"]}` |
| Resolve | `{"op":"resolve","defect_id":"DEFECT_ID","evidence":["The prompt fits at 390 px after the change"]}` |
| Reopen | `{"op":"reopen","defect_id":"DEFECT_ID","evidence":["The prompt clips at 390 px with the updated copy"]}` |

Severities are `critical`, `high`, `medium`, and `low`. The ledger holds up
to 100 items per project across spec digests. Titles allow up to 160
characters and descriptions up to 2,048. Each action requires one to eight
nonblank evidence notes of up to 512 characters each. A defect retains up to
32 notes, with one slot reserved for resolution while it is open.

Use your project ID and copy the latest revision and digest from the ledger
response. This example assumes the first write at revision `0`.

```bash
PROJECT_ID=your-project-id
PROJECT_URL="http://127.0.0.1:8765/api/projects/$PROJECT_ID"
curl -fsS "$PROJECT_URL/supervisor"
curl -fsS "$PROJECT_URL/performance"
curl -fsS "$PROJECT_URL/defects"
curl -fsS -X PUT "$PROJECT_URL/defects" \
  -H 'Content-Type: application/json' -H 'X-Studio-Request: 1' \
  --data-binary @- <<'JSON'
{
  "expected_revision": 0,
  "spec_sha256": "CURRENT_SPEC_SHA256",
  "action": {
    "op": "add",
    "title": "Fallback prompt clips",
    "severity": "medium",
    "description": "The prompt clips at the small layout width.",
    "evidence": ["Observed at 390 px in a layout check"]
  }
}
JSON
```

### The Midnight Shift

The team profile identifies **The Midnight Shift** in `profile.team_name`.
Use role IDs in task board requests. Dispatch exports now identify workers
by the codename slug in `spawn_args[].task_name`. The role entries supply
`name` for display, `codename`, `role_name`, and `agent_task_name`.

| Specialist | Role ID | Exported worker name | Model and reasoning effort |
| --- | --- | --- | --- |
| Count Blueprint | `architecture` | `count_blueprint` | `gpt-6.2-astra` at `ultra` |
| Major Mayhem | `gameplay` | `major_mayhem` | `gpt-6.2-astra` at `ultra` |
| Doctor Doomcheck | `verification` | `doctor_doomcheck` | `gpt-6.2-astra` at `ultra` |
| Madame Glitch | `ui` | `madame_glitch` | `gpt-6.2-astra` at `ultra` |
| Grimbrush | `content` | `grimbrush` | `gpt-6.2-astra` at `ultra` |
| Baron Buildgrave | `build_operations` | `baron_buildgrave` | `gpt-6.2-sol` at `max` |

The profile requests priority service on compatible hosts. The lead claims
eligible tasks on the board before launching workers through an authorized
host.

### Verify the Supervisor

Run the standalone smoke from the Studio directory with Godot available. It
uses temporary workspaces. Pass `--output PATH` to save the run as JSON.

```bash
python3 -m command_center.supervisor_smoke
```

The bundled `command_center/demo/supervisor-smoke.json` records a passing
Godot build and verification, measured pipeline timings, detection of an
invalid release, defect persistence across restart, and rejection of stale
and historical writes. All 16 bundled game packages passed integrity
verification.

Verified v22: 266 Python regression tests passed, all four Node DOM
interaction suites passed, and the final supervisor/HTTP checks passed
again after audit integration. The Team view and dispatch exports identify
The Midnight Shift. Live Chromium visual rendering could not be verified
because workstation restrictions denied socket creation; DOM interaction
and real HTTP/build tests are covered.

## New in v21 — build queue, release registry, and portfolio

### Queue, cancel, and retry builds

Set **Build priority** in the project **Workspace**, then select **Queue build**.
Open **Build queue** to see the running job, pending jobs, build history, and
logs. The worker starts one build at a time. For waiting jobs, 5 is the highest
priority and 1 is the lowest. The default is 3. Jobs with the same priority run
in submission order.

The queue saves each job and its spec snapshot under `jobs/JOB_ID/`. When you
restart the service, queued jobs resume in dispatch order using their original
snapshots. An interrupted running job becomes failed. Use **Cancel build** on a
queued job or **Retry build** on a failed or canceled job while its spec and
project kind still match the saved project. A retry creates a new job at the
original priority and records the source job ID in `retry_of`. After a spec
change, queue a new build for the updated spec.

| Request | Body | Result |
| --- | --- | --- |
| `POST /api/projects/{id}/build` | `{"priority":5}` or `{}` for the default | HTTP 202 and the new job |
| `GET /api/queue` | — | `running` (job or `null`), `queued` (jobs in dispatch order), and `counts` for `queued`, `running`, `passed`, `failed`, and `canceled` |
| `POST /api/jobs/{id}/cancel` | `{}` | HTTP 200 and the canceled job |
| `POST /api/jobs/{id}/retry` | `{}` | HTTP 202 and the new job |
| `GET /api/jobs/{id}` | — | Job status and recorded evidence |

Write requests use `Content-Type: application/json` and `X-Studio-Request: 1`
on the loopback service. For example, replace `your-project-id` with the saved
project ID to submit a priority 5 build.

```bash
PROJECT_ID=your-project-id
STUDIO_URL=http://127.0.0.1:8765
curl -fsS -X POST "$STUDIO_URL/api/projects/$PROJECT_ID/build" \
  -H 'Content-Type: application/json' -H 'X-Studio-Request: 1' \
  -d '{"priority":5}'
curl -fsS "$STUDIO_URL/api/queue"
```

For a cancel or retry conflict (HTTP 409), read the current job and check its
status and spec before taking another action.

### Promote and activate a release

In **Releases**, select a project and choose a **Verified build** for its
current saved spec. Select **Promote and activate** to add a history entry and
make it active. Promotion checks the passed, verified job record, its spec
snapshot, and the sealed output. For v21 jobs, the output manifest must also
match the SHA-256 recorded by the build. Legacy jobs without a recorded
manifest digest establish their release seal at promotion after fresh
verification. To switch to an earlier eligible entry in **Release history**,
select **Activate release**. Activation checks the package against its release
seal.

The registry is saved to `projects/PROJECT_ID/releases.json`. Package files
stay under `jobs/JOB_ID/output/`, so retain the referenced job directories to
keep those releases usable. Spec edits, missing files, and integrity failures
are reflected in the active release state when you read the registry.

| `active_state` | Meaning |
| --- | --- |
| `empty` | The project has no active release. |
| `current` | The active release matches the saved spec and its package passes integrity checks. |
| `stale` | The active release belongs to a different spec digest. |
| `invalid` | The active release's job or sealed output can no longer be verified. |

`GET /api/projects/{id}/releases` returns `project_id`, `spec_sha256`,
`revision`, `releases`, `active_release_id`, and `active_state`. Each release
records `id`, `job_id`, `spec_sha256`, `created_at`, `manifest_sha256`, and the
workspace-relative `output` path.

Send the latest `revision` as `expected_revision` and the live `spec_sha256`
with each `PUT /api/projects/{id}/releases`. A successful write returns the
updated registry. For HTTP 409, use **Refresh releases** or refetch the registry
and check the revision and spec. Ineligible jobs or releases and duplicate
promotions return HTTP 400.

| Operator action | JSON `action` |
| --- | --- |
| Promote a verified build | `{"op":"promote","job_id":"VERIFIED_JOB_ID"}` |
| Activate a release from history | `{"op":"activate","release_id":"RELEASE_ID"}` |

For the first promotion, replace the example digest and job ID with values
from the release registry and the passed job. Later writes use the latest
registry revision.

```bash
RELEASE_URL="$STUDIO_URL/api/projects/$PROJECT_ID/releases"
curl -fsS "$RELEASE_URL"
curl -fsS -X PUT "$RELEASE_URL" \
  -H 'Content-Type: application/json' -H 'X-Studio-Request: 1' \
  --data-binary @- <<'JSON'
{
  "expected_revision": 0,
  "spec_sha256": "CURRENT_SPEC_SHA256",
  "action": {"op": "promote", "job_id": "VERIFIED_JOB_ID"}
}
JSON
```

### Review assignments across projects

The **Portfolio** view shows projects, task counts, role occupancy, and
recommendations across the workspace. For each idle role, the portfolio
recommends the dependency-ready task with the highest priority from current
boards. Ties sort by project ID, then task ID, in ascending order. Running
assignments occupy their roles, including claims on stale boards. Multiple
running claims for the same role appear as a conflict. If a board cannot be
read, recommendations pause until role occupancy can be established.

Use **Download portfolio dispatch JSON** to export `portfolio-dispatch.json`
with the current recommendations. Use **Open project board** to review a
task and its prerequisites in **Team**.

The read-only `GET /api/portfolio` returns `projects`, `summary`,
`occupied_roles`, `assignments`, `conflicts`, and `dispatch_plan`. Each
assignment identifies the project, task, role, priority, model, reasoning
effort, `board_revision`, and `spec_sha256`. The export-only `dispatch_plan`
supplies the specialist profile and one `spawn_args` entry per recommended
role.

Before dispatch, the lead refreshes the portfolio, checks the project's latest
board, and claims the exact task with `start` on the project board. Agent
launches require a manual action on an authorized host. The dispatch profile
requests priority service for five Astra Ultra specialists and one Sol Max
specialist. The five-hour target covers authorized active work within host
and session limits.

### Verify orchestration

Run the v21 smoke from the Studio directory. It uses temporary workspaces
and requires Godot to build and verify a world package.

```bash
python3 -m command_center.orchestration_smoke
```

Verified v21 release: 235 Python regression tests passed, all three Node DOM
interaction suites passed, and all 16 bundled game packages retained valid
integrity seals. The pipeline tests exercised interrupted-service recovery,
priority/FIFO scheduling, cancellation, retry lineage, and manifest sealing.
The standalone `command_center/demo/orchestration-smoke.json` records actual
priority dispatch, a real Godot build and separate verification, portfolio
dispatch identity, and current/invalid/stale release states. Live Chromium
rendering remains unverified because local socket creation was denied by the
workstation; the UI checks cover the DOM and commands, not visual rendering.

## New in v20 — manual task scheduler

The Command Center saves a dependency-aware task board at
`projects/PROJECT_ID/task-board.json` inside the workspace. Use the same
workspace to recover the board after a restart. The board tracks individual
tasks and their evidence. The v19 work checkpoint at
`projects/PROJECT_ID/checkpoint.json` tracks cumulative active work and the
next action for the project.

Select your project in **Team** and open **Task board**.

### Work the task board

1. Use **Add task** to record a task, assign a specialist role, set a priority
   from 1 to 5, and choose a gate. Enter prerequisite IDs separated by commas.
   Add prerequisite tasks before the tasks that depend on them.
2. The ready list contains pending tasks whose prerequisites are completed.
   Priority 5 comes first, with task IDs breaking ties alphabetically.
   **Suggested assignments** shows the first ready task for each idle role.
   Use **Download ready dispatch JSON** to export those suggestions for an
   authorized host. Select **Start task** to mark a task running. Each role can
   have one running task.
3. Select **Complete task** and supply evidence such as the test command and
   result. For a build-gated task, use **Queue build** in the project workspace
   and copy the job ID from **Build queue** after verification passes. The
   scheduler checks the actual pipeline job record for `status: "passed"`,
   `verified: true`, and the same project ID and current spec digest. Supplied
   notes and logs serve as completion evidence alongside the verified job.
4. Use **Block task** to record why a running task stopped. **Return to pending**
   requeues a running or blocked task and retains its attempt count. **Change
   role** reassigns pending or blocked work to a different specialist. Completed
   tasks are read-only.

| Role ID | Specialist |
| --- | --- |
| `architecture` | `gpt-6.2-astra` at `ultra` |
| `gameplay` | `gpt-6.2-astra` at `ultra` |
| `verification` | `gpt-6.2-astra` at `ultra` |
| `ui` | `gpt-6.2-astra` at `ultra` |
| `content` | `gpt-6.2-astra` at `ultra` |
| `build_operations` | `gpt-6.2-sol` at `max` |

The Team dispatch profile requests priority service for these six fixed
specialists. The lead starts work on the board and records the evidence
returned by specialists. Agent launches require an explicit action on an
authorized, compatible host. The five-hour target covers active work within
host limits and can be interrupted.

When a spec edit changes the saved digest, the old board becomes **stale**.
It remains visible for review and stops producing ready tasks and assignments.
Check **Clear the previous tasks and evidence**, then select **Replace task
board** to discard the previous tasks and start an empty board for the current
spec. Use **Refresh board** to read the latest revision after an update from
another session.

### Read and update the board over HTTP

`GET /api/projects/{id}/tasks` returns `project_id`, the live `spec_sha256`,
the recorded `board_spec_sha256`, `state`, `revision`, `tasks`, `summary`,
`ready_task_ids` and `assignments`. A board is `empty` before the first write,
`current` when its digest matches the saved spec, and `stale` after a spec
change. The summary counts `total`, `completed`, `ready`, `running`, `blocked`
and `waiting` tasks. For a current board, waiting tasks are pending with unmet
prerequisites. For a stale board, all pending tasks count as waiting. Each entry
in `assignments` supplies `task_id`, `role`, `model_id` and `reasoning_effort`.

| Task field | Meaning |
| --- | --- |
| `id` | Unique task slug using lowercase letters, digits, and hyphen-separated words. The limit is 64 characters. |
| `title` | Short description, up to 120 characters. |
| `role` | One of the six specialist IDs above. |
| `priority` | Integer from 1 to 5, with 5 highest. |
| `depends_on` | IDs of prerequisite tasks on this board. |
| `gate` | `manual` or `build`. |
| `status` | `pending`, `running`, `blocked` or `completed`. |
| `evidence` | Empty until completion. A completed task has one to eight nonblank evidence strings of up to 512 characters each. |
| `job_id` | ID of the verified pipeline job recorded for a build-gated completion. The ID is 32 lowercase hexadecimal characters. |
| `reason` | Explanation for blocking a task, up to 512 characters. Requeue clears this field. |
| `attempts` | Number of times the task was started. |

`PUT /api/projects/{id}/tasks` applies one action to a board of up to 100
tasks. Send `expected_revision` and `spec_sha256` from the latest snapshot
with each action. The response is the updated snapshot. For HTTP 409, fetch
the current board and reconcile the conflict before retrying. A stale board
accepts only `reset` with its latest revision and the live digest.

Replace `your-project-id` with the ID from the Command Center. This first
write assumes revision `0`. Replace `CURRENT_SPEC_SHA256` with the digest
from the GET response.

```bash
PROJECT_ID=your-project-id
TASK_URL="http://127.0.0.1:8765/api/projects/${PROJECT_ID}/tasks"
curl -fsS "$TASK_URL"

curl -fsS -X PUT "$TASK_URL" \
  -H 'Content-Type: application/json' -H 'X-Studio-Request: 1' \
  --data-binary @- <<'JSON'
{
  "expected_revision": 0,
  "spec_sha256": "CURRENT_SPEC_SHA256",
  "action": {
    "op": "add",
    "task": {
      "id": "define-route",
      "title": "Define the route and acceptance criteria",
      "role": "architecture",
      "priority": 5,
      "depends_on": [],
      "gate": "manual"
    }
  }
}
JSON
```

Use these objects in the `action` field, with the task IDs and real evidence
for your project.

| Operator action | JSON `action` | Applies to |
| --- | --- | --- |
| Start | `{"op":"start","task_id":"define-route"}` | Ready task with an idle role |
| Complete manually | `{"op":"complete","task_id":"define-route","evidence":["Recorded the route criteria in the project brief"]}` | Running task with the `manual` gate |
| Complete with a build | `{"op":"complete","task_id":"build-world","evidence":["Build and verifier passed"],"job_id":"VERIFIED_JOB_ID"}` | Running task with the `build` gate |
| Block | `{"op":"block","task_id":"define-route","reason":"Waiting for the level boundary"}` | Running task |
| Requeue | `{"op":"requeue","task_id":"define-route"}` | Running or blocked task |
| Reassign | `{"op":"reassign","task_id":"define-route","role":"gameplay"}` | Pending or blocked task |
| Reset | `{"op":"reset"}` | Stale board |

`GET /api/team/{id}` includes `scheduled_dispatch_plan`, an export with the
board revision, spec identity and suggested assignments. It has at most one
entry in `spawn_args` per idle role and an empty list for empty or stale boards.
The `task_board_access` entry identifies the endpoint and the lead as the
writer. The `dispatch_plan` entry continues to carry the role templates.
Before dispatch, the lead fetches the current board and claims the exact
task with a successful `start` action. Refresh the export if the task is no
longer eligible.

### Try the example graph

Use an empty board for a disposable world project. Submit each object from
the example, in array order, as the `action` in a separate PUT. Read the
revision and digest from the GET response for the first action and from the
updated snapshot after each write. [task-board-example.json](command_center/demo/task-board-example.json)

Start and complete `define-route` after recording the route criteria. This
makes the gameplay, UI and content tasks ready. Completing those three
unlocks `build-world`. Complete the build task with a verified pipeline job
to make `review-world` ready for the verification specialist.

Run the scheduler smoke test from the Studio directory. It uses temporary
projects, restarts the loopback service, and checks the build gate against a
real Godot world build and verification run.

```bash
python3 -m command_center.scheduler_smoke
```

In the v20 release, the full Python suite passed 207 tests, both Node DOM
interaction suites passed, and all 16 bundled package integrity seals passed.
The standalone scheduler smoke report records actual Godot world route QA,
successful build and separate verification commands, revision recovery, and
rejection of missing, unknown, foreign-project and obsolete-spec build jobs.
See `command_center/demo/scheduler-smoke.json`. Live Chromium rendering was
not verified because the workstation denied Chromium's local socket creation.

## New in v19 — durable work checkpoints

The Command Center stores each project's development checkpoint at
`projects/PROJECT_ID/checkpoint.json` inside the local workspace. A checkpoint
tracks cumulative active work against the project's saved specification. The
lead records completed work, verification evidence, remaining work and the
exact next action every five minutes when practical and at verified milestones.

### Save and resume in the Command Center

Run this from the Studio directory. Use a workspace
on storage that persists across sessions.

```bash
python3 -m command_center.server --workspace ../studio-workspace
```

Select your project in **Team**. In **Work checkpoint**, use **Create
checkpoint** or **Edit checkpoint** to record progress, then select **Save
checkpoint**. On the next authorized activation, reopen the same workspace and
check **Specification identity** for the project ID and saved spec digest
before following the recorded next action. [Open the local Command Center](http://127.0.0.1:8765)

| State | How to proceed |
| --- | --- |
| `empty` | Start recording work against the saved spec. The full 18,000-second target remains. |
| `current` | Resume unfinished work from the recorded next action. Remaining time is the target minus the recorded active seconds. |
| `stale` | The saved spec changed. Review the previous checkpoint, then choose **Start a checkpoint for the current specification** and confirm its replacement. The remaining time is unavailable until reset. |

After completing work, save it with **Completed** status. For a new authorized
activation against the same saved spec, use **Start a new sprint** and confirm
replacement of the completed checkpoint.

The displayed elapsed and remaining seconds stay fixed between saves, even
while the server is stopped. Five hours is a target for active authorized work.
Work resumes when you authorize a compatible active host. Host shutdown,
user stop requests and the other stop conditions in `AGENTS.md` take
precedence. Dispatch JSON exports the endpoint and designates the lead to
commit the merged checkpoint.

### Save and resume from the CLI or HTTP API

Run the CLI from the Studio directory with the same
workspace path used by the Command Center. Use your project's ID in place of
`PROJECT_ID`.

```bash
python3 -m command_center.checkpoint_cli --workspace ../studio-workspace show PROJECT_ID
python3 -m command_center.checkpoint_cli --workspace ../studio-workspace save PROJECT_ID --input checkpoint.json
```

`show` and `GET /api/projects/{id}/checkpoint` return the project ID, current
spec SHA-256, state, revision, checkpoint, target seconds and remaining seconds.
Use the returned `revision` as `expected_revision` and copy the top-level
`spec_sha256` into the save request. This example shows a first save at revision
zero. Replace the example digest with the one returned for your project.

```json
{
  "expected_revision": 0,
  "spec_sha256": "CURRENT_SPEC_SHA256",
  "elapsed_seconds": 300,
  "status": "paused",
  "completed_work": ["Validated the saved world spec"],
  "verification_evidence": ["World spec validation passed"],
  "remaining_work": ["Build the world"],
  "next_action": "Submit a build for the saved world spec"
}
```

Record whole active seconds from 0 to 18,000. Within a run, the elapsed value
can stay the same or increase. The supported statuses are `in_progress`,
`paused`, `completed` and `blocked`. Each list accepts up to 32 entries.
Each entry and the next action must contain nonblank text of at most 1,024
characters. A completed checkpoint can use an empty string for `next_action`.

Replace a stale checkpoint with the current digest and latest revision,
setting `"reset_for_spec_change": true` and `"elapsed_seconds": 0`. After
completing a run, use `"start_new_run": true` and `"elapsed_seconds": 0` to
start a new record against the same saved spec. Each action replaces the
previous checkpoint and advances its revision. Use one of these flags per
request.

To save over HTTP while the server is running, send the same JSON with
`PUT /api/projects/{id}/checkpoint`, `Content-Type: application/json` and
`X-Studio-Request: 1`. If the API returns HTTP 409, read the latest
checkpoint and reconcile the revision or spec before saving again.

### Verify the workflow

```bash
python3 -m command_center.checkpoint_smoke
```

The smoke saves sample progress in a temporary workspace and checks recovery
after a service restart, revision conflicts, reset after a spec change and
starting a fresh run after completion. Pass `--output PATH` to also save its
JSON report.

Release verification: 180 Python tests passed, including independent process
contention and spec-change serialization. The real HTTP smoke report at
`command_center/demo/checkpoint-smoke.json` records restart recovery, both
conflicts (HTTP 409), explicit spec reset, and a fresh sprint after completion.
All previously sealed game packages are retained. The UI interaction harness
passes with `node tests/test_checkpoint_ui.js` (simulated DOM, not live browser
rendering). Browser visual verification remains pending on this host.

## New in v18.1 — sustained-work activation profile

v18.1 introduced the five-hour active-work target for authorized activations
using the six-agent fast deployment profile. The dispatch plan exports the
`profile.continuity` settings and includes the policy in each specialist work
order.

## New in v18 — synchronized interactive multiplayer and dynamic simulation

Frontline City retains all Advanced City offline systems and introduces a
separate shared interactive layer when hosting or joining the local ENet
session. This is a reusable development demonstrator, not a production
networked game or public matchmaking service.

- A shared street car is controlled by its single authorized driver. The host
  validates boarding distance, vehicle ownership and exit, handles steering,
  forward/reverse acceleration and swept building/cover clearance, and carries
  the driver's actual replicated position. Other players see its position and
  driver state. The car uses an explicit planar movement solver, not suspension
  physics.
- A single-rider observation elevator travels continuously from ground to a
  6 m observation stop and back. Ground approach, occupancy, movement
  interlocks and return-to-street exit are enforced by the authority. It is
  a separate network demonstration, not the offline three-storey tower;
  passengers do not disembark on the observation landing.
- Three shared cover panels have per-peer hit cooldowns and three health
  points each. Proximity-authorized hits reduce health; destruction removes
  collision and reveals rubble. The network avatar and car solver honor the
  surviving cover footprint. This demonstration uses numbered target requests,
  not fully replicated camera raycasts or structural building fracture.
- A deterministic mission director issues timed three-stage contracts with
  street landmarks, live markers, progress, scoring and restart after success
  or timeout. The server alone accepts proximity-validated progress. Clients
  receive the current contract and score.
- Two three-member AI squads play a deterministic shield-tag round in a visible
  arena. Agents move in formation, select targets, engage, take shield damage,
  and finish with a winner or draw. The host advances the simulation and
  clients render the replicated state. This is an autonomous game-AI sample,
  not a complete player combat system.
- The original player, population and persistent co-op objective channels are
  retained. New feature requests are fixed-length and rate-limited; full
  world-feature snapshots are bounded, schema-validated and sequenced, with
  periodic publication to late joiners. The new layer resets when a session
  starts; v17's three persistent co-op objectives still survive host restart.

```bash
python3 frontline/build.py frontline/demo_spec.json --output my-frontline --frontline-qa
python3 frontline/build.py --verify my-frontline
godot --path my-frontline -- --host 8765
godot --path my-frontline -- --join 8765
python3 -m command_center.frontline_smoke
```

The included playable project is `frontline/demo/frontline_city`. Offline
mode remains Advanced City with its original controls. Online, F boards or
exits the marked shared car, WASD drives while seated, E operates the marked
observation lift, 1–3 request nearby cover-panel hits, and R interacts with
the active mission target. Q retains the original persistent objectives.
No public server hosting, authentication or internet matchmaking is included.

Verification of the included v18 release: all 154 Python regression tests,
17 Godot component tests, 36 Frontline integration checks and 37 Advanced
City compatibility checks passed. The two-scene Frontline scenario drove
the shared vehicle 8.31 m, synchronized the observation lift, destroyed two
cover panels, completed a 400-point mission, and executed 45 shield-tag
shots. Its sampled aggregate state packet was 1,045 bytes. Detailed new
scenario results and component logs are in `frontline/demo/frontline_city/reports/`.
The HTTP acceptance report at `command_center/demo/frontline-smoke.json`
also passed, including scenario evidence invalidation and custom-map rebuild.
Interactive visual/device playtesting is not covered by these headless gates.

All original packages remain included. The concurrent specialist deployment
profile remains five GPT-6.2 Astra Ultra agents and one GPT-6.2 Sol Max agent.
The command center exports this six-agent launch plan with fast/priority
settings; actual agent launch requires an active compatible agent host.

## New in v17 — connected buildings, driving, quests and durable co-op progress

Advanced City builds on the complete v16 city generator with independent,
reusable systems. Earlier projects and their original verified packages remain
in the archive.

- A second eligible building becomes a three-storey tower with physical floor
  slabs, a furnished entrance, a moving elevator car, landing gates and
  interlocked doors. Players walk into the elevator, ride continuously and
  walk across each landing. The cabin cycles floors 0 → 1 → 2 → 0; calling
  from another floor is also supported. Compact generated layouts without a
  suitable second tall lot omit the tower rather than changing the city layout.
- A drivable touring car has acceleration, reverse, steering, braking, a
  collision-backed chassis, entry/exit checks, a chase camera and a speed HUD.
  This is a flat-street vehicle controller, not a suspension or tire-force
  simulation. The moving ambient traffic still uses its separate simulation.
- Live residents have deterministic names and contextual dialogue. Ada's
  seed-exchange errand has a giver, distinct recipient and return stage. A
  marker follows the current resident so the player can navigate to them.
- Offline surface checkpoints now persist the tower, parked vehicle and quest
  in addition to all the Vertical City feature state. Save and load are blocked
  while riding, driving, inside buildings, underground, or connected online.
  The parked car must also clear doors and the demolition laboratory, so the
  checkpoint can restore safely even before saved geometry states are applied.
- Real ENet loopback co-op now has three shared street objectives. Clients send
  a bounded request; the server checks the actual authoritative peer position,
  objective identity and duplicate claims. The host replicates committed
  progress to clients and late joiners. Host checkpoint files are versioned,
  checksummed and rotated, with recovery from a valid previous copy and
  monotonic progress checks. Fresh hosts resume the saved objective state.
  The persistence scope is shared objective flags, not individual accounts,
  inventory, character poses or the entire live city. The host is local only,
  and one process owns the checkpoint path. Special offline gameplay remains
  unavailable online; no matchmaking, authentication or dedicated server is
  included.

```bash
python3 advanced/build.py advanced/demo_spec.json --output my-advanced-city --advanced-qa
python3 advanced/build.py --verify my-advanced-city
godot --path my-advanced-city
godot --path my-advanced-city -- --host 8765
godot --path my-advanced-city -- --join 8765
python3 -m command_center.advanced_smoke
```

The included playable project is `advanced/demo/advanced_city`. In offline
mode use WASD, Shift and mouse look to explore; E operates doors, the metro
and the tower elevator. F boards/exits the vehicle, WASD drives and Space
brakes. C talks to residents, and F5/F9 save/restore from clear public streets.
In a connected session, Q claims a nearby unclaimed co-op objective. Completed
objective markers change color and the host HUD shows its durable revision.
The command center supports the Advanced City spec and verifies fixture-specific
scenario evidence. Custom specs run all component and launch gates without
claiming the exact fixture scenario passed.

The fixed fixture's sealed `reports/advanced-qa.json` records 37 passed
checks, 221 m walked, 28 m driven, three completed elevator trips, a complete
resident quest and all three shared objectives persisted after host restart.
The builder also runs 12 individual Godot component scripts. A second
regression playthrough adapts the previous 33-check scenario to the new
Advanced City scene itself; it exercises the original interior, metro ride,
destruction, checkpoint and population replication features with the new
systems present. Its reproducible script and execution log are in
`advanced/regression/`. Run it on a disposable copy of the packaged project
after copying the regression script into that copy:

```bash
cp -a advanced/demo/advanced_city my-advanced-regression
cp advanced/regression/advanced_legacy_qa.gd my-advanced-regression/
godot --headless --path my-advanced-regression --fixed-fps 60 --script res://advanced_legacy_qa.gd
```

All 151 Python tests have passed, including native Blender and Godot asset
round trips, and all 15 command-center catalog packages verify. The final
command-center smoke evidence is in `command_center/demo/advanced-smoke.json`.
Human visual and device review remain pending.

The requested six-agent deployment remains five GPT-6.2 Astra Ultra specialists
and one GPT-6.2 Sol Max integration specialist, working concurrently. The local
command center exports the dispatch plan; model hosting is outside its scope.

## New in v16 — connected vertical environments and character production

Vertical City extends the Metropolis generator with three interacting physical
systems and a shared-world transport. The v15 playable city and exporter remain
available as separate production examples.

- Enter one deterministic, furnished ground-floor building through a retracting,
  collision-backed door. The rear room is an exploration objective.
- Descend through a station lift interaction into an underground two-station
  metro. Walk the platforms, board while stopped, ride the moving carriage and
  disembark at a station. Lifts are explicit transitions, not modeled elevators.
- Aim at three destructible cover panels in the demonstration lab. A real
  physics ray, shot cooldown and damage state control removal, bounded debris,
  and subsequent movement through the destroyed panel. This is localized cover
  destruction, not building-scale structural fracture.
- Save an offline checkpoint from the public surface and restore exploration,
  transit phase, damaged cover and the original city simulation. Interior and
  underground saves are intentionally unavailable.
- In loopback multiplayer, the host publishes validated traffic and civilian
  snapshots on a dedicated ENet channel, including late-join state. Clients
  apply authoritative population state instead of advancing their own. Interior,
  metro and demolition interactions remain offline-only; no internet login or
  production dedicated-server deployment is implemented.
- A separate Blender character factory produces an editable skinned courier,
  portable GLB and named animation clips for reuse in future game projects.

```bash
python3 vertical/build.py vertical/demo_spec.json --output my-vertical-city --vertical-qa
python3 vertical/build.py --verify my-vertical-city
godot --path my-vertical-city
python3 vertical/rig.py --out my-courier
python3 -m command_center.vertical_smoke
```

The shipped project is `vertical/demo/connected_city`. Use WASD, Shift and
mouse look; E operates an entrance, lift or stopped train; left-click aims
and fires from the captured mouse camera; F5/F9 save/restore from the street.
Use the same `--host` / `--join` user arguments as Metropolis below.
The command center can build Vertical City specs and link the fixture's
integrated QA report to the exact project artifact. Custom specs run the
component gates without claiming passage of the fixed-fixture scenario.

The fixed fixture's integrated `reports/vertical-qa.json` records 33 passed
checks, 461 m of physical walking, two furnished rooms, two stations, one
completed train journey, cover destruction, fresh-scene checkpoint restoration,
and live state replication between two scene instances. Seven separate Godot
component scripts are also run per build. The original Metropolis scenario
still passes all 21 checks from the updated source.
The HTTP smoke evidence at `command_center/demo/vertical-smoke.json` also
verifies artifact lineage and stale/pending gates after editing the saved spec.
Human render and device review gates remain pending.

The shipped `vertical/demo/character` includes `courier.blend`, `courier.glb`
and `rig_report.json`. The character has 19 skin joints and eight independently
verified idle, walk, run, crouch, aim, reload, jump and death clips. The factory
reopens the native Blender file, inspects the GLB skin and tracks, and, when
Godot is installed, imports and samples animated bone positions in-engine.
It is a reusable production asset, not yet the city player's visible avatar.

The owner-selected concurrent deployment profile is unchanged: five GPT-6.2
Astra Ultra specialists and one GPT-6.2 Sol Max integration specialist. See
`AGENTS.md` for model configuration and host limitations.

## New in v15 — procedural city production and networked exploration

Metropolis generates deterministic urban layouts from a five-field JSON spec:
seed, blocks (3–8 per side), block size (32–64 m), traffic (0–24), and
civilians (0–40). The canonical layout produces a connected grid, distinct
commercial, residential and industrial districts, parcel setbacks, and solid
building envelopes. The default seed 237 covers 192 × 192 m, with 16 blocks,
35 buildings, 25 intersections, 40 road links, 12 vehicles and 20 residents.

- The Godot scene builds solid facade collisions, street surfaces, sidewalks,
  crosswalks, roof trim, color-coded architecture, batched windows and markings.
  The player can physically traverse all three marked district objectives.
  The city uses a flat ground plane, bounded map and non-enterable buildings.
- Seeded traffic follows clockwise lane loops, signal phases, stop lines and
  vehicle spacing. Civilian residents follow scheduled home/work/leisure routes
  along sidewalks and marked crossings, with visible walking poses and nearby
  greetings. Cars and pedestrians are local simulated visuals, not physical
  crash objects or a unified pedestrian/vehicle collision system.
- Offline checkpoints include player position, tour progress, greeted resident
  IDs, traffic and the civilian clock, with validation before mutation.
- Actual Godot ENet loopback multiplayer synchronizes player positions using
  server-authoritative input, sequence validation and planar building clearance.
  Remote peer visuals appear and disappear on join/leave. This synchronizes
  player movement only; civilian/traffic simulation and tour state remain
  local and offline checkpoints are disabled when connected. It is not an
  internet-ready game server, authentication system or anti-cheat product.

```bash
python3 city/build.py city/demo_spec.json --output my-metropolis --city-qa
python3 city/build.py --verify my-metropolis
godot --headless --path my-metropolis --editor --import
godot --path my-metropolis
```

The shipped ready-to-import project is `city/demo/metropolis`. WASD moves,
Shift sprints, mouse looks, G greets nearby residents, and F5/F9 save/restore
while offline. Visit the marked district rings. On the same workstation:

```bash
godot --path my-metropolis -- --host 8765
godot --path my-metropolis -- --join 8765
python3 -m command_center.city_smoke
```

The new tenth command-center project type permits city spec edits, checked
builds and scenario evidence linked to the exact saved spec. Custom city
builds run component and launch gates, not the default tour scenario. The
default scenario report `reports/city-qa.json` records 21 passed checks,
418 m walked, three district visits, a verified solid-building collision,
simulation restore and real host/client scene integration.

### Cross-engine city export

```bash
python3 city/export.py --layout my-metropolis/city.json --out my-city-assets
```

This produces editable `city.blend`, portable `city.glb`, a manifest,
`unreal-placements.json` (centimeters, Unreal axes), and `mesh-audit.json`.
The exported city is simplified massing (buildings, road spans, junctions),
not the complete decorated Godot runtime. The default export is included at
`city/demo/cross-engine` with 100 mesh instances and 1,200 triangles. The
exporter tests reopen Blender's native file and import GLB through Godot,
checking geometry and placement. Unreal Editor import is not verified.

### Headless simulation profiling

```bash
python3 -m city.profile my-metropolis --output my-city-profile.json
```

The tool accepts one to four verified packages, imports private copies and
samples the city simulation callback for 600 physics frames each. It reports
mean, p50, p95, p99 and maximum CPU wall times plus scene node and instancing
counts. These are local headless timings, not GPU, render or device FPS.
The shipped `city/demo/profile-report.json` compares the default city with
`city/demo/max-city`, a 512 × 512 m example with 154 buildings, 24 cars and 40
residents. `city/maximum_spec.json` reproduces that example. Its launch,
component tests, and integrity passed; full custom-world traversal was not
asserted.

All v14 factories, project packages and the six-agent fast profile remain
available. No new proprietary art or paid provider was used.

## New in v14 — living world systems and production automation

Living World preserves Unified Expedition's streamed terrain, driving, crafting,
trading, scheduled residents and training quest, then adds systemic encounters,
diplomacy, rotating jobs, procedural character animation and medical gameplay.
The command center now has a ninth project kind, Living World, with editable
seed, chunk size, radius and inventory capacity and exact-spec evidence gates.

- Six seeded sentry posts, at most three active enemies, patrol, line-of-sight
  pursuit, lost-sight investigation and return. Physics rays test occlusion;
  bounded local grid searches and capsule sweeps detour around solid objects.
  A hit removes one of two sentry HP; proximity attacks reduce player health.
  The initial expedition unlocks hostile gameplay and the red world marker
  identifies the encounter area. The inherited gun shares ammo across both
  training and hostile combat. Bandages heal up to 24 HP when used.
- Three factions (settlers, rangers, traders) have player standings, symmetric
  relationships, territory ownership and influence. Seeded events advance on
  simulation time; greetings, trading and aid change the simulation. Territory
  labels are abstract strategic state, not physically moving border geometry.
- Choose from three procedurally generated jobs, track ordered/count-based
  objectives, claim credits exactly once, and generate a new set of offers.
  Available activities draw on actual gathering, crafting, trade, driving and
  greetings. Saved progress reconstructs the board from its seed/generation.
- A visible articulated scout patrol demonstrates actual joint transforms and
  blended animation. The reusable rig supports idle, walk, run, sprint,
  crouching, aiming, attacks, hit reactions and a fall-to-ground death pose.
  It is a procedural proxy rig, not a skinned character or ragdoll simulator.
- One atomic checkpoint stores the inherited world plus procedural contract
  progress, diplomacy, enemy identity/position/AI state, defeated opponents
  and player health. Malformed state is rejected before it can mutate gameplay.

```bash
python3 living/build.py living/demo_spec.json --output my-living-world --living-qa
python3 living/build.py --verify my-living-world
godot --headless --path my-living-world --editor --import
godot --path my-living-world
python3 -m command_center.living_smoke
```

The default ready-to-import project is `living/demo/frontier`. In addition to
Unified Expedition controls below, press 1/2/3 to accept a board offer, H to
claim its reward, or J to use a bandage. Finish the training quest, then travel
toward the red encounter marker beyond the outpost. F5/F9 operate on one
world-scoped living checkpoint while on foot. The integrated QA scenario uses
real movement, gathering and collision events, including damage, heal, enemy
defeat and restoration into a freshly instantiated scene.
The shipped `reports/living-qa.json` has 28 passed checks and records 47.26 m
driven, 72.01 m walked, two hostile hits and restored health. The independently
rebuilt Unified Expedition also passed all 26 prior scenario checks.

### Multi-world build matrix

```bash
python3 -m living.matrix --output my-matrix --seeds 237 238 239 --workers 2
```

The matrix supports up to 16 distinct specifications and 4 concurrent workers,
with isolated output, logs, integrity checks, timings and a single JSON report.
All worlds run headless import, launch and fourteen component suites; only
the exact default fixture receives the scripted scenario gate. This distinguishes
component/build readiness from demonstrated custom-world playability.
The included `living/demo/matrix-report.json` records the successful seed
237/238/239 matrix; its artifact paths refer to that separate matrix run.

### Authoritative local replication toolkit

```bash
python3 -m living.network smoke --report my-network-smoke.json
python3 -m living.network serve --port 0
```

The separate Python standard-library toolkit runs a real local TCP server on
loopback, with configurable fixed-tick authoritative motion (30 Hz in the
smoke test), validated length-prefixed JSON,
ordered inputs, interest-filtered snapshots and short-lived, rotating reconnect
tokens. Up to 16 clients are supported by the protocol; the included smoke test
exercises two simultaneous clients, remote movement, replay rejection, leave,
interest filtering and position-preserving reconnect. It is deliberately not
connected to the Godot world yet, not a production online server, and not a
substitute for internet authentication, encryption or deployment testing.

Headless tests do not establish visual quality or performance on target hardware.
The v14 release retains all existing v13 factories and demo packages.

## New in v13 — integrated open-world expedition

Unified Expedition combines the Frontier Lab world, inventory, gathering and
factions with the arcade vehicle, scheduled NPC population, finite-stock
economy, four-stage expedition quest and a collision-based target range.
The default simulation clock completes one game day in 120 real seconds.
NPCs follow home, work, leisure and commute schedules; this is a deterministic
schedule simulation rather than collision-aware navigation.

- Gather two wood and one stone, then craft a tool. Drive through the
  checkpoint, park, sell the tool at the outpost and defeat the training drone.
  The quest rejects out-of-order progress and awards 25 credits exactly once.
- Vehicle boarding, trading and exit require physical proximity or safe
  conditions. The terrain streaming window follows the active controller.
- Seeded prices, finite stock and bounded credits protect atomic inventory
  transactions. Buying bandages and selling tools update inventory and wallet
  together; failed transactions have no effects.
- Actual raycasts hit the range drone, which requires two hits. Ammunition,
  reload, cooldown and target state are persisted. NPCs are not combat targets.
- An atomic, checksummed save includes world progress, NPC clock, parked
  vehicle, credits, stock, quest progress and range state. Invalid snapshots
  are rejected before changing gameplay state.
- The command center adds a Unified Expedition project type and a verified
  default fixture; changes invalidate previously saved scenario evidence.

```bash
python3 unified/build.py unified/demo_spec.json --output my-unified --unified-qa
python3 unified/build.py --verify my-unified
godot --headless --path my-unified --editor --import
godot --path my-unified
python3 -m command_center.unified_smoke
```

The ready-to-import project is `unified/demo/expedition`. WASD and mouse move
and look; Shift sprints, F gathers, G greets, C crafts a tool, B crafts a
bandage, E boards or exits, Space jumps or brakes, V sells a tool, T buys a
bandage, left mouse fires and R reloads. Save and restore on foot with F5/F9.
The objective HUD and world markers guide the default excursion.

The packaged default scenario passed 26 headless checks, including a 46.85 m
measured driving leg through streamed chunks and a 11.90 m measured walking
leg. It completed with 62 credits, nine active chunks and thirteen NPCs. The
factory runs ten component suites and launches the actual project. The
package's `reports/unified-qa.json` records the exact fixture evidence.
Custom worlds use component and launch gates; the scripted default scenario
is not evidence that every custom world is beatable. The quest title is seeded,
but the objective sequence is fixed. This is a single-player prototype, not a
multiplayer, general-purpose hostile AI or rendered/device-performance test.
All earlier factories and their demonstration projects remain intact.

## New in v12 — default six-agent fast profile and Frontier Lab

All Team work orders now use a canonical fast profile: five GPT-6.2 Astra
agents at ultra reasoning, one GPT-6.2 Sol at max reasoning, six concurrent
slots, and a priority-service preference. Export the dispatch plan from the
Team view to a compatible agent host. The local command center does not itself
launch language-model sessions; the exported data is a handoff, and priority
is a requested host setting rather than a guaranteed speed or a separate
supported `spawn_agent` parameter. No API credentials are stored by Studio.

Frontier Lab is a standalone Godot project with streamed flat ground and
seeded trees and rocks. The default 32 m cells and radius one keep nine cells
(96 × 96 m of active terrain) loaded while the player travels beyond that
window. Each active cell has one or two wandering NPCs, with deterministic
identities and faction colors. NPC position follows a shared simulation clock.
The generation preview supports 16–64 m chunks and radius 1–2, with nine or
twenty-five active cells. These are bounded active sets, not a fully authored
open-world map or an asynchronous terrain engine. Decor and NPCs are visual,
not collision-aware agents; the terrain itself is physically collidable.

- Resource markers offer wood, stone and fiber; harvested identities persist
  across unload/reload and checkpoint restore. An inventory unit-capacity
  limit protects atomic collection and crafting. Craft a tool from two wood
  plus one stone, or a bandage from two fiber.
- Settlers and rangers have separate bounded reputation; a nearby NPC can
  grant a one-time positive greeting reward. Allied/hostile classifications
  are reputation states, not combat behavior or dynamic diplomacy.
- Save/reload restores position, inventory, reputation, collected resource
  IDs, greeted NPC IDs and the shared NPC motion clock. Checkpoints have an
  atomic replacement and checksum envelope, and a mismatched world is rejected.
  The default save slot is scoped to the world specification.
  Saves allow up to 4096 harvested and greeted IDs each and bounded coordinates;
  the checksum detects damage, not malicious modification by a trusted operator.
- The seventh command-center project type has a seed, cell size, active radius
  and inventory capacity editor, a live grid preview and checked build jobs.
  Editing the saved specification invalidates its old QA and dispatch digest.

```bash
python3 openworld/build.py openworld/demo_spec.json --output my-frontier --openworld-qa
python3 openworld/build.py --verify my-frontier
godot --headless --path my-frontier --editor --import
godot --path my-frontier
python3 -m command_center.openworld_smoke
```

The included `openworld/demo/frontier` is the verified default Godot fixture.
WASD moves, Shift sprints, mouse looks, F collects a nearby marker, G greets
a nearby NPC, C crafts a tool, B crafts a bandage, F5 saves and F9 restores.
Headless QA physically traverses east and negative-coordinate chunks, collects
materials, crafts, greets an NPC, and restores progress in a new scene. Custom
specs run all five component tests and launch verification; the exact default
fixture also runs the 23-check expedition scenario. Render review and device
performance are not established by headless QA. Previous studio capabilities
remain intact.

## New in v11 — expedition simulation

The standalone simulation factory adds editable world simulations on top of
verified world packages. The Relay Basin demonstration is 96 × 96 meters,
with an open driving corridor, service stations, props, and a three-stage
expedition: activate the relay on foot, drive through the checkpoint, and
reach the final goal on foot.

- Arcade vehicle with acceleration, reverse, steering, braking, solid collision,
  animated wheels, proximity-based entry, and clearance-checked exit.
- Clear, rain and fog weather; a configurable day/night cycle controls actual
  lighting and environment fog. Rain uses animated 3D drop geometry.
- One-shot beacon, supply and switch markers with a two-meter activation radius.
- Ordered mission events reject skipping and duplicate stages. A Python seeded
  mission generator can select targets from supplied ID pools.
- Command center simulation project type, climate controls, route/marker preview,
  JSON spec editor, build evidence, and a scenario QA gate. The six-role work
  order template now reflects five Astra Ultra and one Sol Max; it is not an
  embedded agent API.

```bash
python3 world/build.py simulation/world_spec.json --assets demo/first-batch --output my-relay-basin --route-qa
python3 simulation/build.py simulation/demo_spec.json --world my-relay-basin --output my-expedition --simulation-qa
python3 simulation/build.py --verify my-expedition
godot --headless --path my-expedition --editor --import
godot --path my-expedition
python3 -m command_center.simulation_smoke
```

The included `simulation/demo/expedition` is the ready-to-import Godot project.
WASD moves on foot or drives; E enters/exits when near and stopped; F activates
the current mission object; Space jumps/brakes; T cycles weather. Mouse looks
around on foot. The checkpoint is a cyan ring. The objective HUD gives the
current stage. Mission generator usage:

```python
from simulation.mission_generator import generate_mission
stages = generate_mission(511, interact_ids=["relay", "supply"],
                          drive_ids=["checkpoint"], visit_ids=["goal"])
```

All generated target IDs must exist in the actual simulation specification and
world. The current factory supports one driving checkpoint and one world goal.
Custom specs run component tests; only the dedicated default fixture claims full
expedition QA. The command center retains the scenario evidence for the exact
saved specification, and edits invalidate it. The vehicle is an arcade
character-body controller, not a tire/suspension simulator. Interactive markers
are mission objects, not inventory, physics switches, or replicated multiplayer
state. Headless simulation does not establish rendered appearance or GPU/device
performance. The preceding studio factories remain intact.

The shipped `reports/simulation-qa.json` records 17 checks, including rejected
out-of-order actions, a 19.31 m physics-driven vehicle leg, measured braking
versus coasting, and a final walk ending within 0.1 m of the goal. The separate
world route report records 21.87 m of physical walking with zero horizontal
collisions. `command_center/demo/simulation-smoke.json` captures the actual API
build, verification, scenario gate and stale-on-edit behavior. Read these
reports as headless behavior evidence, not rendered performance measurements.

## New in v10 — tactical squad and destructible cover

Gameplay projects support two independent optional controls:

- `tactical: true` enables shared sighting memory and coordinated squad roles.
  Guards report real line-of-sight observations; an alert expires after five
  seconds without refresh. Loss of line of sight leads to investigation of
  remembered information, rather than privileged access to the unseen player.
- `destructible_blocks: ["qa_wall"]` selects actual block IDs in the source
  world. Cover absorbs two 25-HP hits before losing its collision and mesh;
  navigation updates and destroyed cover is included in checkpoint state.

On the command center's gameplay workspace, enable the controls and save the
specification before building. The exact tactical training fixture also runs
the controlled tactical scenario QA, which is distinct from package integrity.
Custom encounters are validated and run the module tests but have no claimed
full encounter QA unless a suitable scenario is supplied. Changed specs make
the old build and tactical review gates stale.

```bash
python3 gameplay/build.py gameplay/tactical_spec.json --world world/demo/training_yard --output my-tactical-yard --tactical-qa
python3 gameplay/build.py --verify my-tactical-yard
python3 production.py --seed 240 --output my-tactical-batch --tactical --destructible-count 6
python3 -m command_center.tactical_smoke
```

The new production batch options select destructible IDs in the actual
generated world and enable tactical guards. They do not guarantee each
procedural encounter is beatable. Destruction is a stateful local scene
prototype, not a rigid-body fracture, debris simulation, or replicated
multiplayer destruction engine. Human visual review and device performance
remain pending. Existing source factories and prior built examples remain
preserved; gameplay specs without these controls use the legacy AI behavior.

Verified v10 examples: `gameplay/demo/tactical_yard` contains the 14-check
real tactical fixture; `tactical-production-demo/seed-240` contains the 32-cover,
six-guard procedural encounter with eight destructible blocks. The fixture's
14 checks include real sightline sharing, 300-frame memory expiry, two-hit
destruction, 11-to-5 m route shortening, checkpoint restoration in both
directions, guard elimination, and 11.32 m physical extraction. Controlled
setup repositions actors; extraction uses the controller without jumps in
position. See `command_center/demo/tactical-smoke.json` for API evidence.

The Studio's new six-role work-order template reflects four Astra and two Sol
specialists; it remains a template, not an autonomous model API inside the app.

## New in v9 — procedural production and physical playtesting

World projects now have a **Procedural arena** form. Set a seed and cover count,
generate a draft, review or edit it, save, then queue a build. The generated
48 × 48 m arena uses a repeatable layout, 1–40 cover blocks, six reused props,
and a central barrier. A conservative 1 m grid planner uses a 0.65 m collider
clearance and continuous segment intersection checks, then simplifies the route.
The planner solves only the flat core; an unsuccessful search does not prove
that jumping, off-core terrain or a finer grid cannot offer another path.

Every command-center world build now gates publication on real Godot player
traversal: the physics-driven actor must follow every waypoint, trigger the
goal, finish within 0.1 m and avoid horizontal collision contacts. The QA
report includes travel distance, tick count, simulated seconds and headless
wall duration. The latter measures an accelerated CPU/headless scene run,
not rendered FPS or target-device performance. Route tests run at fixed 60 Hz.

```bash
python3 -m world.procedural 237 my-level.json --cover 24
python3 world/build.py my-level.json --assets demo/first-batch --output my-world --route-qa
python3 production.py --seed 237 --seed 238 --seed 239 --output my-production-batch
```

The batch runner chains each generated and verified world into the gameplay
factory, produces four guards by default, runs the gameplay import, launch
and module tests, verifies both packages and retains a per-seed report.
It does not yet drive a combat encounter to mission completion, validate
all enemy tactics, or measure GPU performance. `production-demo/` contains
the verified examples and their reports. The UI's generator creates a draft
without modifying the saved project until the user explicitly saves it.
Build jobs also record a canonical SHA-256 specification identity. A successful
older build is marked stale if the saved specification changes; it no longer
qualifies as a release candidate. Historical v8 jobs lack this identity and
must be rebuilt before qualifying for a v9 release.

## New in v8 — one local production interface

Launch the command center from the extracted studio directory on Linux:

```bash
python3 -m command_center.server --workspace ../studio-workspace
```

Open `http://127.0.0.1:8765` in a browser. Python's standard library serves the
interface; no frontend dependencies, cloud login or internet connection are
needed. The underlying factories still require their existing Godot and Blender
executables (`godot`, `blender52`) and Python dependencies. Use `--port` to
select a different local port. Stop the server with Ctrl+C after jobs finish.

The Projects view creates five types of projects, each based on the shipped
factory specification. Workspace edits and saves JSON; world and cinematic
projects also have visual placement and timeline controls. Gameplay and
multiplayer still use the shipped training yard, and multiplayer's specification
is fixed. The catalog inspects the six shipped packages, verifies their SHA-256
inventories and exposes model, animation and sound metadata. The build queue
executes fixed factory commands sequentially, saves a validated spec snapshot,
records command exit codes and durations, and shows logs. A new build output
is isolated under `studio-workspace/jobs/<job-id>/output`.

The Team view drafts work-order templates for five Astra Ultra specialists
and one Sol Max build-operations specialist. It shows build and verification
evidence. Agent launches require an authorized host. A release candidate is
a recorded build snapshot that passed the package verifier. Human render
and device review remain pending.

The service is loopback-only, has a same-origin write guard, validates project
IDs and specs, and serves only allowlisted catalog media. It is designed for a
trusted single local operator, not for deployment as a public or multi-user server.

Run the HTTP and real world-builder acceptance checks:

```bash
python3 -m unittest discover -s tests
python3 -m command_center.smoke
```

See `command_center/demo/smoke-report.json` for the recorded end-to-end build
and verification evidence. Access prior factories directly using the included
CLI instructions below.

## New in v7 — original cinematic production

The cinematic factory generates an original, seeded 24 × 30 m street set with
six modular building façades, windows, lanterns, pavement, road geometry and
materials. It also builds a 16-joint skinned mannequin with six genuinely keyed
animations (Idle, Walk, Run, Aim, Crouch and Reload), and synthesizes original
ambience, footsteps and thunder WAVs without external samples.

```bash
python3 cinematic/build.py cinematic/sequence.json --output my-cinematic --demo-qa
python3 cinematic/build.py --verify my-cinematic
godot --headless --path my-cinematic --editor --import
godot --path my-cinematic
```

The included `cinematic/demo/nightfall_patrol` project runs a 10-second,
three-shot cinematic from an editable JSON timeline. Space pauses; R restarts.
The timeline interpolates camera position, framing and actor blocking, samples
the imported skeleton animation, and drives fog, rain particles, lighting and
spatial audio sources. `--demo-qa` checks the supplied fixture; custom timelines
need their own shot/animation acceptance. The editable `.blend` files are in
`source/`, outside Godot's import scan; engine assets are in `assets/`.

`preview.png` is a CPU-rendered Blender review frame made from actual GLB
exports, not a fake screenshot or an exact runtime frame. The builder requires
Blender 5.2.4, Godot 4.7.2 and Python with Pillow (for raster sanity checks).
The scope is a stylized set, not a finished city gameplay map; no building
interiors, walkable collision, photoreal visual quality, rendered Godot frame,
audio listening acceptance, or target-device performance is claimed.


## New in v6 — host-authoritative multiplayer

The multiplayer factory adds a standalone Godot ENet arena to the studio. It
keeps the v5 single-player and v4 world factories untouched. The arena supports
a local listen host and direct-address clients, a roster with readiness and
host-only start, server-side character physics, raycast player combat, a
server-driven NPC, health/ammunition, and 10 Hz state snapshots. The lobby
has a 16-player configured cap (host plus 15 clients).

```bash
python3 multiplayer/build.py --world world/demo/training_yard --output my-network-arena
python3 multiplayer/build.py --verify my-network-arena
```

The shipped `multiplayer/demo/network_arena` has the verified layout. The
factory currently requires the exact training-yard layout because spawn slots
and NPC placement are fixture-specific. After extracting, import the project
with Godot before launching it; the derived import cache is not packaged.

```bash
godot --headless --path multiplayer/demo/network_arena --editor --import
godot --path multiplayer/demo/network_arena -- --host --port=23777
# In a second terminal:
godot --path multiplayer/demo/network_arena -- --join=127.0.0.1 --port=23777 --name=Player2
# Run an isolated loopback test with four remote clients:
python3 multiplayer/stress.py --project multiplayer/demo/network_arena --output my-test-run --clients 4
```

F2 toggles ready, Enter starts the match on the host, WASD moves, mouse aims,
left mouse fires, R reloads, Escape releases the cursor. Default server bind
is loopback; only for a trusted private LAN, a host may explicitly supply
`--bind=0.0.0.0` and clients use the host's LAN address. No internet service,
accounts, public matchmaking, host migration, relay, or port forwarding is
installed or enabled. Do not expose this prototype to the public internet.

Security boundary: the client supplies movement intent, aim and buttons, not
position, player ID, damage amount, hit target, or ammunition. The host derives
identity from the RPC sender, applies physics and ray queries, caps command
rate, rejects stale/out-of-range input, expires stale movement, and disables
peer-to-peer relay. This is a foundation, not production anti-cheat or
authentication. Read `multiplayer/demo/VERIFICATION.md` for measured results.


## New in v5 — reusable gameplay production

The gameplay factory layers a single-player FPS encounter over a verified v4
world without modifying the source. It adds capsule-visual AI guards, 0.5 m
grid A* navigation, patrol/chase/attack behavior, physics-ray hitscan combat,
health and ammunition, reload, elimination objectives and extraction, and a
local JSON checkpoint with validated state restoration.

```bash
python3 gameplay/build.py gameplay/demo_spec.json --world world/demo/training_yard --output my-combat-level --demo-qa
python3 gameplay/build.py --generate 238 --count 3 --world world/demo/training_yard --output another-encounter
python3 gameplay/build.py --verify my-combat-level
godot --editor --path my-combat-level
```

The shipped `gameplay/demo/combat_yard` has two guards; `seed_238` is a
separately generated three-guard encounter. The seed chooses guard placements
and patrol routes, with bounded clear-space validation. `--demo-qa` applies
only to the fixed two-guard fixture; generated layouts are imported, launched
and module-tested, not guaranteed to be beatable. Custom maps require their own
path and mission acceptance testing.

Controls: WASD, mouse, Shift sprint, Space jump, left mouse shoot, R reload,
F5 save, F9 load, Escape release cursor. Defeat every guard, then physically
reach the green extraction marker. Checkpoints preserve health, ammo, mission
progress and actor positions, not every transient animation, path or timer.

The AI and weapon are intentionally starter implementations: no multiplayer,
advanced tactics, finished character/weapon animations, or graphics/device
playtest is claimed. See `gameplay/demo/VERIFICATION.md` for evidence.


## New in v4 — playable world production

The world factory converts a bounded JSON level specification and a verified
asset batch into an editable, standalone Godot project. It builds terrain with
mesh collision, static cover, boundary walls, placed GLB props, lighting, spawn
and goal markers, and a first-person player with a simple completion HUD.

```bash
python3 world/build.py world/demo_spec.json --assets demo/first-batch --output my-new-level --demo-qa
python3 world/build.py --verify my-new-level
godot --editor --path my-new-level
```

The included `world/demo/training_yard` is a ready-made example. Open its
`project.godot`, edit `world.tscn`, or run the main scene. Controls: WASD, mouse,
Shift to sprint, Space to jump, Escape to release the mouse. The green goal
triggers the completion HUD. The blueprint is a plan view, not a game screenshot.

The builder validates input, checks source asset hashes, bakes a native scene,
imports and launches the project headlessly, and emits a manifest and logs.
`--demo-qa` additionally exercises physical movement and traversal for the
training-yard fixture specifically; custom layouts need their own gameplay tests.
The generated output cannot overwrite an existing directory. Failed builds
retain staging diagnostics. Verify a pristine package before opening or editing
it; the editor may write derived import data and cache files.

The complete test evidence is available in `world/demo/VERIFICATION.md` and
`world/demo/training_yard/reports/`. Interactive visual, hardware performance,
and broader gameplay acceptance are still pending.
Historical workstation dashboard and registry snapshots are omitted from the
public distribution. Re-register the toolkit at its new location for live
coordination after moving or extracting it. Sealed synthetic fixture reports
remain intact so their manifests can be independently validated.

## New in v3 — automated asset production

The asset factory adds a working, local batch pipeline using Blender 5.2.4 LTS
and Godot 4.7.2. It preserves the v2 studio task manager and audit. It creates
original procedural assets from a bounded JSON design specification, not from
arbitrary reference images. Current recipes are starter assets, not finished
AAA game art.

```bash
python3 factory/build.py factory/demo_spec.json --output my-new-batch
python3 factory/build.py --verify my-new-batch
```

Each batch has:

- editable `assets/*.blend` and engine-ready `assets/*.glb`;
- original-source provenance and the normalized specification;
- actual Godot-import geometry, triangle, material and bounds checks;
- skin, bone and animation checks for character assets;
- Blender and Godot logs and JSON reports;
- a SHA-256 manifest covering the batch inventory.

The factory stages new data separately and only commits the destination
directory if its validation passes. It refuses to replace an existing output.
On failure, it retains diagnostic staging for inspection. It does not inject
assets into any existing project or change approved engine choices.
Hashes detect accidental or unrecorded changes relative to the manifest;
they are not a digital signature or a substitute for a source-control review.

### Recipes

| Kind | Variant | Parameters |
|---|---|---|
| prop | crate, barrel, barricade | size_m, RGB color |
| character | articulated training mannequin | height_m, RGB color |

Each record also supports `max_triangles`, `max_materials`, and
`max_file_bytes` budgets. Up to 32 records per batch; Blender and Godot jobs are
serialized to preserve memory. The mannequin uses a segmented shell with
one skinned mesh, a 16-bone rig, and a looping idle clip. The Godot animation
name is `Idle`. It is a rigging pilot, not a production-ready humanoid
with retargeting, walk/run, facial rig, or complete FPS animation library.
The shipped demo uses original procedural meshes and materials, with no
external models or paid generation service.

### Integrate quality gates with studio tasks

From this toolkit directory, register a trusted project source and declare a
task and gate; use the actual generated batch as verification input:

```bash
python3 studio.py register factory --name "Asset factory" --source "$PWD" \
  --objective "Verify generated assets" --engine Godot --platform Linux
python3 studio.py task factory batch --title "Validate batch integrity" \
  --owner "Astra QA" --acceptance "Package inventory and file hashes match"
python3 studio.py gate factory "Batch integrity" --task batch
python3 studio.py run factory batch -- python3 factory/build.py --verify my-new-batch
python3 studio.py report
```

Headless engine validation does not establish rendered appearance, collision
gameplay, target device performance or animation deformation quality. Those
remain separate acceptance gates, with human review when appropriate.

See `demo/first-batch` for the actual validated sample assets and evidence.
The historical private-run dashboard and logs are omitted from public releases.
The included `demo/asset-preview.png` is a CPU-rendered review image of the
actual GLB exports (not concept art). Regenerate the demo preview to a new
destination:

```bash
blender52 -b --factory-startup --python-exit-code 1 \
  --python factory/render_demo.py -- "$PWD/demo/first-batch/assets" "$PWD/demo/new-preview.png"
```

## New in v2

This edition turns the operating handbook into an executable local control
center. Python 3.11+ is required; there are no third-party Python dependencies.
The asset audit and pipeline test run on Linux/WSL (POSIX).

- Register verified project roots, objectives, engines and target platforms.
- Define agent work orders with explicit ownership, scope, dependencies and
  acceptance criteria. Generate copy-ready assignment briefs.
- Run a trusted verification command explicitly. Capture its combined log, exit
  code, duration, timestamp and SHA-256 checksum. A failed command cannot pass.
- Block dependent work orders until their prerequisite evidence passes. Re-running
  a prerequisite resets downstream status; missing or tampered logs block gates.
- Create quality gates linked to verified tasks; human/device gates stay pending.
- Generate an offline, responsive HTML dashboard and a text report.
- Audit asset inventory and size budgets, licensing records, attribution,
  case-insensitive path collisions and symlinks without following them.

### Quick start

From the extracted toolkit directory (replace the project path with an existing
authoritative root; the registry is only a coordination index):

```bash
python3 studio.py register demo --name "My game" --source /path/to/project \
  --objective "Build a playable slice" --engine Godot --platform Windows
python3 studio.py task demo base --title "Verify baseline" --owner "Astra QA" \
  --acceptance "Headless baseline test exits 0" --scope "tests only"
python3 studio.py gate demo "G0 baseline" --task base
python3 studio.py gate demo "G4 physical device acceptance"
python3 studio.py brief demo base
# Replace with the project's REAL test command; never use a dummy pass.
python3 studio.py run demo base --timeout 120 -- godot --headless --path . --quit
python3 studio.py report
python3 studio.py dashboard studio-dashboard.html
```

Open the generated HTML file in a browser. Use `--state /path/to/studio.json`
before the subcommand to select the registry. The lead is the single writer;
agents should run their own tests and return evidence rather than editing this
registry concurrently. Back up state and its evidence folder together; register
the correct source path again when moving to a different machine. A task pass
proves the exact recorded command ran successfully, not that the current source
has never changed or that an arbitrary test covers the full acceptance criteria.
Re-run affected checks after changes. Review source and test scope before release.
Only run trusted commands. Do not put credentials in arguments or output logs.

### Asset compliance

Place `provenance.json` in the asset directory, using a top-level array:

```json
[
  {
    "path": "props/crate.glb",
    "source": "Original studio creation, artist and date",
    "license": "Studio-owned",
    "attribution": "Not required"
  }
]
```

```bash
python3 asset_audit.py /path/to/project/assets \
  --max-file-bytes 52428800 --max-total-bytes 1073741824
```

Those are example budgets, not universal production limits. The audit returns
JSON and a nonzero exit code for hard failures. It verifies presence/consistency
of records, not legal redistribution rights; the producer reviews actual terms.

### Test the toolkit

```bash
python3 -m unittest discover -s tests -v
bash verify-workstation.sh
```

Regenerated dashboard snapshots show recorded Studio verification, not the
completion of any external project.

## Purpose

The project's creative director owns the design. The lead agent coordinates production,
preserves approved design decisions, and delivers verified improvements. This kit
is reusable across independent game, engine, tooling, and research projects.
It does not migrate any existing project or grant access to unrelated accounts.

## Activate it

In a project conversation, say:

> Activate the studio. Work on [project and objective]. Spawn Astra specialists
> where useful. Keep moving through authorized, verifiable milestones. Preserve
> existing canon, provide progress and evidence, and bring me the next real
> decision or completed deliverable.

Each session begins by locating the current authoritative repository, GDD, or
artifact; checking the environment; and stating the precise milestone. Do not
rely on old conversation alone. Do not invent engine choices or restart working
projects. Agents are created on demand, not permanent background employees.

## Staff and ownership

The lead producer/architect coordinates the objective, scope, dependencies,
interfaces and final integration. The current six-role Midnight Shift uses
the following ownership and handoffs (see [AGENTS.md](AGENTS.md) for exact
model and dispatch policy).

| Specialist | Owns | Required handoff |
|---|---|---|
| Count Blueprint | Architecture, engine interfaces, world and system design | Interface contract, implementation plan and evidence |
| Major Mayhem | Movement, combat, interaction, AI, rules, networking | Playable feature slice, focused tests and tuning values |
| Doctor Doomcheck | Independent verification, defects, performance and quality | Repro steps, test logs, severity and release checklist |
| Madame Glitch | UI, player feedback, HUD, controls and accessibility | Interface implementation, interaction checks and evidence |
| Grimbrush | Models, textures, materials, animation and environment content | Editable source, exports, provenance and visual checks |
| Baron Buildgrave | Builds, packaging, release and production operations | Reproducible build, package evidence and known limitations |

The lead owns integration. Agents work in separate files/directories or branches;
never let two edit the same shared asset simultaneously. Assign concrete slices
with prerequisites and acceptance tests. Use fewer agents for small tasks.
Swap specialists for UI/audio, networking, documentation or research as needed.

## Production cycle

1. **Intake:** locate source of truth, verify repository and engine versions,
   identify acceptance requirements, protect user changes.
2. **Plan:** choose a small end-to-end milestone, define interfaces, sequence
   dependencies, estimate scope and risks. Record in tasks/plan.md and tasks/todo.md
   or the existing issue tracker.
3. **Build:** implement on scoped branches/paths; add tests and asset source.
   Work in parallel only after dependency contracts are fixed.
4. **Integrate:** lead reviews diffs and asset imports; run the integrated test
   suite, actual build and available visual checks. Fix material defects.
5. **Accept:** report pass/fail/blocked with evidence and build identifier.
   Never label a feature complete solely because source exists.
6. **Checkpoint:** preserve verified source, export or reproducible build notes,
   test artifacts and decisions in their natural project owner. Continue only
   within the authorized milestone.

## Shared quality gates

- G0: engine/tool versions and repository baseline confirmed.
- G1: objective and interfaces defined; assets have documented license/source.
- G2: feature runs, unit/logic tests pass, no regressions.
- G3: independent review; verify actual asset import, scale, animation, navigation
  and gameplay where applicable.
- G4: target platform build and device/playtest results; explicitly mark pending
  when no target device or GPU is accessible.
- G5: deliver reproducible checkpoint, release notes, known limitations and
  clear next action. No public publication or paid service without authorization.

### Engineering standards (technical specialist review)

- Separate gameplay rules from rendering/input so tests can exercise them headlessly.
  Pin engine versions; clean-import a checkout and execute focused scene/runtime tests.
- Multiplayer: establish state authority, protocol schemas and versioning before
  concurrent implementation. Verify host/server and two local clients with join,
  play, disconnect, reconnect and state convergence; record separate logs.
  Real WAN/packet loss performance requires a separately measured run.
- Set explicit memory, load time and frame-time targets by platform. Serialize
  heavy Blender/Godot jobs on this workstation. Record platform export separately
  from device launch, visual fidelity, controller/audio and frame pacing.
- Use short-lived branches, one owner per binary asset, tracked source and Godot
  UID files, ignored generated caches, and Git LFS where configured and warranted.
  Release manifest: commit, build checksum, exact test commands and outcomes,
  device type, unresolved risks.

### Content standards (art and animation specialist review)

- Agree on scale in meters, axes, pivots, stable names, reusable material and
  texture budgets based on the lowest-spec target, and glTF/GLB export settings.
- Retain editable Blender source and preview at gameplay distance; maintain a
  pilot scene with representative assets, lighting and camera.
- Treat skeleton/rest pose, attachment bones, clip names, loop and root-motion
  conventions as interfaces. Test a pilot idle/turn/attachment, foot contact
  and deformation, then retest clips whenever the skeleton changes.
- Validate graybox traversal using the actual player dimensions, camera,
  step height and jump reach before final art. Test doors, stairs and seams.
- Use Godot wrapper scenes for gameplay/collision overrides so reimports do
  not erase them. Reimport representative content twice; test materials,
  transforms, clips and transitions. Compare fixed-camera screenshots.
- Record creator/source, license, attribution, third-party modifications and
  affected files for every introduced asset; confirm redistribution rights.
  CPU/headless import proves functional data, not beautiful rendered output.

## Current workstation baseline

Verified 2026-11-20: Linux x86_64; 9 logical CPU cores; about 9.7 GiB RAM;
Godot 4.7.2 and Blender 5.2.4 LTS available. Blender 5.2 is invoked with
`blender52`; the system Blender 4.3.2 is retained for compatibility.
No GPU device was available for dedicated hardware acceleration.
Git, Python, Node, GCC/G++ and FFmpeg were found.

Prefer small assets, Compatibility renderer when appropriate, short CPU renders,
headless test runs and limited parallel heavy processes. Do not assume virtual
hardware benchmarks predict physical handheld or Android devices. Re-check resources and
tool availability for every new workspace.

Run the included `verify-workstation.sh` to prove Blender → glTF → Godot import
and runtime loading. It is a small integration smoke test, not proof of FPS,
graphics fidelity, GPU availability or production game performance.

### Verified initial integration run

2026-11-20, exit code 0:

- Blender 5.2.4 LTS hash cd5dc428cce1: generated cube and exported GLB.
- Godot 4.7.2 stable ed1daf0bf: imported scene and instantiated mesh.
- Markers: STUDIO_EXPORT_PASS, STUDIO_IMPORT_PASS, STUDIO_SMOKE_PASS.
- Headless only; no device or hardware-rendered gameplay acceptance.
- The two independent Astra reviews supplied engineering and content standards;
  the lead executed the integration test.

## Portfolio boundaries

Keep project registries, unpublished design documents, credentials and source
repositories separate from the public Studio toolkit. Adoption does not change
project priorities, engine choices or unrelated source files.

## Agent work order template

- Project and authoritative sources:
- User-approved objective and constraints:
- Agent's specific outcome:
- Allowed paths/actions:
- Excluded paths/actions:
- Interface/version prerequisites:
- Acceptance tests (observable):
- Expected output (paths, test results, limitations):

## Status report template

Milestone: [specific outcome]
Status: [not started / active / pass / fail / blocked]
Evidence: [actual source path, command, build output, visual artifact]
Progress: [accepted tasks / planned tasks, not invented overall percentages]
Risk or limitation: [specific unverified area]
Next: [within scope or precise user decision]

## Continuity

Maintain the canonical project repository and its own design documents rather
than one duplicate mega-ledger. Retain milestone artifacts and checkpoints
durably. On a new session, load this kit and the project source; recreate the
team as appropriate. Durable storage is not an always-on working process.
