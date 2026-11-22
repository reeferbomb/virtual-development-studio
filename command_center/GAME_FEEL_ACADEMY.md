# Graveforge Academy — game feel and presentation

Good presentation supports the player's decisions, emotional experience and
understanding of the world. Select a coherent art, sound and interface language
for the original game; measure it against gameplay and the target hardware.
This is a set of instructions and original structured exercises, not model
weight training or proof that a game is fun, attractive or safe.

## Playstyles and Fallout reference study

Study Fallout 3, Fallout: New Vegas and Fallout 4 separately. Bethesda's
[series timeline](https://bethesda.net/en-EU/news/fallout25-presents-the-fallout-timeline)
describes their distinct settings and the introduction of V.A.T.S. in Fallout 3.
The publisher's [Fallout 3](https://fallout.bethesda.net/en/games/fallout-3),
[New Vegas](https://fallout.bethesda.net/en-US/games/fallout-new-vegas) and
[Fallout 4 character system](https://bethesda.net/en-US/news/fallout-4%27s-character-system)
pages are useful starting points. Study New Vegas's factions, reputation,
dialogue and competing outcomes, and Fallout 4's perk ranks, exploration,
customization and workshop systems. Distinguish original releases and DLC.
Do not copy quests, locations, faction names, art, dialogue, music or trademarked
interface designs. See [Fallout and playstyles](presentation_studies/FALLOUT_PLAYSTYLES.md)
for title-specific sources and original exercises.

| Playstyle | What to design and verify |
| --- | --- |
| Direct action / aggressive | Responsive controls, clear hit confirmation, fair risk, ammunition and recovery. |
| Tactical / defensive | Information, positioning, cover, resource pressure, squad or tool coordination. |
| Stealth | Readable visibility and sound, consistent enemy knowledge, escape and recovery after detection. |
| Social / diplomacy | Contextual options, meaningful consequences, relationship state, noncombat success. |
| Explorer / collector | Landmarks, clues, optional rewards, discovery at different skill levels, safe backtracking. |
| Builder / crafter | Legible costs, planning, construction feedback, resource sinks, repair and undo where suitable. |
| Survival / horror | Scarcity, readable danger, atmosphere and credible recovery without arbitrary grind. |
| Hybrid / challenge | Different approaches can coexist; prevent one mandatory build or a hidden failure state. |

Define the player fantasy, abilities, resources, constraints and intended
experience. Give alternatives genuine costs and consequences, not identical
routes with different labels. Compare reachability, completion time, risk,
resource use and outcome for each intended build. Test a novice, an expert and
a mixed approach using actual consented playtest observations when authorized.
Failure and retry should teach rather than silently punish. Not every game
needs every playstyle; prioritize those that fit the design.

## HUD and menu style library

The visual style is not the information hierarchy. Critical information must
remain findable regardless of theme, opacity, resolution, accessibility or
active input device. Design a persistent, contextual and optional layer;
protect gameplay sightlines and dialogue subtitles. Support reduced HUD and
full-information profiles where appropriate.

| Style | Appropriate use and risk |
| --- | --- |
| Minimal / contextual | Exploration or cinematic action; reveal essential state when needed, never hide imminent danger. |
| Diegetic / immersive | In-world instruments, watches, terminals and signs; provide readable accessible alternatives. |
| Tactical / military | Clear status, ammo, team and objectives; avoid competing alerts or obstructed aiming. |
| RPG / retro terminal | Inventory, statistics, dialogue, map and equipment; preserve reflow and font legibility. |
| Strategy / management | Resources, queues, selection and consequences; group related information and limit overlays. |
| Arcade / expressive | Rapid scoring and action feedback; keep decorative motion away from essential cues. |
| Modern / cinematic | Restrained typography, spatial hierarchy, coherent transitions; avoid slow animations that block input. |

Menu alternatives include static illustrated title screens, original animated
world views, diegetic interfaces, list navigation, tabs, radial selection,
cards, and pause overlays. Choose based on task frequency and input. Test
focus, back/cancel, confirm, error, disabled states, modal ownership, focus
restoration, text scaling, localization and controller prompts. Review at
1280×720 on handheld and representative desktop displays. Assess actual
composition, spacing, type, contrast and readability at gameplay speed.
Do not make interaction depend on animation finishing or color alone.
See [interface styles](presentation_studies/INTERFACE_STYLES.md) and the
existing [HUD guide](reference_studies/HUD_UI.md).

## Startup, menus and recovery

Design a startup state machine, not a sequence of uninterruptible videos.
Consider engine startup and initial settings, required legal/platform notices,
optional branding and cinematics, background resource loading, title and
main menu, saved game validation, new/load/continue, transition to gameplay,
and failure/retry. Which screens are required depends on actual platform and
licensing requirements; confirm them before release. Make first-run
accessibility options available before optional audiovisual content, respect
reduced motion/audio preferences, provide skip/pause where allowed, and
persist settings. Avoid unnecessary logos on subsequent launches. Never
enable Continue for an incompatible or terminal save; keep valid recovery
options available. Test cold/warm launch, interrupted loading, corrupt save,
death/checkpoint, controller disconnect and resume. Measure time to first
responsive input and time to playable state separately. See
[startup sequences](presentation_studies/STARTUP_SEQUENCES.md).

## Art direction and visual identity

| Art direction | Priorities |
| --- | --- |
| Photorealistic | Accurate forms and scale, physically consistent material response, lighting and texture; strong optimization. |
| Semi-realistic | Believable proportions and materials with deliberate simplification; consistent detail, palette and silhouette. |
| Stylized / painterly | Shape language, deliberate exaggeration, controlled color and texture marks; preserve readable forms. |
| Cel-shaded / illustration | Stable shading bands, line weight and silhouette, limited clutter; inspect motion and distant objects. |
| Low-poly / retro 3D | Intentional geometry, disciplined pixel density, silhouettes, fog and texture scale; avoid accidental inconsistency. |
| Pixel / 2D | Consistent pixel grid, palette, animation timing, readable layers and camera scaling. |
| Industrial / horror | Purposeful wear, material history, dark/light contrast and environmental storytelling; never obscure critical signals. |

Create a style bible with original examples, reference provenance, mood and
color roles, material ranges, lighting, proportion guide, silhouette and
camera rules, asset fidelity tiers, LODs and texture budgets. Evaluate the
hero object, environment, character and UI together in representative scenes.
Keep attention on gameplay-critical forms, use detail where it supports
function, and judge quality on the intended device. See
[art and visual styles](presentation_studies/ART_STYLES.md).

## Sound effects, music and visual effects

Sound design communicates cause, surface, distance, urgency and emotion.
Create original or licensed one-shots, Foley (footsteps, handling and cloth),
impacts, environment beds, machinery, interface feedback and spatial sources.
Use small variations to avoid obvious repetition, distinct critical cues,
material-sensitive playback, distance and occlusion, and bounded concurrency.
Mix dialogue, effects, music, ambience, UI and radio separately; protect
intelligibility, avoid clipping, and respect player volume controls. Review
the real mix on headphones and speakers. Provide captions or visual
alternatives for essential non-speech cues. Use only authorized performances.

Music should serve pacing and identity: establish original themes, ambient
space, tension, exploration, combat and resolution; use loop points,
phrase/bar-aligned transitions, stingers and intensity layers as appropriate.
Maintain silence as a deliberate choice. Separate in-world radio from
non-diegetic score; do not use copyrighted music without suitable rights.
See [sound and music](presentation_studies/SOUND_MUSIC.md).

VFX should communicate anticipation, impact, persistent state and recovery.
Use particles, trails, decals, lighting, distortion, weather, debris, magic
and destruction only where they serve a purpose. Synchronize to authoritative
gameplay events; balance timing, layers, scale, color and opacity. Reserve
visual attention for danger and meaningful interactions. Provide lower-motion
and lower-intensity alternatives and test actual frames for photosensitivity
hazards; a numerical exercise alone cannot certify safety. Pool and bound
effects, clean up on interruption and scene change, and measure frame time
and overdraw rather than assuming a particle count guarantees performance.
See [VFX design](presentation_studies/VFX_DESIGN.md).

## Production acceptance

Use the [Xbox Accessibility Guidelines](https://learn.microsoft.com/en-us/xbox/accessibility/guidelines)
as one public reference alongside the actual target-platform requirements.
For every authorized production, record the exact build, control scheme,
display/audio device, settings, intended experience, measured observations,
unresolved issues and retest plan. Keep private game content, player data,
recordings and practice evidence outside the public checkout. The Lab checks
synthetic data only; inspect actual rendering, playback, sound and player
comprehension separately. All earlier Academy tracks still apply.
