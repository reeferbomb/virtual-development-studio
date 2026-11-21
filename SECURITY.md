# Security and privacy

Studio is designed for trusted local development. The Command Center listens
on loopback and uses local request checks, not Internet-facing authentication.
Do not expose its port through a public reverse proxy or tunnel.

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
