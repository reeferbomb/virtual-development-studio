# Game startup and return to play

## Make the opening usable

Keep the engine splash small and predictable. Godot supports a boot image, background color, and a minimum splash duration. Set these deliberately and measure the time until the first responsive game screen. Treat an optional animated studio logo as a separate scene with a visible skip action. [Godot ProjectSettings](https://docs.godotengine.org/en/stable/classes/class_projectsettings.html#class-projectsettings-property-application-boot-splash-minimum-display-time)

Make the first interactive screen reachable with keyboard and controller. Let players set narration, captions, volume, text size, and motion before optional video or gameplay. Start with readable text and visible focus, supply a way back to settings, and apply a saved profile before showing the opening on later launches. Microsoft’s startup accessibility metadata describes a first-screen setup and reuse of saved preferences as a supported pattern. [Xbox accessibility metadata](https://learn.microsoft.com/en-us/gaming/game-publishing/concepts/metadata-accessibility) · [Xbox UI navigation guideline](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/112)

Record the owner, approved copy, region or platform, ordering, minimum visible time, acknowledgement, and skip behavior for each required notice. Measure display time from the rendered appearance and give players a way to keep text visible while reading. Use the applicable title agreements and platform guidance for actual timing. Review photosensitive effects in the finished opening and remove unsafe effects at the source. [Xbox photosensitivity guideline](https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/118) · [Xbox accessibility guideline version history](https://learn.microsoft.com/en-us/gaming/accessibility/xag-version-history)

## Keep the player’s route intact

Separate title presentation from menu readiness. Show when a save is still being checked. Validate the profile, schema, integrity, and checkpoint before enabling Continue. Explain fallback to the last good generation, incompatible data, or an unresolved cloud conflict. Keep the existing save intact when loading fails or the player backs out. New Game needs an explicit choice. [Microsoft GDK Game Saves system dialogs](https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/game-save/game-saves-dialogues)

In Godot, request scene resources with `load_threaded_request()` and poll `load_threaded_get_status()` across frames. Report real progress when available and use a status label while work is indeterminate. Fetch the resource only after the loaded status because an early `load_threaded_get()` can block. Keep the current screen responsive during scene preparation. Bind status, completion, and failure to the current request and ignore callbacks abandoned by cancel or retry. [Godot background loading](https://docs.godotengine.org/en/stable/tutorials/io/background_loading.html) · [Godot ResourceLoader](https://docs.godotengine.org/en/stable/classes/class_resourceloader.html)

| Player action | Destination |
| --- | --- |
| Continue from menu | Last usable committed save |
| Resume after suspend | Held live session, with safe focus on return |
| Retry checkpoint | Last committed checkpoint in the current session |
| Confirm restart | Beginning of the intended level or run |
| Cancel a load or decline restart | Prior safe menu or paused state |

## Verify the target build

Capture cold and warm startup on representative devices. Record the exact build and profile, time to first visible and interactive frames, time to menu readiness, input response and frame stalls during loading, and the time from the load command to feedback and playable state. Separate player reading time from engine waits. Test controller reconnect, suspend and resume during menu and play, invalid saves, load failures, cancel, retry, and completion after foreground changes. Microsoft’s platform tests exercise suspend, progress retention and reloading a subsequent save. [Xbox title stability tests](https://learn.microsoft.com/en-us/gaming/gdk/docs/store/policies/xr/xr001)

The **Bring the relay station back online** Lab exercise compares three synthetic startup traces. Its notice time and budgets belong to that exercise. Review legibility, timings, real device behavior, and approved notice copy in the target build.
