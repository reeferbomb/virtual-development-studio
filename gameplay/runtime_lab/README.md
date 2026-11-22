# Graveforge Runtime Lab — v38

The Runtime Lab is a small, original Godot 4 test project built by Graveforge's
six specialists. It runs **real engine code**, separately from the Academy's
structured exercises and from the Studio's existing release gates.

From the public Studio checkout on a Linux workstation, create a fresh private
output directory outside the repository:

```sh
python3 -m gameplay.runtime_lab.runner --output ../runtime-lab-test --engine
```

Omit `--engine` to export the reviewed source without executing it. Each run must
have a new output destination; the runner refuses existing paths, paths inside
the checkout and symbolic links. Its `--engine` option needs an installed
Godot 4 executable and Linux user network namespaces. It cannot launch an
arbitrary game, plugin, script, project or externally supplied asset. On a
Windows workstation, the original template can be studied or integrated into
Godot manually; the CLI is verified on Linux only.

| Probe | What it exercises |
| --- | --- |
| NPC | Patrol, sight, chase, bounded memory/search and return |
| Difficulty | Opt-in, bounded adaptation with stable difficulty settings |
| Capture | Real consecutive engine-frame intervals and capture lifecycle |
| Interface | Control geometry, focus and menu/retry state |
| Presentation | Environmental clues, engine animation/cue/effect lifecycle and accessible alternatives |
| Replay | Seeded scenario, versioned checkpoint, retry and deterministic input replay |

The private `reports/report.json` contains the observed check outcomes, exact
source inventory, source checksum, Godot version and runtime log checksum.
`reports/qa.log` is the raw bounded engine result. When the probes pass,
`reports/captures.json` contains measured test-scene frame intervals in the v37
production intelligence format; `reports/intelligence.json` is the advisory
analysis of the supplied capture(s). Open the latter in the Command Center's
**Intelligence** tab. Missing diagnostic domains remain explicitly unevaluated.
An observed timing warning does not mean the capture lifecycle failed; it also
cannot establish performance on a rendering device.

Exit code 0 means the requested export or scripted QA passed; 1 indicates a
scripted runtime failure, 2 unavailable/invalid export or runtime prerequisites.
The runner bounds process output and execution time, checks the fixed report
schema, source identity and exit status, verifies the original source files
again after runtime, and keeps the runtime environment isolated from the
operator's usual configuration. A source checksum is not a signature or
malicious-tamper proof.

The lab records only its own scripted scenario, no outside games or human
participants. Headless checks do not certify rendered visual quality, audio
quality, actual controller devices, player enjoyment, accessibility, GPU
performance, or release readiness. Test the authorized target build and target
hardware separately. Keep all exports, logs and captures private.
