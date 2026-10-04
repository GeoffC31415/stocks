# Documentation index

Start with [workflow.md](workflow.md). It owns development/release/cleanup policy
and labels proposed commands separately from installed capabilities.

## Day-to-day

- [Analysis semantics](analysis.md): interpreting observations, returns and scope.
- [Trading 212 service sync](trading212-service-sync.md): button/worker contracts,
  safe diagnostics, extension policy and activation recovery limits.
- [Release controller](simple-release.md): code-only publication/rehearsal/recovery.
- [Sync integrity](../backend/docs/sync-integrity-operator.md): ingest invariants.
- [Sync diagnostics](sync-reliability-operator-notes.md): failure/freshness semantics.

## Specialized references — load only when needed

- [Public hosting](public-hosting.md)
- [Broker isolation](broker-isolation.md)
- [Passkeys](passkeys.md)
- [Passkey-only cutover](passkey-cutover.md): explicit operator gate, not routine deployment.
- [Security identity](security-identity.md)
- [Market data](market-data.md)

Historical plans, reviews, verification transcripts and Barclays automation
handoffs live outside repositories under `~/archives/stocks-docs` and
`~/archives/stocks-retired`. Archives preserve worktree-specific edits with hashes;
they are not authoritative current instructions. Query the installed release and
service configuration rather than trusting a dated document's deployment claim.
