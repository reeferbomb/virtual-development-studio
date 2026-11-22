# Choosing a HUD and menu style

A survey balloon is drifting toward a ridge. The operator needs to see the horizon, read the lift charge and notice when a vent needs attention. A dispatcher also needs the route and the survey queue. The same flight can support a wrist instrument and a chart table because the two views serve different decisions.

## What the sources establish

- Dino Ignacio, lead UI designer on *Dead Space*, describes how the team developed an interface that belongs to its fictional world. Study how an object can carry information while its user stays in the scene. Use original objects, layouts and markings for the new game. [GDC session](https://gdcvault.com/play/1018819/Crafting-Destruction-The-Evolution-of)
- PlayStation documents HUD toggle shortcuts, configurable text and icon sizes, and a high-contrast HUD in *God of War Ragnarök*. World’s Edge documents contrast controls and size changes for some menu and HUD text in *Age of Empires IV*. These examples give a designer separate controls to consider for persistent information, scale and backing. [PlayStation](https://www.playstation.com/en-us/games/god-of-war-ragnarok/accessibility/) · [World’s Edge](https://www.ageofempires.com/age-iv-accessibility/)
- Microsoft recommends aligning navigation with a component’s meaning or visual position, and making the outcome of an action clear before activation. If a vertical style picker becomes a horizontal strip, its directional controls should follow the new arrangement. A preview should tell the player whether the change has been applied. [Xbox UI navigation](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/112) · [Xbox UI context](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/114)

## Original design studies

| Style | Composition and menu treatment | Review question |
| --- | --- | --- |
| Minimal | Preserve the horizon. Keep one lift reading at rest, reveal the bearing on request and interrupt for an urgent vent warning. Provide an always-visible option. | Can a new player recall status and recover a missed warning? |
| Immersive or diegetic | Put a numbered gauge on the pilot’s glove. Pair a needle entering a marked region with a word and shape. Offer a screen-space reading when the glove is hidden. | What happens on a sharply angled, dark or occluded instrument? Can the player obtain an audible equivalent? |
| Tactical | Keep energy, near-term risks and the next action in a stable strip. Replace a low-priority notice during an alert, then restore it after acknowledgement. | Can the operator find the urgent item while the whole display is busy? |
| RPG | Give the equipped and proposed instruments aligned rows, units and signed differences. Open item history as a detail screen. Canceling a comparison restores focus to the originating item. | Can the player distinguish a previewed upgrade from an equipped one? |
| Strategy | Bind costs and the work queue to the selected station. Group current state, pending change and command result. Use a row or grid whose focus order follows its geometry. | After changing selection, do all displayed costs and available commands belong to the new station? |
| Retro | Use an integral pixel grid, sturdy letterforms and a cursor shape that differs from a disabled mark. Provide enlarged text and a way to remove flicker, scanlines and decorative motion. | Are similar glyphs distinguishable at output size? Can the player still identify focus with the screen in grayscale? |
| Modern | Group one decision per card and use whitespace to expose relationships. Show state words such as **Preview** and **Applied**. Keep confirmation and cancellation responsive throughout any visual transition. | Does a change in animation speed or a long translated label obscure the next action? |

## Put two styles through one decision

1. Draw both styles first in grayscale. Label what is urgent, what the player must compare and what can be recalled later. The compact study should visibly free play space. The tactical study should place related information where it can be compared.
2. Capture rest, warning, occluded instrument, open picker, preview, cancel and apply. Read each state without hue. Check the text, focus ring and its surrounding background, including moving gameplay beneath translucent panels. Offer another sensory channel where a visual cue alone would exclude a player. [Xbox contrast guidance](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/102) · [Xbox additional channels](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/103)
3. On a controller, open the style picker, navigate, preview, cancel while moving, apply, then reopen. The original choice should survive cancel. The applied choice should regain focus on reopening. Repeat with reduced motion and distinguish focused, previewed and committed states in wording or shape. [Xbox UI context](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/114)
4. Inspect the rendered result on a handheld at 1280×720 and at the target device’s native resolution, with enlarged text and a long translation. Check real button prompts, reading distance and controls throughout the menu. Valve lists 1280×800 as preferred for Steam Deck and also recommends 1280×720. [Steamworks compatibility guidance](https://partner.steamgames.com/doc/steamhardware/compat?l=english)

The `interface-styles` Lab uses declared rectangles in one 1280×720 viewport, synthetic single-line labels, opaque swatches and timed digital inputs. It checks the structural distinction between the dial and chart, visibility of a fallback warning, focus order and the cancel/apply state trace. A rendered device pass supplies the evidence for glare, text shaping, camera occlusion, comfort and actual input latency.
