# Changelog

## 26.0 — Specialist Coordination

### Added

- Persistent, specification-scoped specialist memory derived from accepted handoff reports.
- Dependency-aware ready-task ranking and blocked-task recovery advice.
- Six-role workspace allocation with exact observed occupancy and conflict owners.
- Read-only Coordination workspace and specialist dispatch references.

### Changed

- Portfolio recommendations preserve explicit priority while breaking ties by downstream impact and remaining dependency-chain length before stable IDs.
- Portfolio project snapshots use a coherent shared-lock scan to avoid false conflicts during cross-project role transfers.

### Preserved

- Advisor projections never claim, requeue, launch, accept, or publish work.
- Existing revision-bound operations, private local data and explicit lead review.

## 25.0 — Production Planning

### Added

- Project-type-specific starter milestone blueprints for the six specialist roles.
- Revision-bound, atomic blueprint application to an eligible task board.
- Structural dependency impact analysis and role-constrained hypothetical execution waves.
- Integrity-bound release preflight that cross-checks current dossier evidence and outstanding work.
- A Planning workspace and a real Godot-backed integration smoke test.

### Preserved

- Existing build verification, task claims, release registry, evidence history, handoff reviews and recovery exports.
- Loopback-only local operation and the separation between exported dispatch instructions and actual host agent execution.

## 24.0 — Production Operations

- Initial public MIT-licensed release, with revision-bound work orders, handoff ledger, evidence dossiers, recovery bundles and the existing production toolchain.
