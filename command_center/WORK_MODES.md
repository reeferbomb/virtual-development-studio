# Unified Creative & Planning Mode — v41.2

## One mode, two phases

- **Creative phase:** explore ideas before committing. Produce at least two
  original alternatives, each with a player-facing pitch and tradeoff, a lead
  recommendation, risks and questions that future playtests can answer. User
  selects an alternative (or defers/rejects the session).
- **Planning phase:** turn the chosen direction into a workable pre-production
  plan: bounded deliverables, role owners, dependencies, acceptance criteria
  and high-risk tasks within the same saved session. No separate activation.
- **Development:** the existing production boards, work orders, evidence and
  release gates remain the same. A mode approval is not an implementation
  order, release approval, or claim that a game is fun or complete.

| Midnight Shift member | Creative | Planning |
| --- | --- | --- |
| Count Blueprint | System options and feasibility | Architecture, milestones and dependencies |
| Major Mayhem | Player fantasy, mechanics, fun and replay | Gameplay slices and criteria |
| Doctor Doomcheck | Independent critique and playtest hypotheses | Positive/negative verification and risks |
| Madame Glitch | HUDs, menus, onboarding and accessibility concepts | Controller, interface and UX criteria |
| Grimbrush | Original visuals, narrative, animation, voices and audio | Asset, story and presentation pipeline |
| Baron Buildgrave | Free-tool, licensing and budget feasibility | Build, packaging, capacity and recovery |

The default five Astra Ultra and one Sol Max model requests are unchanged.
Actual host availability is not assumed. The host lead dispatches only within
authorization; each specialist returns an independent report or an explicit
unavailable status. The lead synthesizes and the user decides. The tool
exports assignment packets, not live agent calls or generated opinions.

## Use the workflow

First register the project and private journal using the
[administration guide](ADMIN_TRIBUNAL.md). Example commands below use project
`sample` and journal `../studio-private/history.json`. Replace example
revision numbers with the latest value from `state`; never blindly retry a
revision conflict. For sensitive briefs or reports use the private JSON event
form (`append registry ... --revision N`) rather than command-line history.

```sh
python3 -m command_center.admin_cli --journal ../studio-private/history.json mode-start sample design1 --brief 'Explore a courier game' --constraint 'Controller-friendly' --constraint 'Free assets only' --revision 1
python3 -m command_center.admin_cli --journal ../studio-private/history.json mode-dispatch sample design1
```

The dispatch packet contains private source identity, independent assignment
instructions and the original brief. Give each authorized role only its own
assignment and the relevant common context, not other initial reports. Report
actual findings, using the stable role IDs `architecture`, `gameplay`,
`verification`, `ui`, `content`, `build_operations`:

```sh
python3 -m command_center.admin_cli --journal ../studio-private/history.json mode-report sample design1 gameplay reported --phase creative --summary 'Actual specialist findings here' --revision 2
```

Use `unavailable` with the real reason for a missing role. Do not manufacture
reports. Once all six have a disposition, the lead writes the synthesis as a
private JSON file, e.g. `concepts.json` (illustrative data, not evidence):

```json
{"alternatives":[{"id":"routes","title":"Route choice","pitch":"Choose paths around a changing town","tradeoff":"More world states"},{"id":"clock","title":"Timed journey","pitch":"Race a changing deadline","tradeoff":"Less relaxed exploration"}],"recommendation":"routes","risks":["Route variety needs actual playtests"]}
```

```sh
python3 -m command_center.admin_cli --journal ../studio-private/history.json mode-synthesize sample design1 concepts.json --phase creative --revision 8
python3 -m command_center.admin_cli --journal ../studio-private/history.json mode-handoff sample design1
```

Read the exact `synthesis_sha256`; only after the user chooses the concept,
record `mode-decide sample design1 approve --phase creative --choice routes --digest HASH
--rationale 'User selected this direction' --revision 9`. The verification
role must have returned a critique for approval. `defer` and `reject` close
the session without choosing an alternative; no digest is required for those.
The actor field records the operator's attribution, not remote authentication.

Approval opens planning automatically in the same `design1` session. Read
`mode-dispatch sample design1` again and use `--phase planning` for new reports,
synthesis and decisions. The chosen concept is retained and creative reports
remain in the private history. Late creative reports are rejected. A planning
synthesis has this shape:

```json
{"tasks":[{"id":"prototype","title":"Build a route prototype","owner":"gameplay","depends_on":[],"acceptance":["Both routes are selectable"],"high_risk":false},{"id":"verify","title":"Test retry and rewards","owner":"verification","depends_on":["prototype"],"acceptance":["Retry restores initial state","Duplicate reward is rejected"],"high_risk":true}],"risks":["Unproven physical-controller comfort"]}
```

Approve the plan using `--phase planning` and its exact synthesis digest (no `--choice`). Cycles,
unknown dependencies, duplicate IDs, invalid roles and empty acceptance lists
are rejected. High-risk flags are instructions for future independent positive
and negative tests, not completed evidence. The lead must separately obtain
development authorization and use the normal production planning workflow.

## Autonomous drafting and training

Add `--autonomous` to the combined `mode-start` command to delegate provisional
concept selection. Once the creative synthesis has all specialist dispositions
and an independent verification-role report, its recommended concept opens
planning automatically. The recorded choice is provisional, not user approval.
Continue through planning synthesis and present both the concept and plan for
one final owner decision. Missing verification, stale source and other blockers
still stop progress. No autonomous build or release is authorized.
Use `mode-next sample design1` with the journal to get the next safe action:
dispatch pending roles, synthesize, await the user, complete, blocked or stale.
The host lead follows these instructions using available authorized workers;
the local CLI itself does not launch agents or generate their opinions.

The dispatch packet includes the relevant Academy v7 track: `creative-ideation`
or `autonomous-planning`. Practice through the existing training lab; new
exercises check meaningful mechanic variation, hypothesis design, feasibility,
task graphs, critical path, risk tests and rollback. Structural assessments
are learning evidence, not proof of creativity or trained model weights.

Existing single-phase `creative` and `planning` sessions remain supported by
their original commands without `--phase`; explicitly specify those modes only
for legacy or narrowly scoped work. The default is now `creative-planning`.

## Safety and continuation

One open session per project; closed sessions remain immutable. Changing the
source (including dirty tree), environment or registry decisions makes a
session stale. Defer stale work, start again and reuse only revalidated ideas.
The regular Chat handoff includes captured and current work-mode history for
that project, and changes invalidate pending continuation receipts.

The Tribunal remains optional: prepare a separate explicitly approved,
minimal shareable summary via v41 review packets. Never send the private
mode dispatch, journal, raw responses, unrelated logs or credentials to an
external provider. Device tests, human feedback and actual engine evidence
remain distinct from design opinions and plans.
