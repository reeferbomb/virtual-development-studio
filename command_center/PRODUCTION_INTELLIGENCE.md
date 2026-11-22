# Production Intelligence — v37

This is a private, offline analytical workbench, separate from the Academy's
synthetic exercises and from release acceptance. It turns explicitly supplied
measurements into reproducible observations and revision priorities. No engine,
file discovery, network service, participant tracking, model call, account,
external dependency or automatic publication is required.

## Start here

From the Studio checkout, create a private workspace directory outside the
public repository. The bundled example is invented and must not be presented as
observed production evidence.

```sh
python3 -m command_center.production_intelligence_cli example > ../capture-example.json
python3 -m command_center.production_intelligence_cli analyze ../capture-example.json > ../intelligence-report.json
```

An example with a deliberate pacing warning exits with code 1. Exit 0 means
all six domains were submitted and their checks passed; 1 means one or more
warnings/failures or missing domains; 2 means invalid/unavailable input. Use
`example balance` (or `playtest`, `frame`, `ui`, `audio`, `build`) for just one
domain. Edit the example in your private workspace, replacing fabricated values
with authorized measurements. Include only captures that actually exist.
The bundle envelope requires `schema_version: 1` and a `captures` object with
one or more of the six domain keys. Unknown fields, invalid values, duplicate
JSON keys and oversized input (4 MiB) are rejected. Reports are capped at 2 MiB.

Start the existing Command Center normally and open its **Intelligence** page.
Select the report file. The page reads it in the browser and does not upload,
store or modify it. It validates the report's structure and status consistency,
not the authenticity of the supplied observations or their reported hashes.

## Six independent diagnostic domains

| Domain | Supply | Findings to investigate |
| --- | --- | --- |
| `balance` | Matched scripted trials across authored builds and scenarios | Dominance, viability against designer constraints, missing or short coverage |
| `playtest` | Anonymous aggregate baseline/candidate counts within matched task and cohort | Completion, abandonment, retry, confusion and optional replay differences; insufficient evidence |
| `frame` | Ordered frame intervals in microseconds and scenario-specific target FPS/budget | Nearest-rank p95/p99, worst frame, late share and consecutive late clusters |
| `ui` | Measured widget rectangles, shaped text extents, safe areas, required controls and focus edges per profile | Clipping, overlap, missing controls, unreachable focus and inability to return |
| `audio` | Matched standard/quiet master true peaks and stem RMS, expected cue occurrences | Headroom, speech/background power proxy, missing cue alternatives and quiet-profile reduction |
| `build` | Declared baseline/candidate logical asset manifests, group budgets and required IDs | Footprint growth, asset additions/removals/changes, digest-size inconsistencies and missing assets |

The source modules (`intelligence_balance.py`, `intelligence_playtest.py`,
`intelligence_frame.py`, `intelligence_ui.py`, `intelligence_audio.py`, and
`intelligence_build.py`) describe the schemas; the `example` command generates
valid, editable input without requiring manually constructed JSON. Use stable
non-identifying project labels only, and enforce private handling of both input
and output. Do not use sample thresholds as universal quality standards.

## Production workflow

1. **Count Blueprint** and **Major Mayhem** agree on the gameplay hypothesis,
   intended tradeoffs, reproducible seeds/conditions, and authored constraints.
   Compare the same scripted trials across builds; test meaningful alternatives
   and avoid treating time-to-win as the only measure of value. Analyze actual
   authorized aggregate observations within the same task/cohort and protocol.
2. **Doctor Doomcheck** gathers repeated frame captures on representative
   hardware. Keep distinct device profiles, target FPS and test scenarios;
   record capture configuration and CPU/GPU profiler traces privately.
3. **Madame Glitch** measures the actual rendered text, geometry and focus moves
   for each language/device/profile. Review contrast, affordances, actual input
   and screen-reader feedback independently; a fit check is not UI acceptance.
4. **Grimbrush** measures aligned standard/quiet mix windows and tests cue
   delivery. Review listening, actual subtitles, accessibility, music timing,
   artistic direction and licensed source materials separately. Relative
   digital gain does not establish safe listening levels.
5. **Baron Buildgrave** compares declared byte-level manifests, identifies
   budget problems, and independently checks the actual files and hashes.
6. The lead reviews warnings and failures alongside current build evidence,
   decides what is worth changing, repeats the same scenario, and records
   actual evidence through the existing authorized project workflow. Do not
   replace release gates, submit an example as independent practice, or blindly
   promote a passing report.

The canonical JSON bundle digest and per-capture digests use Studio's
`provenance.spec_digest` (sorted keys, compact JSON; SHA-256). The report digest
is calculated over the report before the `report_sha256` field is added. These
are consistency identifiers, not signatures, file-byte hashes or proof of
authorship. Re-run analysis against the same capture to verify report identity.

## Privacy and limitations

Only explicitly authorized production observations, anonymous aggregates and
original synthetic inputs belong here. Keep the files, reports, instrumented
builds and raw source observations private and outside the repository. Do not
include participant names/IDs, recordings, session notes, contact details,
source assets, full file paths or credentials. Human research still requires
informed consent, minimized private records, limited access and a deletion
policy. The tool has no facility to collect telemetry, identify players or
measure whether a game is enjoyable. Its results cannot certify performance
on untested devices, accessibility, artwork, hearing safety or release status.
