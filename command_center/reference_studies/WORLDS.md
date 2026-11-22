# Public worlds, appointments and repeating time

## Grand Theft Auto V — a public response the player can read

**Documented behavior.** The Xbox One game manual lists ordinary city activities including tennis, darts and racing. Its HUD section describes one to five wanted stars as a visible indication of police interest. These are two aspects of the same public world: the player can pick a destination and the world can report a changing response. The manual supports the meaning of the display; it does not specify every underlying AI transition. [Rockstar Games, *Grand Theft Auto V* game help, “Wanted Level” and activities](https://dlassets-ssl.xboxlive.com/public/content/4f0a3089-ba2c-4f3d-9e38-102a41cbd885/GameManual/9dfeb637-1cb0-46c8-b7d7-0c58cf990494/en-GB/index.html)

**Design inference.** Give players an ordinary reason to visit a public place, then let their actions change how that place works. In our ferry office, a service bell heard by a resident draws the staff’s attention. Repeated calls can interrupt a timetable lesson. A bell rung on an empty landing goes unanswered. A player should be able to predict which of these will happen by observing the room.

## Shenmue — treat availability as a property of the world

**Documented behavior.** SEGA describes a day/night cycle, businesses with opening hours and residents with individual schedules. Investigation includes exploring places and speaking to people. Time and place therefore matter when looking for someone. [SEGA, *Shenmue I & II*, publisher description under “About This Game”](https://store.steampowered.com/app/758330/Shenmue_I__II/)

**Design inference.** Give the ferry guide and clerk independent rounds. Staff can share a room or leave one empty. A guide who has left the tower should be found at their next stop, and returning on a later cycle should produce the same appointment. In a playable version, leave a legible clue at the old post and budget the time it actually takes to reach the new one.

## The Legend of Zelda: Majora’s Mask — make a reset understandable

**Documented behavior.** The Nintendo 64 manual distinguishes returning to the first morning from reaching the end of the three days. Returning preserves major acquired items while reverting various puzzles and events. Discussing the 3DS remake, Eiji Aonuma describes the problem of missing events that happen at specific places and times. The team added hints and improved the notebook, including an event alarm. [Nintendo 64 manual, “Time in the Game” and “About Saving”](https://www.nintendo.com/eu/media/downloads/games_8/emanuals/nintendo_8/Manual_Nintendo64_TheLegendOfZeldaMajorasMask_EN.pdf) · [Nintendo, *Iwata Asks*, discussion of scheduled events and the notebook](https://www.nintendo.com/en-gb/Iwata-Asks/Iwata-Asks-The-Legend-of-Zelda-Majora-s-Mask-3D/The-Legend-of-Zelda-Majora-s-Mask-3D/6-Every-Boss-Stage-is-Weird-/6-Every-Boss-Stage-is-Weird--959902.html)

**Design inference.** Give each state an explicit lifetime. In the ferry exercise, the shift repeats automatically. A traveler keeps their knowledge of the tide table. The crossing permit belongs to a single shift, and staff attention returns to normal when the next shift starts. Predict the final tick and the first tick of the next shift to catch resets that happen in the wrong order.

## Studio test

Record two shifts from the same clock. Check the roster immediately before and after a change of post. Try the bell with and without witnesses, attempt the office service before learning the tide table, then repeat it after the shift changes. The assessment compares a declared action trace with a small deterministic simulation. A playable build still needs tests for travel time, staff movement, readable feedback and a first-time player’s understanding of the reset. [World-schedule exercise](../lab_reference_worlds.py)
