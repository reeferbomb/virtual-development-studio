# Reading an action encounter

A player taps a command, the scenery changes, a teammate gains an opportunity, and a witness changes its plan. The four events can happen at different times. These reference studies inform an original arcade prototype that lets a designer inspect each event separately.

## Call of Duty and Modern Warfare 2 (2009)

Infinity Ward’s 2009 game offers three distinct contexts. Campaign uses automatic checkpoints and lets players revisit finished missions. Special Ops offers short objective and time-trial challenges, supports two-player cooperation, and lets players revisit unlocked missions at three difficulty levels. In online multiplayer the match keeps running while a player opens the objectives screen, and a new class chosen there takes effect at the next spawn. Those differences matter when borrowing a retry or menu convention. [Original manual, Main Menu and Pause/Objectives Screen](https://steamcdn-a.akamaihd.net/steam/apps/10180/manuals/CODMW2_Manual.pdf?t=1436565389) · [Activision’s original game listing, Special Ops](https://store.steampowered.com/app/10180/Call_of_Duty_Modern_Warfare_2_2009/)

The manual also describes an interaction prompt that appears near usable objects, a directional damage cue, and a reticle that changes with movement. Each helps answer a different question under pressure. Can I act here? Where did that change come from? Has my current action changed what I can do? [Original manual, Heads-Up Display](https://steamcdn-a.akamaihd.net/steam/apps/10180/manuals/CODMW2_Manual.pdf?t=1436565389)

**Graveforge design inference.** Give one short encounter a repeatable start. Acknowledge a command immediately, schedule its world effect separately, and make a rejected repeat legible. In the arcade exercise, a tap can be accepted even when the later deflection misses. Log both outcomes. In a playable version, compare the command timestamp, first visible response, impact cue and retry time. The prototype's tick budgets are original tuning choices.

## Battlefield across three releases

| Reference | What the developer or publisher documents | Graveforge design inference |
| --- | --- | --- |
| Battlefield series | EA’s retrospective traces the class system and interactions across land, sea and air to *Battlefield 1942*. It identifies squad and commander features in *Battlefield 2*. [EA series retrospective](https://www.ea.com/games/battlefield/news/battlefield-anniversary-community-videos) | Give two jobs different effects on one shared objective. Test the same inputs after removing one contribution to see what it enabled. |
| *Battlefield Vietnam* (2004 standalone PC game) | Lead designer AJ Marini describes developing a helicopter flight model players could understand, plus technical work to maintain frame rate in dense foliage. He names cities, mountains and river deltas alongside jungle as distinct map settings. [Developer Q&A](https://www.gamespot.com/articles/battlefield-vietnam-qa/1100-6076300/) | A new traversal verb changes both input demands and what the player must read in the setting. Test travel time and landmark visibility together in an original scene. |
| *Battlefield: Bad Company 2* (2010 base game) | The manual describes four-player squads, squadmate respawn and complementary kits. Engineers repair friendly vehicles, medics restore teammates, and assists contribute to score. DICE also describes destruction that alters buildings and cover during a match. [EA manual, Squad Play and Kits](https://eaassets-a.akamaihd.net/eahelp/manuals/battlefield-bad-company-2-manuals_Microsoft%20XBOX360.pdf) · [EA/DICE multiplayer announcement](https://news.ea.com/press-releases/press-releases-details/2009/DICE-Delivers-Best-of-Breed-Multiplayer-Action-on-March-2-2010-With-Battlefield-Bad-Company-2/default.aspx) | Give changed scenery an observable rule. The arcade's panel intercepts the first two successful deflections. Later sparks can reach a bell through the opening. A teammate can cash in the bell and restore the panel. |
| *Battlefield: Bad Company 2 Vietnam* (2010 expansion) | DICE’s announcement identifies it as a multiplayer expansion to the 2010 base game. It describes new maps and vehicles with established modes including Conquest and Rush. [EA/DICE expansion announcement](https://news.ea.com/press-releases/press-releases-details/2010/EA-Storms-the-Frontlines-With-Battlefield-Bad-Company-2-Vietnam/default.aspx) | Keep one known objective and change the space around it. Compare two layouts with the same scoring rules to learn whether navigation, team timing or encounter readability changed. |

## Naughty Bear (2010)

In a pre-release interview about the original game, A2M’s lead designer and creative director described small sandbox areas, points for witnessed actions, and characters that could change plans. Their example of a bear trying to leave and finding its vehicle unavailable connects the state of a prop to the character’s next reaction. This is a developer account of the design. It supplies no measurements of what players noticed during play. [A2M developer Q&A, Hooked Gamers](https://www.hookedgamers.com/features/2010/06/27/interview_with_naughty_bear_developers_a2m.html)

**Graveforge design inference.** Make NPC knowledge local. In the arcade prototype a clockwork usher sees a panel open and starts inspecting the bell. If it later hears the chime while watching, it cheers. Replay the same input schedule while masking only its view of the panel opening. The bell and team score follow the same rules, but the unprepared usher searches for the sound. A playtest can ask which event the player thinks changed the usher’s behavior.

## Verify the original encounter

1. Log accepted and busy inputs, the delayed contact outcome, the panel state, the teammate’s bank receipt and each NPC state change. Include an early bank attempt and a missed spark.
2. Replay with the opening hidden from the witness. Compare the witness histories and confirm the shared objective still resolves. The Lab evaluates these deterministic event traces.
3. In an actual build, capture input-to-render timing and try two controllers. Check whether both players can tell who contributed, when a repeat becomes available and why the usher reacted. Collect playtest observations separately from model output.
