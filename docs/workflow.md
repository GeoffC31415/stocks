# Stocks development, publish and housekeeping

## Agreed workflow

1. Work in the single canonical `~/code/stocks` checkout on the gaming PC or
   Surface. Use feature branches, not permanent parallel agent repositories.
2. Obtain a verified WAL-aware snapshot of the authoritative Surface database
   `/var/lib/stocks-data/portfolio.db` through the installed read-only snapshot
   capability. The Surface checkout's `portfolio.db` is not production.
3. Preserve the snapshot and run the test site against a separate working copy.
   Frontend hot reload and backend reload let the owner iterate without deploying.
   Binding beyond loopback requires explicit private-network approval.
4. Test UI/backend/import behavior on disposable data; real broker GET testing is
   explicit. Keep API credentials outside source and out of logs. Never use live
   imports or startup migrations as a development smoke test.
5. After owner acceptance: full gates, independent review, commit, publish to
   `master`, verify remote SHA, prepare an exact-revision release, deploy on the
   Surface, and verify code identity, auth boundary and requested behavior.
6. Only after successful verification, clean all task-created staging. On failure,
   retain bounded evidence/recovery material outside active source until resolved.

## Command consolidation still to implement

Target interface, **not current commands**:

- `stocks dev`: verified snapshot + isolated preview + visible URL.
- `stocks refresh`: explicit DB refresh with rollback backup, never on each edit.
- `stocks publish`: tests/review + approved master publication + Surface release
  preparation, activation and readback.

The repository already has Vite, FastAPI, tests, snapshot/rehearsal helpers and
release tooling. A unified command must orchestrate them, not bypass protections.
A code-only controller cannot silently approve schema, runtime, dependency,
credential or service-policy changes. Such changes require a reviewed supported
path and appropriate rollback limits.

## Permission boundary

The SSH identity does not have unrestricted or passwordless sudo. Deployment
currently needs an attended operator approval. A future one-hour deployment lease
must be root-issued, bounded, revocable and scoped to the installed release
controller; no arbitrary commands, unit editing or credential access.

The historical `stocks-debug-access` package was prepared but not installed. It
grants diagnostic/sync starts, **not deployment**. Its archived sources are not
an active permission grant. Discover installed capabilities before suggesting
commands.

## Filesystem contract

- Active source: only `~/code/stocks` on each machine.
- Durable commands: maintained in this repository; an installed launcher may point
  to reviewed code. No new one-off `~/stocks-*` scripts or permanent deployment
  trees under `~/.local`.
- Private development DB/backups: one explicitly configured private location,
  separate from tracked source; preserve last verified rollback copies.
- Task staging: one bounded scratch location, recorded in a cleanup manifest;
  remove it after verified publish, including transient broker-key staging.
- Retired unique code/docs: verified compressed archives plus manifest outside
  `~/code`, private mode, marked historical. Keep Git refs/bundle and dirty patches
  before retiring old worktrees. Never blindly discard unmerged work.
- Production `/opt/stocks`, `/etc/stocks`, `/var/lib/stocks*` and
  `/var/backups/stocks` are **not temp files**. Preserve deployed release/recovery
  state, credential files, auth/browser state, portfolio data and backups.
- Cleanup must not restart services, change schedules or delete unrelated projects.

## Current operational references

Use [simple-release.md](simple-release.md) for the installed code-only controller,
[trading212-service-sync.md](trading212-service-sync.md) for its dedicated worker
and policy gate, and [public-hosting.md](public-hosting.md) for host security.
Inspect actual installed units and current release before acting. Old upgrade or
cutover procedures are not interchangeable with the installed controller.
