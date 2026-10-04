# Documentation

These guides describe current source contracts, not the currently deployed revision.
Master is the sole pre-deployment source; a local commit, pushed revision or prepared
bundle is not proof of activation. Read back the actual release before making live claims.

- [Product semantics and navigation](../README.md)
- [Deployment and recovery](simple-release.md): sole home-script entrypoint and refusal handling.
- [Hosting and backups](public-hosting.md): isolation, TLS and private persistence.
- [Passkeys](passkeys.md): owner use, sessions, API and local recovery.
- [Sync and development](sync-reliability-operator-notes.md): worker routes, status and isolated checks.
- [Ingest safety](../backend/docs/sync-integrity-operator.md): paired imports, trusted HL ownership and reviewed closures.
- [Market data](market-data.md): cache/FX/coverage limits.
- [Security identity](security-identity.md): exact reviewed aggregation registry.

Historical plans, migration commands, test timings and release evidence belong in
Git history/private archives, not in current operating instructions. Archived
handoffs cannot authorize activation, database changes or schedule catch-up.
