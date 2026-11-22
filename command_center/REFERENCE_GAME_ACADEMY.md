# Graveforge Academy — reference games and interface excellence

The purpose of a reference study is to understand why a particular design might
work for a particular player, not to reproduce a commercial game. Study a
legitimate copy or publisher/developer documentation, identify a transferable
mechanic, develop an original prototype and test whether that mechanic serves
the new game's player fantasy. Never infer unseen implementation details from
a screenshot or store copyrighted game assets, scripts, voices or maps in this
repository. A reference title is not a quality guarantee or a universal design
standard. The Academy is an instruction and structured-practice system, not
model-weight training or a substitute for human playtesting.

## Reference syllabus

The title-specific studies below distinguish publicly documented features from
Graveforge's design interpretations and original implementation exercises.

| Game or series | Design study and transferable question |
| --- | --- |
| Mass Effect | Character-driven RPG, choices, squad identity: how does a player's decision affect their relationships and future objectives? |
| Mass Effect 2 | Team recruitment, loyalty and mission preparation: can consequences be anticipated without spoiling their outcome? |
| Mass Effect 3 | Persistent narrative continuity and action-oriented squad combat: can a long-running choice be expressed in both gameplay and narrative? |
| The Darkness (2007) | Supernatural power, light and atmosphere: how can an environment affect capabilities and reinforce a character's fantasy? |
| Legacy of Kain: Soul Reaver | Dual-world exploration: can the same space offer meaningful routes and recognizable landmarks under different world states? |
| Call of Duty (especially Modern Warfare 2, 2009) | Weapon feedback, movement, objectives, match flow, progression: can players rapidly read and respond to threats without unfair surprise? |
| Battlefield (especially Bad Company 2 and Vietnam) | Combined arms, class cooperation, destructive cover and large-scale objectives: how does a changed battlefield create new team decisions? |
| Naughty Bear | Systemic NPC reactions and alternate approaches: can an authored situation generate varied consequences rather than a single scripted result? |
| Grand Theft Auto | Sandbox autonomy, world rules, driving, urban landmarks and reactive escalation: can the player understand how actions change the surrounding world? |
| Shenmue | Daily schedules, lived-in locations, social interactions and discovery: how can an ordinary routine be interesting and navigable? |
| The Legend of Zelda: Majora's Mask | Time-loop structure and scheduled events: what changes on reset and what persistent knowledge or progression rewards exploration? |
| Super Mario | Readable platforming, jump feel, teaching through level geometry and escalating challenges: can the player learn a rule through safe experimentation? |
| Sonic the Hedgehog | Speed, momentum, alternate paths and recoverable route mistakes: can mastery yield a faster route without making the beginner route impossible? |
| The Legend of Zelda: Ocarina of Time | Item-gated exploration, targeting, spatial puzzles and revisitation: can players understand and use a new capability to open a meaningful path? |
| From Dust | Terrain and element manipulation, dynamic hazards and protection: will the simulation produce coherent, legible consequences from player intervention? |
| Civilization Revolution | Condensed turn-based strategy, competing win conditions, expansion and investment: do tradeoffs encourage distinct viable strategies rather than a dominant rote path? |

### Detailed production studies

- [Narrative continuity, powers and dual worlds](reference_studies/NARRATIVE.md)
- [Combat, combined arms and systemic action](reference_studies/COMBAT.md)
- [Living worlds, schedules and resets](reference_studies/WORLDS.md)
- [Traversal, momentum and puzzle progression](reference_studies/TRAVERSAL.md)
- [Terrain simulation and strategic choice](reference_studies/STRATEGY.md)
- [HUD and UI excellence](reference_studies/HUD_UI.md)

## Applying a reference to a new game

1. State the target fantasy, audience, genre, session length, controls, camera,
   minimum hardware and intended emotional effect. Define the mechanic's purpose.
2. Document the specific game, version/platform, publicly available reference,
   observed interaction and design hypothesis. Separate what a source confirms
   from what the team infers. Never claim a developer's proprietary algorithm.
3. Translate the concept to an original setting and interface. Keep the
   mechanic simple enough to isolate and evaluate. Establish a baseline,
   measurable rules, inputs, state transitions, timing and feedback.
4. Build a playable slice only when assigned. Test normal use, failure and
   recovery, cancellation, save/load, accessibility and the relevant input
   devices. Evaluate choices, boredom, confusion, challenge and voluntary replay
   using consented observations rather than invented scores. Preserve the
   baseline and compare competing explanations.
5. Record evidence against the precise build; distinguish simulated rule checks,
   engine measurements, visual inspection and human observations. Keep private
   playtest and project evidence outside this public source checkout. Review
   actual game assets and usage rights before distribution.

## HUD and interface acceptance standard

Design the interface around the player's next decision. Separate persistent
critical signals, contextual information, optional detail and decorative
elements. A HUD need not show everything at once. Keep the center clear of
noncritical overlays during aiming and traversal; show priorities at the
appropriate moment, then retire resolved notifications. Do not hide necessary
information under a decorative animation or behind a color-only cue.

| Surface | Acceptance questions |
| --- | --- |
| Gameplay HUD | Can the player see health, resource/ammo, current objective and urgent threats at a glance? Does the display match actual gameplay state? |
| Contextual interaction | Is the available action, required resource and input clear? Do hold, cancel, unavailable and completed states give feedback? |
| Inventory / map / strategy | Are sorting, selection, comparison, costs, consequences and next actions readable? Are locked actions explained? |
| Dialogue / narrative | Are choices distinct, speakers labeled, subtitles legible and timing synchronized? |
| Pause / settings | Are control remaps, input glyphs, scale, opacity, audio, accessibility and confirmation behavior predictable? |
| Death / restart / save | Are valid recovery choices available? Can the player checkpoint, restart or return to menu without returning to an unwinnable state or losing progress unexpectedly? |

Test a 1280×720 handheld/gamepad view as well as desktop and supported larger
displays. Use target-device viewing distance, text-scale options, safe areas,
localized strings and visually distinct state/focus cues. Check geometry at
multiple scales rather than assuming scaled text fits. Verify non-color signals,
caption visibility, sufficient contrast against changing scenes, and reduced
motion options. Ensure controller focus has an initial target, a clear selected
indicator, logical navigation, back/cancel, and restore focus after closing an
overlay. Support keyboard/mouse and controller prompts without trapping input.
Use measured thresholds as initial acceptance gates, not universal guarantees;
test real rendered frames and gameplay where permitted. The original numeric
Lab exercise provides a bounded simulation only.

The six new Lab exercises supplement all existing production tracks. They are
not an instruction to add every mechanic to every game. A studio specialist
should choose only relevant references and preserve the authorized project scope.
