# Visual effects that communicate a state change

A player at a flooded greenhouse needs to know which gate will open, when it has opened, and whether water is still crossing the path. Give each question its own visible answer. In this original design, a toothed rim identifies the moving gate, a latch-shaped mark confirms contact, and a low fan of droplets shows flow direction. Riot's VFX lesson describes the competing demands of spectacle, identity and clarity. The greenhouse designs below are our application of that principle. [Riot Games, Visual Effects](https://www.riotgames.com/en/artedu/visual-effects)

## Build from the action outward

| Effect | First read | Supporting layer | Test at game-camera distance |
| --- | --- | --- | --- |
| Impact | Place a brief, asymmetrical notch at the contact point. Align its wide side with the surface. | Send a few droplets away from the contact normal and leave a wet mark. | Can a viewer identify the struck surface and contact frame with the droplets disabled? |
| Magic | Trace a broken arc around the intended growth area before a seed opens. Close the arc on activation. | Let thin tendrils travel inward, followed by slow drifting seeds. | Does the outline still identify the active plot on low quality and over light soil? |
| Destruction | Make the broken silhouette persist after a pane gives way. | Drop a few readable shards, then fade fine dust. | Do moving fragments conceal the now-passable opening? Does its physical state agree with the image? |
| Ambient and weather | Use drifting pollen to indicate a sheltered space and slanted rain outside it. | Add sparse ground splashes near the player and a drier band under the eaves. | Cross the threshold, rotate the camera, then teleport. Look for rain indoors or a conspicuous emitter boundary. |
| Decal | Leave a shaped latch mark aligned with the receiving surface. | Fade a wider wet patch over a longer interval. | Check walls, thin geometry, moving props and the low-end renderer for projection on unintended receivers. |

Use anticipation to tell the player where to look. Synchronize the contact shape with the simulation's confirmed event, including interrupted or canceled actions. Let a lingering state cue last as long as the state is relevant. Review a frame before contact, the contact, the first readable aftermath and a second event over the fading first one. Godot's Decal projects onto meshes inside a volume, so receiver setup and volume placement both matter. [Godot 4.3, Decal](https://docs.godotengine.org/en/4.3/classes/class_decal.html)

## Spend quality where the silhouette needs it

Keep the shape and onset of the warning at both quality levels. On the richer preset, add foam at the outside edge where it can help communicate direction. Epic's Niagara guidance distinguishes reducing the number of live systems from scaling emitters, particles and renderers. It also explains that pooling reduces repeated allocation while reactivation still costs time. Profile transparent screen coverage, draw and simulation time, and peak instance demand on each intended device. A big, nearly transparent card can cover much more of the screen than a tight cluster of particles. [Epic Games, Scalability and Best Practices for Niagara](https://dev.epicgames.com/documentation/en-us/unreal-engine/scalability-and-best-practices-for-niagara)

Godot 4.3 documents that lowering a GPU emitter's emission ratio leaves its configured particle capacity allocated and processed. Choose a suitable capacity for the lower preset and measure it. At teardown, stop new births, let the tail end or explicitly clear it, release the instance, and reset its local transform and material parameters. Trigger the next use at a different location to expose a stale trail. Test scene unload and cancel-during-warning as separate runtime cases. [Godot 4.3, GPUParticles3D](https://docs.godotengine.org/en/4.3/classes/class_gpuparticles3d.html)

## Keep information available with motion reduced

Use a still outline and confirmation glyph at the same place and time when a player disables shake or fast movement. Preserve state through shape as well as color. Inspect the final picture with weather, post-processing, HUD and simultaneous impacts active. Even individually calm layers can combine into a repeating high-contrast pattern. Review the actual output with a flash-analysis process, including transitions and overlapping bursts. Microsoft's XAG 117 covers visual movement controls and XAG 118 addresses photosensitivity testing. The exercise's still/off labels describe authored intent and cannot certify the composite image. [Xbox Accessibility Guideline 117](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/117) · [Xbox Accessibility Guideline 118](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/118)

## Worked overlap test

Contact frames are 8, 14 and 20. For the first contact, the rim occupies frames 5–7 and the confirmation occupies frames 8–9. The main spray emits on frames 8 and 9. With a five-frame particle lifetime, its last cohort is still visible on frame 13 and its pool slot can be reused on frame 14. High-quality foam begins on frame 9 and needs a second slot when the next contact's foam starts on frame 15. Frame 15 still contains the last cohort from the first foam burst.

| Setting | Peak live particles | Peak checked-out instances |
| --- | ---: | ---: |
| Low, standard | 2 | 2 |
| High, standard | 18 | 4 |
| Low, reduced | 0 | 1 |
| High, reduced | 0 | 1 |

The exercise verifies every cue frame, resource tail and slot boundary in this declared sequence. Its cover layer is a binary model of the shared focus area. Use captures of the actual game to evaluate translucent overdraw, silhouettes, perceived timing, performance and the effect of camera movement.
