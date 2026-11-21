# Player Experience Academy — field guide

The goal is to create games that players want to play, not merely games that
compile. The six disciplines below complement the existing production academy.
Use them within an assigned project; do not silently alter the owner's design
canon or release requirements. Treat each proposed source of enjoyment as a
hypothesis for the intended audience, not a numeric measure of universal fun.

## 1. Design for a particular kind of enjoyment

Write the player fantasy, audience, genre, device and intended emotion first.
Describe a short core loop: goal, action, decision, consequence, feedback and
next choice. Prototype the loop before committing to expensive content.
Make controls responsive and outcomes understandable. A challenge can be
satisfying when the player learns, gets a fair opportunity to improve and can
recognize their progress. A difficult task is not automatically frustrating,
nor is a quiet stretch automatically boring. Curiosity, comedy, atmosphere,
expression, cooperation, competition and suspense can all support enjoyment.

| Intended experience | Design questions | Evidence to seek |
| --- | --- | --- |
| Competitive FPS | Does positioning, aim, team play and counterplay matter? Are deaths explainable? | Route and fight decisions, input response, perceived fairness, voluntary rematch |
| Survival/horror | Do preparation and exploration change meaningful risks? Do quiet periods build dread? | Risk decisions, tension and relief, recovery clarity, frustration versus fear |
| Narrative adventure | Do characters, mystery and choices keep the player emotionally invested? | Character recall, comprehension, emotional response, desire to see the resolution |
| Sandbox/building | Can players express ideas and discover meaningful system interactions? | Self-set goals, experimentation, distinct creations, voluntary revisits |
| Puzzle/strategy | Can players infer rules, plan, learn and pursue distinct solutions? | Insight, failed approaches, explanations of decisions, alternative victories |

## 2. Diagnose the reaction, not just the symptom

Observe players doing the task without coaching them through the answer.
Record neutral behavior before interpreting it. Ask open-ended questions
after the session ("What were you trying to do here?", "What would you change?",
"What made you want to stop?"). Ask directly about enjoyment, frustration,
fairness, comprehension and desire to play again; do not infer an emotion
from silence, playtime, a smile or a quit event alone.

| Observed signal | Competing explanations | Next targeted check |
| --- | --- | --- |
| Player waits, wanders or repeatedly checks menus | Unclear objective, deliberate exploration, missing affordance | Ask their goal; compare objective cues or first-task completion |
| Player repeats one action | Enjoys mastery, lack of options, dominant exploit, required grind | Compare alternative strategies and ask why they chose it |
| Player abandons a challenge | Bored, frustrated, accessibility issue, time limit, satisfied | Ask reason, note failures and context, test a targeted revision |
| Player loses and retries | Enjoys challenge, wants closure, feels compelled to recover loss | Check perceived fairness and whether retry is truly optional |
| Player returns voluntarily | Curiosity, social play, skill improvement, habit | Ask reason, examine whether the next session offers meaningful choices |

Compare novice and experienced audiences; recruit representative consenting
players and provide appropriate accessibility options. Define observation
windows, denominator, completion and exclusion rules before testing. Keep
nonresponses and external interruptions separate from design-attributed
dropouts. Compare the same task, device and version where possible; use
counterbalanced presentation or independent groups to reduce order bias.
Small samples reveal issues but cannot establish population-wide preference.
Never fabricate participants, survey answers, telemetry or consent. Store
only private, minimized, authorized evidence; no automatic collection,
third-party analytics, direct player identifiers, recordings or public reports.

The Player Experience Inventory (PXI) separates immediate experiences of
features (such as ease of control or audiovisual appeal) from broader
experiences (such as mastery or immersion). That distinction helps diagnose
why a technically functional feature fails. If using a validated instrument
in actual research, follow the instrument's conditions; a home-made survey
is not a validated PXI score.

## 3. Make repeat sessions worth playing

Identify two or more meaningful approaches where the game permits them.
Consider mastery, changing tactical contexts, systemic encounters,
player-driven goals, social dynamics, distinct builds, optional discovery and
branching narrative. A carefully authored linear story can succeed through
a single excellent experience; do not force procedural systems into it.
Ensure different routes or seeds change decisions or consequences rather
than just visual decoration. Test dominant strategies, guaranteed dead ends,
content exhaustion, unfair randomness and overly long repetitive travel.
Give players satisfying stopping points, fair recovery and optional return;
do not use punishments for taking a break, artificial scarcity, compulsory
daily chores or deceptive reward mechanics to inflate time played.

For a concrete production study, examine Valve's *Left 4 Dead* AI systems:
procedural enemy populations and dramatic pacing can vary encounter pressure
without requiring an entirely new level. Test whether a similar approach
actually changes decisions and creates breathing room in the intended game.
Do not copy Valve's assets or assume its pacing fits every genre.

## 4. Meet the visual promise

Agree on a visual target before producing assets: mood, style (realistic,
stylized, abstract, retro), camera distance, reference set, platform and
performance tier. Derive a compact art bible with sample silhouettes,
scale, color palette, material behavior, lighting, composition, animation
and UI conventions. Use legally sourced references without copying assets.
References guide expectations; they are not proof of final quality.

Review actual gameplay views, not only a hand-picked hero render:
near/far, bright/dark, motion, interactions, multiple aspect ratios and
representative low/high graphics settings. Check material/lighting consistency,
contact with the environment, clipping, foot sliding, believable scale,
texture repetition/seams, readability and tone. For realism, prioritize
coherent forms, materials, lighting, movement and spatial detail before
increasing polygon counts. A cohesive stylized game can exceed a visually
inconsistent realistic one. Record each mismatch, severity and intended fix.

Use readable silhouettes, visual hierarchy, consistent affordances,
accessible text, redundant shape/label/sound cues, configurable contrast,
motion and camera options. In dark scenes maintain an intentional atmosphere
without making critical interactions or hazards indistinguishable. Test
contrast against actual changing backgrounds and test with target displays.
Review responsiveness, frame-time spikes, loading, input latency, memory
and motion stability on representative hardware. A static screenshot,
synthetic budget or structurally valid material is not device evidence.

## 5. Close the learning loop

For each assigned review, retain a private record using this outline:

1. Target experience, intended audience, platform, exact build/spec identity.
2. Core-loop hypothesis and explicit risk (boredom, confusion, frustration,
   unfairness, repetition or visual expectation mismatch).
3. A reproducible scenario, objective metrics and questions; baseline and
   candidate conditions, limits and sampling plan.
4. Actual observations, counts/denominators, missing data and competing
   explanations; separate subjective feedback from instrumented measures.
5. One prioritized modification, predicted tradeoff and regression guards.
6. Fresh same-scenario verification, uncertainty, open issues and independent
   review. Distinguish synthetic practice, actual engine output, visual
   judgment, player observation and device measurements.

Use the Academy's matching Lab exercises for explicitly assigned practice.
They measure structured reasoning or supplied fixture data, not fun,
artistic taste, human behavior, accessibility certification, or model weights.
Do not turn a passing practice result into a game's release approval.

## Reading for designers and reviewers

- Ryan, Rigby & Przybylski (2006), [The Motivational Pull of Video Games](https://doi.org/10.1007/s11031-006-9051-8):
  research connecting motivation to perceived control, mastery and social connection.
- Sweetser & Wyeth (2005), [GameFlow](https://doi.org/10.1145/1077246.1077253):
  an evaluation framework for gameplay enjoyment, not an automatic classifier.
- [Player Experience Inventory development and validation](https://doi.org/ggjqff):
  distinguishes immediate functional experiences from broader psychosocial outcomes.
- Michael Booth (2009), Valve, [The AI Systems of Left 4 Dead](https://steamcdn-a.akamaihd.net/apps/valve/2009/ai_systems_of_l4d_mike_booth.pdf):
  production example of procedural variation and pacing.
- Microsoft, [Xbox Accessibility Guideline 102](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/102)
  and [Guideline 103](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/103):
  contrast, meaningful information across different sensory channels, and
  testing game-specific backgrounds and conditions.
- UK Government Service Manual, [Getting users' consent for research](https://www.gov.uk/service-manual/user-research/getting-users-consent-for-research)
  and [Analyzing research sessions](https://www.gov.uk/service-manual/user-research/analyse-a-research-session):
  practical guidance on consent and separating findings from raw observations.

The practical review procedures in this guide are original Graveforge
recommendations informed by these references. Apply and revise them with
evidence; do not assume a framework establishes the quality of any particular game.
