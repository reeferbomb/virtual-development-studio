# Contributing to Graveforge Studios

Studio is a local development workbench, not a hosted agent service. Please
keep changes small, reproducible and independently verifiable.

## Local development

Use Python 3.11+, Node.js for UI tests, Godot 4.x for engine integration tests,
and Blender for asset generation. See the README for workstation requirements.
Start the server with a disposable workspace outside the checkout:

```bash
python3 -m command_center.server --workspace ../studio-dev-workspace
```

Run the Python and simulated-DOM JavaScript test suites:

```bash
python3 -m unittest discover -s tests -v
for test in tests/test_*_ui.js; do node "$test" || exit $?; done
```

For the planning workflow, `python3 -m command_center.planning_smoke` also
exercises an actual verified Godot build and a service restart.

## Changes and evidence

- Preserve project/specification identity, revision checks, same-origin
  confinement, and existing task and release acceptance gates.
- Bump the Academy lab version whenever a rubric or evaluator's behavior
  changes, even when its brief is unchanged. Saved records from older digests
  remain historical rather than being silently re-scored.
- Add tests for new behavior and failure modes. Include reproducible evidence
  and explicitly distinguish simulated UI tests from live browser acceptance.
- Keep user workspaces, personal project information, credentials, private
  handoffs, Academy submissions/reviews and recovery exports out of the repository.
- Include only redistributable original or properly licensed fixture assets,
  with provenance where appropriate. Never edit a sealed fixture without
  regenerating and verifying the associated manifest.

## Review

Describe the behavior change, verification commands, and remaining limitations.
Do not claim that a successful local build establishes physical-device gameplay
quality or authorization for external publication. See `SECURITY.md` for
privacy and deployment boundaries.
