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

For the original sample assets, provenance records document generated test
content. Keep external dependencies and newly imported assets under their
respective licenses. Never assume an external asset inherits the Studio MIT
license.

Before sharing any release, review the exact staged paths and scan text and
binary files for secrets and personal information. Review Git history before
publishing it. If a credential has been committed or otherwise exposed,
revoke or rotate it; removing a file alone does not invalidate the credential.
