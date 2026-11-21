"""Versioned, original game-production playbooks for the Studio's specialists.

This augments work orders with instructional context; it does not train model
weights, grant permissions, execute exercises, or establish completed work.
"""

from copy import deepcopy

from .provenance import spec_digest


def _track(identifier, title, roles, workflow, deliverables, verification, exercise):
    return dict(id=identifier, title=title, roles=roles.split(), workflow=workflow,
                deliverables=deliverables, verification=verification, exercise=exercise)


_TRACKS = [
    _track('game-design', 'Game design and systems', 'architecture gameplay ui verification', [
        'Define player fantasy, target audience, core loop, session length, and the explicit win/failure conditions before adding features.',
        'Prototype the smallest playable loop; identify decisions, risk/reward, feedback, progression, and resource sinks.',
        'Balance with explicit variables and scenarios; separate player skill from random outcomes and test edge cases.',
        'Use playtest observations to revise mechanics; preserve accepted design constraints and maintain a decision log.'
    ], ['One-page design brief and prioritized vertical-slice scope.', 'Rules/state diagram, tunable balance table, and playtest scenarios.'], [
        'Run a complete start-to-finish loop including failure and recovery.', 'Measure rule consistency, timing, economy invariants, and player comprehension; label human judgments unverified until tested.'
    ], 'Prototype a scavenging loop with a resource cost, reward, loss condition, and three balance scenarios.'),
    _track('game-development', 'Game development and gameplay engineering', 'architecture gameplay build_operations verification', [
        'Separate input, simulation, presentation, persistence, and networking; document ownership and stable interfaces.',
        'Implement deterministic state transitions, data-driven tuning, bounded resource lifetimes, and explicit error paths.',
        'Use fixed-step simulation where necessary; distinguish local prediction from authoritative multiplayer state.',
        'Write focused tests before logic changes, validate save/load compatibility, then run the engine build and integration suite.'
    ], ['Small runnable vertical slice with source and config under version control.', 'Architecture/data contracts, automated test cases, reproducible build instructions.'], [
        'Test state transitions, invalid input, frame-rate variance, save/reload, and cancellation.', 'Verify the exact build, compare real logs, and test multiplayer ownership/replication if applicable.'
    ], 'Implement a deterministic interaction system with inventory limits, rejection cases, and save/load round-trip.'),
    _track('modeling', '3D modeling and asset construction', 'content architecture verification', [
        'Start from legal references and orthographic proportions; block out silhouette, scale, pivots, and functional dimensions.',
        'Model with clean topology, intentional edge flow, usable normals, and appropriate geometry density; sculpt detail only where it contributes.',
        'Prepare names, transforms, mesh separation, collision proxies, and LODs using engine-specific import conventions.',
        'For rigged characters, preserve deformation loops at joints, compare turnarounds, and validate the asset in an engine scene.'
    ], ['Editable source mesh plus engine-ready export, units and pivot specification.', 'Turnaround renders, topology view, triangle/vertex counts, LOD/collision inventory.'], [
        'Check scale, bounds, transforms, nonmanifold geometry, winding/normals, and import warnings.', 'Inspect silhouette and shading from multiple angles; verify collision and deformation in the target engine.'
    ], 'Create a reference-matched game prop with two LODs, collision proxy, and verified import at real-world scale.'),
    _track('textures', 'Textures, UVs, and PBR materials', 'content ui verification', [
        'Unwrap UVs with consistent texel density, intentional seams, sufficient padding, and unique or deliberately mirrored islands.',
        'Author base color, normal, roughness, metallic and optional AO maps appropriate to the asset; keep noncolor data linear.',
        'Separate material response from baked lighting in albedo; match reference material, wear, scale, and surface detail.',
        'Use engine-specific normal orientation, channel packing and compression; check mipmaps and texture memory budgets.'
    ], ['UV layout and source texture/material files with provenance.', 'Engine-ready material set with map roles, resolution, color space, compression and previews.'], [
        'Inspect UV overlap/stretch, seam bleeding, roughness/metallic values, and normal orientation.', 'Compare neutral-light and representative scene renders at multiple distances; record memory and import results.'
    ], 'Texture a wood-and-metal prop with consistent texel density and verify materials under two lighting setups.'),
    _track('storytelling', 'Storytelling, narrative design, and dialogue', 'architecture gameplay content ui verification', [
        'Establish premise, theme, protagonist motivation, conflict, stakes, tone, and audience; keep a canon ledger of locked facts.',
        'Build a beat sheet with setup, escalation, reversals, climax and resolution; map each beat to a playable objective or intentional cinematic.',
        'Develop distinct character voices, relationships, believable choices, consequences, and environmental storytelling; avoid redundant exposition.',
        'Write mission flow, dialogue with speaker/context/emotion, branching conditions, pacing and continuity; revise against the actual playable sequence.'
    ], ['Narrative bible and character/relationship arcs.', 'Mission beat sheet, branching dialogue/state conditions, recording-ready lines and environmental story props.'], [
        'Trace chronology, motives, player agency, branching reachability, and continuity across missions.', 'Play through narrative triggers and failure/retry paths; review dialogue aloud and distinguish subjective feedback from tested behavior.'
    ], 'Design a three-beat quest with a character reversal, two player approaches, conditional dialogue and coherent endings.'),
    _track('animation', 'Rigging and animation production', 'content gameplay verification', [
        'Define skeleton naming, rest pose, coordinate basis, skinning, joint limits, attachment sockets, and animation retarget conventions.',
        'Build motion from anticipation, contact, weight transfer and follow-through; maintain consistent root motion policy.',
        'Author movement and action clips with transitions, blend spaces, IK where needed, and event timing aligned with gameplay.',
        'Verify mesh deformation and animation playback in the engine, including interrupted actions and ragdoll or recovery where required.'
    ], ['Rigged editable character and engine-compatible skeleton with socket map.', 'Named animation clips, transition/state chart and retarget tests.'], [
        'Inspect joint deformation, foot sliding, clipping, root travel, hand/socket alignment and loop continuity.', 'Test traversal, action interruption, blending and event synchronization in play.'
    ], 'Rig a simple humanoid and import idle, walk and run clips with validated transitions and joint deformation.'),
    _track('level-design', 'Level and world design', 'architecture gameplay content verification', [
        'Derive movement metrics and gameplay goals; sketch routes, landmarks, spawn/goal placement, encounter pacing and sightlines.',
        'Block out at correct scale and run traversal checks before detail; measure travel times, choke points and intended alternate routes.',
        'Build modular environment kits, lighting/navigation zones, streaming boundaries and collision; keep world logic separate from decoration.',
        'Playtest with the target camera and controls; iterate route clarity, accessibility, encounter fairness and performance.'
    ], ['Scaled top-down map and blockout with annotated paths, elevations and landmarks.', 'Traversal/encounter tests, modular asset list and streaming plan.'], [
        'Check reachability, headroom, collision, navigation, sightlines, and route times.', 'Verify representative in-engine routes, respawn and transitions; record any untested zones.'
    ], 'Block out a small combat arena with two routes, cover, sightline checks, and measurable traversal times.'),
    _track('interface', 'Game interface, controls, and accessibility', 'ui gameplay verification', [
        'Map user tasks and visual hierarchy; define HUD placement, readable text, prompts, menu states, and feedback timing.',
        'Design controls for target devices, remapping, input focus, dead zones, sensitivity and pause behavior.',
        'Use responsive layouts, safe areas, contrast, non-color cues, captioning and consistent navigation.',
        'Test with real game states and representative resolutions, including empty, error, disabled and interrupted transitions.'
    ], ['HUD/menu wireframes and input action map.', 'State-specific screenshots, accessibility checklist and interaction test cases.'], [
        'Check contrast, text scaling, clipped panels, focus order, controller/keyboard interaction and resolution changes.', 'Capture actual engine or browser rendering; mark simulated-only evidence separately.'
    ], 'Create an accessible inventory HUD with keyboard/controller navigation and empty/full/error states.'),
    _track('quality-assurance', 'Quality assurance and playtesting', 'verification architecture gameplay ui content build_operations', [
        'Translate requirements into acceptance criteria, traceable scenarios and negative tests with exact project/spec/build identity.',
        'Separate automated assertion, visual inspection, performance measurement and human playtest evidence; never substitute one for another.',
        'Reproduce defects with steps, expected/actual results, severity, environment, evidence and regression tests.',
        'Compare current quality gates against captured observations; prioritize actual blockers and reverify corrected builds.'
    ], ['Requirements-to-tests matrix and reproducible scenario suite.', 'Defect record, evidence artifact identifiers and current release-readiness report.'], [
        'Confirm tests ran against the intended build and that failed tests can detect the original defect.', 'Record limitations, stale evidence and unresolved issues; never auto-promote a release based on advisory reports.'
    ], 'Build a smoke-test matrix for a playable loop, report a reproducible defect, and demonstrate a meaningful regression test.'),
    _track('build-performance', 'Build operations, performance, and asset provenance', 'build_operations architecture verification content', [
        'Establish target platform, frame-time, memory, package size, and loading budgets; select representative scenes and hardware.',
        'Measure baseline build/runtime telemetry before optimization; isolate bottlenecks and change one measurable cause at a time.',
        'Verify asset license, source, hashes, package admission, dependency versions and reproducible builds; preserve editable sources.',
        'Keep publish/deploy approval separate from local testing; use scoped permissions and never expose credentials.'
    ], ['Build manifest, exact tool versions, asset provenance and dependency inventory.', 'Measured baseline/comparison report, target budgets, build/log artifact IDs.'], [
        'Build and verify the exact target; compare representative frame-time and memory measurements under comparable conditions.', 'Inspect logs and artifact hashes, license terms and package size; distinguish static inspection from device performance evidence.'
    ], 'Measure a fixture build, identify one expensive asset or operation, improve it and compare the same scenario.'),
]


def curriculum():
    body = dict(version=1, tracks=deepcopy(_TRACKS),
                note='Role-specific production playbooks and practice exercises. Apply only to authorized work; '
                     'record actual evidence, not claimed training or model-weight changes.')
    return {**body, 'curriculum_sha256': spec_digest(body)}


def training_instruction(role):
    tracks = [track for track in _TRACKS if role in track['roles']]
    if not tracks:
        raise ValueError('Unknown Studio training role')
    parts = ['Studio curriculum v1 (/api/training). Use the following applicable role playbooks within the '
             'claimed task only; do not broaden scope or run practice exercises unless assigned.']
    for track in tracks:
        parts.append(f"{track['title']}: {' '.join(track['workflow'])} "
                     f"Evidence targets: {' '.join(track['verification'])}")
    parts.append('Return the applicable deliverables and actual verification observations to the lead; '
                 'do not treat training material or planned tests as completion evidence.')
    return ' '.join(parts) + ' '
