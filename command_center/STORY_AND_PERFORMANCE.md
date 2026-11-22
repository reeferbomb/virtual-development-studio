# Graveforge Academy: Story and Performance

The goal is to make a game world feel inhabited, responsive and believable.
Study the underlying production technique, create original work and review it
from the player's perspective. The Lab measures structured practice, not the
quality of finished animation, acting, story or audio. It does not train model
weights. The Player Experience field guide remains applicable.

## 1. Motion design and character performance

- Establish the genre, camera distance, body dimensions, rig, movement speed,
  interaction reach and intended feel. Block poses for silhouette and readable
  intention. Design timing, spacing, anticipation, contact, weight transfer,
  follow-through and recovery. A close-up needs subtler detail than a distant
  character; exaggerated anticipation can help readable combat.
- Build locomotion around idle, starts/stops, walk, run, sprint, turns, strafing,
  crouch and prone where appropriate. Integrate jumps, landings, hits, aiming,
  reloads, interaction, weapon handling and recovery as the genre requires.
  Avoid foot sliding, unwanted teleportation, clipping and abrupt transitions.
- Specify who owns displacement: authored root motion or gameplay-driven
  movement. Use blend spaces, crossfades, contact windows and foot/hand IK
  where suitable. Keep collision and simulation authoritative; tie hit events,
  footsteps and resource changes to a single validated state/marker. Test
  interrupted, canceled, repeated and network-corrected actions.
- Character acting includes posture, gaze, blinks, expression, gesture,
  breathing and listening reactions. Use phoneme-aligned visemes, then adjust
  coarticulation and emotional expression; avoid a mouth-only performance.
  Retarget to compatible skeletons and compare deformation, rest pose, scale,
  attachment sockets and contact points. Use authorized motion capture only.
- Review actual clips at normal speed, slow motion and from the game camera.
  Check response latency, animation continuity, movement and hit timing,
  readability, frame budget and frame-rate variance. Record build, rig, clip and
  capture identity, observed issues and retest. Structural or numeric checks do
  not establish compelling acting or an engine import.

Primary production studies:

| Reference | Technique to study | Original exercise prompt |
| --- | --- | --- |
| [Ubisoft: Motion Matching](https://www.gdcvault.com/play/1023280/) and [For Honor follow-up](https://gdcvault.com/play/1026472/ML-Tutorial-Day-From-Motion) | Pose and movement selection based on motion context | Prototype a guard transition that preserves contact and gameplay timing |
| [Assassin's Creed: Fitting the World](https://gdcvault.com/play/1023316/Fitting-the-World-A-Biomechanical) | Adapting contact to world geometry | Check a walk across different ground heights and steps |
| [Naughty Dog: Motion Matching in The Last of Us Part II](https://media.gdcvault.com/GDC%2B2021/Motion_Matching_In_TLOU2.pdf) | Runtime animation system design | Compare responsive locomotion with and without transition blending |
| [Godot AnimationTree](https://docs.godotengine.org/en/stable/tutorials/animation/animation_tree.html) and [3D skeleton retargeting](https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/retargeting_3d_skeletons.html) | Concrete state, blend and rig integration | Import a legal original rig and verify movement and transitions |

## 2. Environmental storytelling and diegetic narrative

Write a brief describing who occupied the location, what happened, when, why,
what changed afterward and what the player should infer. Separate facts from
optional interpretation. Assign each required fact at least one observable
clue on every feasible route; reinforce safety-critical facts with independent
channels. Map optional secrets and alternate perspectives without forcing the
player to find everything. Allow different discovery orders unless the story
requires a prerequisite. A clue must be physically plausible in its location.

- Tell the story through object placement and absence, damage, wear,
  repaired structures, room use, debris, lighting, graffiti, signage, sound,
  weather, traces of previous routines and changes in architecture. Nothing in
  a space needs to be decorative merely because it looks expensive.
- Layer the broad story (silhouette and landmarks), evidence at gameplay
  distance (object groups, paths and contrasts), and close-up discoveries.
  Visual guidance must be legible without excessive prompts. Do not hide a
  mission-critical clue in an optional audio log. Avoid over-explaining what
  the player just saw; let players make and test deductions.
- Check actual visibility, camera angles, obstruction, lighting, audible
  range and timing. Provide captions/description for critical non-speech
  audio, visual equivalents and non-color cues; test muted and alternate
  discovery routes as well as normal play. Avoid assuming a clue is understood
  just because the character passed near it.
- Ask consented players after an unprompted route what happened, what made
  them think so, which details surprised them and what was unclear. Do not
  confuse agreement with the intended story with enjoyment; compare observed
  behavior, alternate explanations and the previous build.

| Reference | Technique to study | Original exercise prompt |
| --- | --- | --- |
| [Worch and Smith: What Happened Here?](https://www.worch.com/2010/03/11/gdc-2010/) | Players infer past events from the environment | Arrange clues about a fictional abandoned workshop without a narrator |
| [Fullbright: Level Design of Gone Home](https://www.gdcvault.com/play/1022112/Level-Design-in-a-Day) | Explore the relationships between familiar spaces, objects and discovery | Design a new room that reveals a resident's routines and a disruption |
| [Fullbright: Tacoma and Nonlinear Discovery](https://www.gdcvault.com/play/1025178/Level-Design-Workshop-Designing-for) | Nonlinear story discovery | Let two original paths reveal different perspectives on the same event |
| [Bethesda: Skyrim and Fallout level-design workflow](https://www.gdcvault.com/play/1020777/Level-Design-in-a-Day) | Iterative level design and world spaces | Block out a fictional ruin, establish a history and verify the clue routes |

The prompts are Graveforge's own design interpretations and exercises, not
reproductions of the games. Use public developer talks as reference; do not rip
assets, copy layouts, reproduce dialogue, download game voice files or import
unlicensed recordings. Keep reference provenance alongside original work.

## 3. Voice direction and production integration

Define the character's objective, relationships, age range where appropriate,
background, speech register, vocabulary, emotional range and story context.
Cast for performance and intelligibility; direct what the character wants and
what just happened, rather than asking for a famous voice imitation. Distinct
characters should be recognizable through original phrasing and intent.

- Use a recording script with stable line IDs, speaker, preceding/following
  beats, addressee, context, pronunciation guide, delivery intent, priority,
  timing window and variants. Record authorized alternatives for a different
  emotional state, or shorter take for urgent gameplay. Review rhythm, stress,
  pauses, breath, reaction and conversational turn-taking. Reject clipped,
  noisy, distorted, wrong-script or uncleared takes; a valid hold is better
  than forcing a bad take into the build.
- Give dialogue a purpose. NPC barks should communicate useful state and have
  cooldowns, contextual variants and interruption rules. Radio/PA or fictional
  DJ voices need an identifiable source, appropriate phrasing and a mix that
  stays intelligible. Narrative dialogue may need protected story beats or a
  resumable playback position. Avoid repeated long lines during combat.
- Use stable asset identities, localization packs, fallback policy, duration,
  subtitles with correct speaker and timing, captions for non-speech sounds,
  phoneme/viseme cues and explicit clip readiness. Define priority, concurrency,
  ducking, spatial attenuation, pause/resume, cancel, scene reset and streaming
  behavior. Preserve player control and prevent overlapping critical lines.
  A recording is not the same as a synchronized playback artifact.
- Listen in the actual build with music, effects and background ambience at
  representative listening conditions. Check dialogue clarity, loudness and
  peaks, clipping, device variation, spatial source, mouth timing, timing of
  translated lines and caption readability. Do not rely on a metadata-only
  assay for acting authenticity or sound quality.
- Confirm recording and reuse terms, performer consent and the intended
  distribution before recording or synthetic generation. Never clone or
  impersonate an identifiable person's voice without express authorization
  and applicable rights. Distinguish scratch timing audio from approved final
  voice assets; document synthetic generation when used. Store sources and
  production notes privately; never upload voice recordings to the Lab.

Production references: [Anatomy of Great Voice-Over](https://www.gdcvault.com/play/1023353/Anatomy-of-Great-Voice-Over),
[Dynamic Dialogue: the Game Designer](https://gdcvault.com/play/1025109/Dynamic-Dialogue-The-Game-Designer),
[Demystifying VO in Games](https://gdcvault.com/play/1035594/Demystifying-VO-in),
[Xbox accessibility guidance: subtitles and captions](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/104)
and [audio accessibility](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/105).
For performer rights, see [SAG-AFTRA interactive agreement resources](https://www.sagaftra.org/contracts-industry-resources/interactive/2025-interactive-media-video-game-agreement);
actual production contracts and applicable rights require separate review.

## 4. Practice to production

1. Select the new track in Training; state the original creative target and
   the relevant reference technique. Do not copy reference content.
2. When assigned, build a fresh synthetic JSON submission in Lab and assess
   it. Inspect and correct failures; teaching examples are not independent work.
3. For an authorized production, make the original rig, environment or voice
   content in the private workspace. Run target-engine/device checks with the
   exact build; record playback, visual and audible observations separately.
4. Compare actual results with the intended effect. Document unresolved
   issues, evidence limitations, rights checks and proposed improvements.
   Only the lead can record assigned practice or request release approval.

No real recordings, private scripts, actor data, participant data or imported
assets are required for the synthetic exercises. No automatic telemetry,
network transmission or engine execution is introduced by these lessons.
