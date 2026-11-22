# Sound effects and adaptive music

In a ferry hall, a heel lands on timber, a radio plays from the ticket counter, and a bell warns that the platform is moving. Mute the sound. Can a player still identify the warning? Turn sound on and walk away from the counter. Does the radio stay in the room while the score follows the player? These two checks reveal different design problems.

## Build the effects around actions

| Sound | Authoring decision | Playback question |
| --- | --- | --- |
| Footstep and foley | Synchronize the sole contact to the movement marker. Pick the bank using footwear and the material actually under the planted foot. Record or synthesize distinct heel, scrape and weight-shift takes. Keep isolated tails for cutting. | Does the first step after crossing onto tile use tile? Does repeated walking sound repetitive? Does stopping silence new steps while the last tail decays naturally? |
| Fictional firearm or energy-tool effect | Build a short attack, a body and an environment-dependent tail from original synthesis or cleared library elements. In an original toy blaster prototype, a wooden snap, a synthesized buzz and a short room reflection can give the action a distinct identity. Audition rapid repeats at a comfortable level. | Do the input and the sound onset agree? Is a quiet confirmation distinguishable from the world effect? Do repeated tails obscure the next cue? |
| Ambience | Give the location a stable bed, then place intermittent details at identifiable sources. Check the loop seam and changes of enclosure. | Can the player tell that a pump stopped or that a door changed the room tone, even when the score is busy? |
| Feedback | Reserve a timbre, a playback priority and a visual equivalent for time-critical signals. Give refusal, success and a continuing condition distinguishable treatments. | Can the player act on the warning with ambient effects muted, in mono, and with audio disabled? |

Audiokinetic’s Project Adventure examples select footsteps from character, step and surface switches. Epic documents how voice limits and resolution rules determine which instances survive a concurrency contest. These are implementation references. The ferry sounds, two-slot limit and priority order in the Lab are original teaching decisions. [Audiokinetic Project Adventure, Footsteps](https://www.audiokinetic.com/download/documents/WwiseProjectAdventure_en.pdf) · [Epic Sound Concurrency Reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/sound-concurrency-reference-guide)

For production, log the creator, original take or licensed pack and cue ID, permission scope and attribution terms for each recording, composition and derivative stem. Keep source masters apart from edited clips. A third party owning a song and a third party owning its recording may be different parties. If a source lacks a usable grant, commission an original or use a cleared replacement. The Lab uses symbolic IDs, integer levels and note numbers only.

## Give the score a musical job

Write an original motif short enough to recognize when its instrumentation changes. Export synchronized stems with matching start, duration and loop endpoints. Try a quiet exploration pass with motif and room tone. On a state change, introduce a separate rhythmic stem at the next musical boundary. Keeping the motif's playhead moving preserves its phrase. An authored bridge into a different section is another option when the new state needs a new tempo or cadence. Test requests on a boundary, just after it, and while a previous request is waiting. Audiokinetic’s music-switch example documents authored source/destination transitions and musical synchronization. [Audiokinetic Project Adventure, Interactive Music Transitions](https://www.audiokinetic.com/download/documents/WwiseProjectAdventure_en.pdf)

A radio belongs to a place in the world. Give it an emitter, a plausible listening range and an independent level or mute. The dramatic score can continue across rooms. In a two-pass test, mute only the radio and verify that the score reaches the same motif note and changes state on the same boundary. An in-world DJ, tuning transition or advertisement also needs a cleared recording or an original production.

## Mix the busiest moment

Start from the player's most important information and balance outward. Route effects, ambience, radio, score and speech to controllable buses. Audition quiet material as well as dense combinations. Limit redundant tails before raising the critical signal. Use short, deliberate gain moves if a priority cue needs space, and audition both the reduction and the recovery. Check the master output and individual buses. Godot documents bus routing, decibel scale and the 0 dB digital clipping boundary. [Godot audio buses](https://docs.godotengine.org/en/stable/tutorials/audio/audio_buses.html)

The exercise adds conservative, nonnegative peak bounds in linear units. Eighty of one hundred units is a fixture target with reserve. A recorded waveform has phase, spectrum, dynamics and duration. Evaluate a rendered mix for true peak, loudness, masking, distortion and fatigue on its intended device. Add captions or visible cues for essential non-speech events, and check readable delivery with sound muted. Give players meaningful independent volume adjustments. [Xbox Accessibility Guideline 104](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/104) · [Xbox Accessibility Guideline 105](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/105)

## Review a playable build

Capture the same route three times with its build ID and audio settings. Use a full mix, a radio-muted mix and a mix with important information communicated visually. Compare the first material change, the warning under load and the transition back to exploration. Listen to the recorded onsets and tails on target speakers and headphones. A matching Lab trace establishes the scheduling and numeric bound of the submitted model.
