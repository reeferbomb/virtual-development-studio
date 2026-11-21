# Third Door

Mara and Ivo are looking for his old home on the Nightfall Patrol street. The house numbers are gone. Ivo remembers the door because he still carries its key.

[The edit](nightfall_plan.json) runs 312 frames at 24 fps (13 seconds). Frame ranges include the first frame and exclude the last. [The staging](nightfall_bindings.json) uses Godot world coordinates in metres and angles in degrees. Mara holds the left mark, Ivo the right. The cameras stay on the same side of their eyeline. Both actors use the same mesh, so their screen positions and the order of the cuts identify them.

## Shot directions

| Frames | Camera | Direction |
| --- | --- | --- |
| 0–72 | `street_pair` | Open on both figures. Mara is crouching and speaks first. Give the audience half a second to place her before the caption arrives. |
| 72–166 | `ivo_single` | Cut to Ivo before he answers. Hold past “key” to give Mara time to catch the implication. Mara changes to her standing idle pose off camera. |
| 166–228 | `mara_single` | Give Mara the whole frame for the question. Leave room on screen right in the direction of Ivo. |
| 228–276 | `ivo_single` | Return to the same framing for the answer. Keep the key off screen. |
| 276–312 | `street_pair` | Return to the opening composition, now with both figures standing. Leave the last 36 frames clear of captions before returning control. |

## Caption sheet

| Frames | Cue ID | Speaker | Text |
| --- | --- | --- | --- |
| 12–64 | `painted_numbers` | Mara | They painted over the numbers. |
| 78–152 | `third_door` | Ivo | Third door. You had to lift it to turn the key. |
| 173–210 | `kept_key` | Mara | You still have it? |
| 233–268 | `every_move` | Ivo | Three cities. Same key. |

The performers stay on their marks. The player samples the imported `Crouch` and `Idle` animations locally on each actor. All four lines are conveyed by captions. The procedural footstep loops for the duration of each caption as a scratch timing cue and stops when that cue ends.

## Gameplay handoff

The event `enter_nightfall_street` starts the edit when the story state is `home_unlocated`. Completion and skip both set `third_door_found`. Interruption returns to `home_unlocated` for a fresh attempt. Each exit returns the camera and input to gameplay, stops the scratch audio and clears the caption.

Run the seven editorial checks from the repository root.

```sh
python3 -m command_center.training_lab_cli assess cutscenes cinematic/production/examples/nightfall_plan.json
```

The checks cover declared timing, continuity, bindings, subtitle synchronization and handoff. Review the framing, performances, caption legibility and playback levels in a rendered run.

## Asset credits

The stage reuses the Nightfall Patrol `city.glb`, two instances of `animated_actor.glb`, and `footstep.wav`. All three are original procedural assets credited to the Virtual Development Studio contributors under the repository’s MIT license. Their file hashes and attribution are recorded in the [source manifest](../../demo/nightfall_patrol/assets/provenance.json). Retain the [copyright and permission notices](../../../LICENSE) with copies of the assets.
