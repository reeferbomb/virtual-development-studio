# HUD and menu design at handheld scale

Start with the decision the player makes while looking at the world. In the signal-station exercise, the operator needs to know whether the relay works, which gantry to reach and when pressure requires immediate attention. Tracking all three while standing at a console can obscure the prompt that opens it.

## Three reference studies

| Published example | What the developer documents | Transfer to an original design |
| --- | --- | --- |
| Halo Infinite, first-person HUD | Separate controls for reticle outline, objective markers, event-feed backing and HUD opacity, alongside notification duration. [Halo Support](https://support.halowaypoint.com/hc/en-us/articles/4408122295444-Accessibility-Features-in-Halo-Infinite) | Keep the center of the first-person view clear. Give the player independent control over transient notices and essential state cues. Check both against a bright moving background. |
| Age of Empires IV, real-time strategy | The developer describes strong contrast, key remapping and scaling for some HUD and menu text. Its documented narration coverage includes the main menu and excludes the in-game HUD. [World’s Edge](https://www.ageofempires.com/age-iv-accessibility/) | Group selected units, available commands, queue position and cost so a player can predict an order’s outcome. Try a large selection at the biggest type setting. Record exactly which elements can be heard or operated. |
| God of War Ragnarök, action interface with RPG equipment | PlayStation documents separate controls for UI text, icons and caption size, a high-contrast HUD backing and presets that change several settings together. [PlayStation](https://www.playstation.com/en-us/games/god-of-war-ragnarok/accessibility/) | In an equipment comparison, preserve the current item, candidate item, signed change and confirm action. Test enlargement with a long item name. Let players adjust settings independently after selecting a preset. |

## Decide what stays visible

| Situation in the signal station | First question to answer | HUD behavior |
| --- | --- | --- |
| Walking to the gantry | Where should I go? | Keep relay status and destination in stable locations. |
| Using the station console | What can I do here? | Show the current input binding and remove the prompt on leaving its range. |
| Pressure alarm | What changed and how urgent is it? | Keep the warning and status visible even in compact mode. Pair the warning with a distinctive shape and words. Provide an equivalent audible signal where supported. |
| Pause to change settings | Where is focus? What will this input change? | Place focus on a visible control. Keep directional movement inside the current menu. On closing display settings, return to the control that opened it. |

Give the same action a stable name across help, settings and prompts. Update its displayed key or glyph immediately after a remap or a switch between controller and keyboard. Use distinct feedback for applied, blocked and pending operations. A blocked action should explain its cause and what the player can do next. [Xbox input guidance](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/107) · [Xbox navigation guidance](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/112)

Separate color from meaning. A labeled lock and a check mark can distinguish a blocked result from success in grayscale. Both are visual, so offer speech or another appropriate sensory channel when the result is needed without sight. Inspect the indicator against the inside and outside edges of its focus background. [Xbox additional channels](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/103) · [Xbox contrast guidance](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/102)

## Run the handheld pass

1. Use a 1280×720 viewport, then repeat at the device’s native aspect ratio. Start with the controller alone. Reach settings, change text size, close the nested panel and resume. Switch input device mid-menu and verify the active prompt. Valve identifies 1280×800 as preferred and also recommends 1280×720. Its guidance specifies physical viewing distance and distinguishes rendered character height from a font setting. [Valve’s compatibility checklist](https://partner.steamgames.com/doc/steamhardware/compat?l=english)
2. Compare default and enlarged UI. Check safe edges, subtitle clearance, translated strings, long numbers, focus outlines and the world area left visible. Inspect rendered glyphs over representative backgrounds as well as opaque panel swatches. [Xbox text display guidance](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/101) · [Xbox contrast guidance](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/102)
3. Attempt a blocked action. Correct it and apply the change. Reopen settings after a restart, return from a nested dialog and repeat with a remapped confirm button. Record the input sequence, before/after settings, device, language and observed focus. [Xbox input guidance](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/107) · [Xbox navigation guidance](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/112)

## What the exercise measures

The `hud-excellence` exercise enumerates simultaneous widget rectangles at three profiles, calculates ratios for declared opaque colors, checks two remapped input maps and replays their physical button sequences. It uses a synthetic monospace advance, a 4% safe margin, a 14px base glyph floor and an enlarged setting of 150%. Those are exercise parameters. Actual text shaping, controller hardware, transparent backgrounds, narration, persistence and readability at viewing distance require a separate test in the build.
