# Terrain changes and strategic commitments

## From Dust (2011)

Ubisoft Montpellier made terrain part of the control surface. The player can sculpt land, drain water, and redirect hazards while keeping a community safe. The development team described Galileo, its real-time simulation of water and lava flow, erosion, sedimentation, and vegetation. A channel that clears one route can change what happens downstream. The important design relationship is that the same material edit changes the environment and the ways people can move through it. [Ubisoft’s publisher description](https://store.steampowered.com/app/33460/From_Dust/) · [Ronan Bel and Eric Chahi at GDC Europe 2010](https://www.gdcvault.com/play/1013667/Creating-a-High-Performance-Simulation)

Eric Chahi described low tide opening a possible settlement window and direct terrain manipulation giving the player a way to respond when a character changes course. The transferable lesson is to show the next hazard and its likely route early enough for the player to act. When an edit shifts the problem elsewhere, show the affected place and the remaining time to respond. [Eric Chahi’s developer interview](https://www.gamedeveloper.com/design/the-core-of-i-from-dust-i-)

## Sid Meier’s Civilization Revolution (2008)

In the original Xbox 360 release, a settler can inspect nearby food, production, and trade before choosing a city site. The city’s surrounding spaces determine its yields, and nearby resources can need a technology before they become useful. Players can direct a city’s trade toward research or wealth and spend gold to finish construction immediately. These choices connect a local terrain decision to a later technology, treasury, or production decision. [2K Games and Firaxis Xbox 360 manual, “Terrain” and “Cities”](https://epix.xbox.com/shaXam/0201/c0/8c/c08ccaa5-b593-4e4c-88ff-3ab4d5150773.PDF)

The manual describes four ways to win. Domination requires enemy capitals. Economic and cultural victories each pair a threshold with a final construction project. Technology culminates in a spaceship reaching Alpha Centauri. The diplomacy panel shows comparative progress across the victory types. The transferable lesson is to display how close each plan is to its actual objective and what the current investment delays. [2K Games and Firaxis Xbox 360 manual, “Diplomacy” and “Victory”](https://epix.xbox.com/shaXam/0201/c0/8c/c08ccaa5-b593-4e4c-88ff-3ab4d5150773.PDF)

## Original Academy exercise

In **Allocate a storm crew at the rain terraces**, a nursery and a freight yard share runoff. The crew can move a finite supply of blocks or do productive work. On each turn, rainfall splits around the current barrier, the sites drain at different rates, and sufficiently heavy overflow can knock one block into sediment. Deep water stalls work. A nursery plan and a freight plan can each meet their own objective under the same initial conditions. Removing a single barrier change and replaying the remaining decisions isolates the effect of that change.

The Lab checks a synthetic trace with whole-unit flow, material movement, and output. In an engine prototype, preview both sites before committing a crew action. Show stored water, drainage, where a lost block went, and both objective totals. Ask players to predict the next runoff split and explain which job the crew gives up. Repeat with a dry turn and a stronger storm to see where the same strategy breaks.
