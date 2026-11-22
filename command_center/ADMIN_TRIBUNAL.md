# Graveforge Administration and Tribunal — v41

## What this does

Use this local toolkit to resume long projects without losing decisions or
mixing up versions. It is separate from the game tools. The studio still uses
the six Midnight Shift roles; a review is not permission to release software.
The owner makes the final decision. No subscriptions, model APIs, account
credentials, automatic uploads or chat deletion are required.

The journal is an ordered, integrity-checked history of two independent
streams: `registry` (projects and continuations) and `tribunal` (review work).
Each write requires the latest revision; preserve old copies and raw evidence.
It is a local integrity mechanism, not a signature or authentication system.
Never commit this journal, private transcripts, candidate files or outputs.
Keep backup copies in a durable authorized private location.

## Getting started

From the repository with Python 3, create a private directory outside the
checkout (on Linux, `mkdir -m 700 ../studio-private`), then use:

```sh
python3 -m command_center.admin_cli --journal ../studio-private/history.json state
python3 -m command_center.admin_cli --help
```

A missing journal starts at revision zero. Save each event as a small JSON
file in the private directory. Append it with the displayed current revision:

```sh
python3 -m command_center.admin_cli --journal ../studio-private/history.json append registry ../studio-private/event.json --revision 0
```

Use `append tribunal` for review events. On conflict, read `state` and inspect
the existing event; never blindly replay a stale write. All commands return
JSON, except help. Read `state` only locally: its full history is private.

## Project continuation

The registry event schemas are described in `admin_registry.py`. For example,
start a project with this intentionally fictional source identity:

```json
{"type":"project","project_id":"sample","name":"Sample game",
 "source":{"commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","release_ref":"project/sample/v1","library_ref":null,"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","dirty":false},
 "environment":{"engine":"Godot 4","platform":"Linux"}}
```

Use actual fingerprints, full commit IDs and artifact references instead of
the sample values. `identity` records a changed source or environment. `log`
registers a separately retained complete or partial transcript by stable
chat ID, reference and SHA-256. Store only relevant project logs. `decision`
records a unique ID, decision text, rationale, status and optional superseded
decision ID. Historical decisions stay visible.

`checkpoint` takes `checkpoint_id`, `summary`, relevant `log_ids`, `criteria`,
`tests`, `pending` and `gaps`. Each criterion has `id`, `description`,
`high_risk`. Each test has `id`, `criterion_id`, `kind` (`positive` or
`negative`), `evidence` (`observed`, `reported`, `not-run`), `result` (`pass`,
`fail`, `unknown`) and `raw` (null, or `{ "ref": "private reference", "sha256": "actual digest" }`).
Observed requires a raw output reference and digest. High-risk criteria require
observed positive and negative tests. Reported claims and unrun tests never
count as verified; changed identity makes prior results stale.

```sh
python3 -m command_center.admin_cli --journal ../studio-private/history.json handoff sample cp1
python3 -m command_center.admin_cli chat-capability
```

Export the packet locally. On explicit user request or real platform warning
only, record a `request` event (`project_id`, `checkpoint_id`, `reason` equal
to `user-request` or `platform-warning`, and `detail`). Check current project
and packet hash, and create a **regular Chat**, not a Work conversation, in
that same project using the authorized host interface. Attach the relevant
complete logs and the handoff; never attach unrelated logs. Verify the result
in the destination yourself. Record a `receipt` containing `project_id`,
`checkpoint_id`, `packet_sha256`, `actual_project_id`, `mode` (`regular`),
`chat_id` and `ref`. The registry rejects duplicate or stale receipts. It does
not claim that an unverified destination exists. No automatic chat API or
fullness measurement is provided; fullness is unknown until an explicit
request/warning. Unavailable transcripts are listed as gaps rather than
fabricated. Do not delete old chats or checkpoints.

## Tribunal: free browser or offline manual exchange

1. Record an `open` event with `op`, `event_id`, `review_id`, UTC `at`, a
   manually reviewed `summary`, `source_sha256`, `shareable:true`, and optional
   `risk` (`high` or `normal`), `providers`, `roles` and coordinating `owner`.
   Default roster: ChatGPT, Claude, Gemini. Keep private data out of summary.
2. Generate independent proposal packets (these deliberately exclude each
   other's proposals) with:

   ```sh
   python3 -m command_center.admin_cli --journal ../studio-private/history.json packet review1 claude proposal
   python3 -m command_center.admin_cli provider claude
   ```

   Save the packet JSON privately. `provider` reports operator-declared status
   only: `unknown`, `unavailable`, or `ready-for-manual`. It does not test login.
3. Run `relay PACKET.json --share-confirmed`. Confirm that the exact summary
   is relevant and safe before copying `copy_text` into a free existing Claude,
   Gemini or ChatGPT browser session you are authorized to use. No Claude Code,
   paid API or automation is needed. If access is unavailable, record an
   unavailable response slot instead. Never fabricate a response.
4. Fill the returned `response_template` with actual reply text, UTC receipt
   time, provenance and a separately reviewed shareable summary. Save it
   privately, then use `receive PACKET.json RESPONSE.json --event-id reply1
   --revision N --share-confirmed` with the journal option. The response is
   attributed to the operator's receipt, not independently authenticated by
   Graveforge. Raw response and digest remain private. An offline JSON entry
   uses the same form and validations. The Python relay adapter accepts a
   supplied response; it does not launch browsers or models.
5. Once all independent proposal slots have a recorded response or explicit
   unavailable status, generate `critique` packets; only approved summaries
   are included. Repeat the relay/import step for cross-critique. Record
   disagreements with `dispute`; use `evidence` and `resolve` with actual
   matching source observations. An unavailable slot has `op:response`, the
   review/event IDs, UTC `at`, provider, round, exact packet digest,
   `status:unavailable`, a brief shareable reason and `shareable:true`.
6. A separate verifier records evidence (verifier ID distinct from reviewers,
   source digest, `status`, `outcome`, `risk`, `test_kind`, artifact SHA-256 and
   summary). The coordinator records `synthesize` with owner, summary and
   next action. The owner records `decide` with `actor:user` and decision
   `accept`, `revise`, `defer` or `reject`. Acceptance requires independent
   observed positive evidence, negative evidence for high risk, and resolved
   conflicts; a provider's claim or agreement is never a test. Use
   `review-handoff REVIEW_ID` for local review history only.

## Reconcile competing versions

Never assume two archives with the same displayed version share ancestry.
Hold each immutable original and rollback checkpoint. Use:

```sh
python3 -m command_center.admin_cli fingerprint-git /path/to/repo studio v40.0
python3 -m command_center.admin_cli fingerprint-file /path/to/candidate.zip studio v40.0
python3 -m command_center.admin_cli compare BASE.json CANDIDATE.json --repo /path/to/repo
```

The local Git fingerprint includes the exact commit, working content hash,
index identity and dirty state; archives are hashed without extracting or
executing. Known local commits can be compared by ancestry; unknown or
diverged same-project candidates are quarantined for review. Use
`project/<project>/<version>` namespaced tags for projects. Only a clean,
reviewed canonical Studio checkout can be considered for a shared release;
project candidates must never replace core Studio merely by version label.
Record proposed improvements with owner, source identity, status and rationale
in the decision ledger. Rerun exact tests on integrated source and keep raw
test outputs. No automatic merge, promotion, archive extraction or deletion.

For standalone coordinator Godot runs, add `--godot-clean` before `--` to
reject error, warning and failure diagnostics even if the child exits zero.
The raw log, actual child exit code and diagnostics are retained. The legacy
non-strict default remains compatible; runtime fixture parsers still validate
their exact markers. A clean diagnostic log alone is not proof of acceptance.

## Midnight Shift responsibilities

Count Blueprint owns design and integration boundaries; Major Mayhem or the
relevant implementer authors a candidate; Madame Glitch and Grimbrush provide
independent critiques; Doctor Doomcheck verifies independently on exact source
and negative tests; Baron Buildgrave preserves source and evidence identity.
The coordinating lead synthesizes and records the owner's final decision.
Names are assignments, not authenticated identities. External reviewers are
optional; if unavailable, record the gap without relabeling another agent.
