# Security and privacy

Studio is designed for trusted local development. The Command Center listens
on loopback and uses local request checks, not Internet-facing authentication.
Do not expose its port through a public reverse proxy or tunnel.

The Runtime Lab exports only fixed Studio-authored Godot scripts to a new
private directory outside the checkout. Its explicit `--engine` option requires
network isolation and runs only that project with a bounded process and output.
Never use it to execute externally supplied scenes, plugins or scripts. Keep
captures, generated projects and reports private; the original benchmark is
not a telemetry collector or an authenticated release certification.

Production Intelligence is an offline analyzer of deliberately supplied bounded
JSON. Use anonymous aggregate playtest observations only, with prior authorization
and consent; do not submit participant identifiers, real names, recordings, raw
session logs, contact details, paths or credentials. Keep captures and reports
private outside the checkout. The dashboard's Intelligence tab reads report
files in the browser without uploading or persisting them. It displays reported
hashes, not authenticated evidence. No analyzer changes project, practice or
release state, and a passing check does not certify player enjoyment, hardware,
accessibility, hearing safety or release readiness.

Do not commit API keys, private keys, tokens, personal project material,
credential files, user-generated logs, or exported project recovery/dossier
records. Keep the working workspace outside the checkout. No provider API
credential is required to run the local toolkit. Model dispatch exports are
instructions only: they do not grant access to a model provider or launch a
remote agent automatically.

Academy practice history contains original submissions and reviewer notes. Keep
the workspace, ledger and exported reports private; do not expose the local
service port or publish these files. Declared submitter and reviewer roles are
workflow labels, not authentication or proof of authorship. The local integrity
digest detects inconsistency, not malicious rewriting by a trusted disk owner.

The Player Experience Academy uses synthetic practice fixtures, not a player
analytics service. Its playtest-interpretation exercise accepts only bounded
synthetic codes and categorical responses. Never enter real participant data,
recordings, contact details or session notes into Lab. Real playtests need
separate authorization, informed consent, minimized private records, limited
access and a deletion policy. Neither the dashboard nor dispatch automatically
collects player reactions or transmits telemetry.

Game Feel and Presentation practices use bounded synthetic data, not actual
save files, personal settings, recordings or commercial game assets. Do not
submit private player sessions, copyrighted music, proprietary logos or game
files. Use authorized original or licensed production materials, and keep
practice submissions outside the public checkout. Numerical VFX checks do not
certify photosensitivity safety; real frame review remains separate.

Reference Game and Interface exercises use original bounded synthetic scenarios.
Do not submit commercial game binaries, extracted assets, source code, private
game designs or player recordings. Public reference material is for analysis,
not authorization to reproduce protected content. The Lab does not download
or execute reference games or transmit your practice records.

Story and Performance exercises use original synthetic metadata, not recordings,
voice profiles or imported game assets. Do not submit private scripts, actor
identifiers, recordings or biometric information to the Academy. Obtain explicit
authorization and applicable usage rights for voice recording, reuse and synthesis;
never imitate or clone identifiable voices without consent. Keep authorized
production assets and review evidence in the private project workspace. Reference
studies do not authorize extraction or reuse of third-party game assets.

Asset validation reports identify the inspected bytes by SHA-256 and are not
authenticated certificates of quality or safety. The Lab's report viewer reads
selected JSON files in the browser; it does not upload, store or approve them.
Keep reports containing private production information local. Structural asset
checks do not make arbitrary models safe to execute. The optional Godot import
probe is a separate, explicit operation with a disposable project and network
isolation; it does not execute a supplied game project or user script. Treat an
unavailable isolation mechanism as unavailable evidence, not as permission to
run the probe without isolation.

For the original sample assets, provenance records document generated test
content. Keep external dependencies and newly imported assets under their
respective licenses. Never assume an external asset inherits the Studio MIT
license.

The cinematic production runner accepts bounded JSON plans and bindings only.
It creates a fresh private output using fixed trusted Studio scripts and
original verified assets; `--engine` explicitly executes that generated project.
Do not use it to launch unknown Godot projects, scripts, plugins or asset files.
Do not expose or publish private scripts, plans, diagnostics or reports.
Engine checks report observed runtime behavior, not authentication or a
general-purpose engine sandbox.

Before sharing any release, review the exact staged paths and scan text and
binary files for secrets and personal information. Review Git history before
publishing it. If a credential has been committed or otherwise exposed,
revoke or rotate it; removing a file alone does not invalidate the credential.
