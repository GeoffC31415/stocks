# Sync reliability and isolated preview operator notes

## Status contract (schema version 2)

`GET /api/sync/status` preserves `accounts`, `last_snapshot_date`, `age_days`,
`stale`, `last_run`, `running`, and both enable flags. It adds `next_run_at`
(UTC ISO timestamp or null) and a human-readable `schedule`. The next elapse is
read from the fixed `stocks-sync.timer`, including systemd's randomized delay,
only when service-trigger support is enabled; null is unknown, not an estimate.

`last_run` and the CLI JSON retain `started_at`, `finished_at`, `invocation_id`,
`ok`, `steps`, and `files`, and add:

- `schema_version: 2`.
- `outcome`: `complete`, `partial`, `failed`, `no_op`, or `disabled`.
- `freshness[provider][section]`, with providers `Barclays`,
  `Hargreaves Lansdown`, and `Trading 212`, and sections `holdings`, `orders`,
  `cash`, or `transactions`.
- Each section has `last_attempt_at`, `verified_at`, `valuation_at`, `coverage`,
  `status`, `reason_code`, and `action_code`. Public `steps[].sections` uses this
  same sanitized section metadata; private CLI steps retain current-run results.

An attempt is published before awaiting a provider. Only an explicit successful,
validated and committed broker section advances `verified_at`; an unchanged
broker check is a new observation, not a new import batch. `valuation_at` is the
provider observation/valuation date, not the latest attempt. A failure preserves
prior verification and valuation. `coverage` describes that retained verified
observation when no new verification occurred; consult current `status` and
`reason_code` as well. A missing prior verification remains null/unknown.

A duplicate local file is *not* a verified broker check. An empty inbox is
`no_op`, not verified unchanged. Disabled/unconfigured brokers are not failures.
Rejected files, failed checks, incomplete required sections, and post-commit
archive/acknowledgment failures require attention. The aggregate is `partial`
when useful work coexists with a failure; otherwise `failed`. CLI exits 1 for
both, even when another broker succeeded. Terminal reports are finalized during
cancellation too. Publication failure is itself reported, and does not abort
independent providers; if the filesystem cannot be written, no persisted
terminal report can be guaranteed (the returned/CLI report still fails).

Safe reason codes are enumerated in `sync_freshness.py`; examples include
`verified_changed`, `verified_unchanged`, `provider_failed`, `not_verified`,
`disabled`, and `partial_coverage`. Actions are `none`, `retry`, `configure`, or
`operator_review`. Public reports strip filenames, source paths, error text,
unknown fields/codes, credentials and values. UTC timestamps and valuation dates
are validated. Legacy reports are readable but cannot invent historical checks.

## Durability and transaction boundaries

Provenance uses the worker-owned `last-sync.json`, not a new DB table. Version 2
is retained across runs under the stable worker lock; old versions have no
verified observation until a real check. Atomic publication writes a private
same-directory temporary file, fsyncs it, replaces the destination, and fsyncs
the directory. Public status is separately sanitized and mode 0640. No database
migration or live data change is needed for these source artifacts.

Inbox scans, reads, imports and archives are isolated. A post-commit archive
failure is `committed_with_attention`, never a rollback claim. Same-day snapshots
compare the latest canonical account batch, not all historical hashes, so
A -> B -> A -> A restores A once and then becomes unchanged. Failed payloads
are not inserted into the per-run deduplication set.

Whole broker operations are bounded by `sync_runner.FETCH_TIMEOUT_SECONDS`
(default 300 seconds), including pair import. Integrity-worker Trading 212
client integration owns the tighter `runtime_budget` constructor parameter
(default 180 seconds), injected monotonic `clock`, per-request `timeout`, and
bounded retry/pagination handling. Do not create a second client/retry layer.
The runner lazily accepts `hl_sync_service.FetchedHLPair(holdings, orders,
observed_at)` and calls its `import_pair(session, holdings, orders, as_of=...)`
exactly once; both halves stay out of the unpaired inbox. The integrity-worker
helper/parser/fetcher changes must be merged before a staged HL run. A source-only
scratch overlay of the parent integrity implementation plus these service files
passed 44 combined tests, including the real runner/helper commit-and-unchanged
integration and the helper's cancellation rollback tests. The helper is not
copied into this commit; `test_sync_hl_integration.py` skips until it is merged.

## Review-only operator policy and effective schedule

`deploy/stocks-sync-operator.rules` is a *separate* start-only Geoff grant. It
allows exactly `(geoff, org.freedesktop.systemd1.manage-units,
stocks-sync.service, start)`. Synthetic negative tests cover other users,
`manage-unit-files`, other units, and other verbs. It neither replaces nor
expands the existing web-identity policy. No policy was installed and no service
was started/refreshed.

Read-only `systemctl cat/show` confirmed live identities `stocks` and
`stocks-sync`, supplementary group `stocks-data`, separate private state and
mutual inaccessible paths. The effective live timer is **daily 18:30
Europe/London**, with **RandomizedDelaySec=2min** still effective (daily drop-in
on the older weekday base). The source timer now matches that effective daily
schedule. No sandbox directive was weakened.

Installed rule inspection is blocked: `/etc/polkit-1/rules.d` is root:polkitd,
mode 0750, and this ordinary Geoff session cannot list/read/stat entries there.
An empty glob is not evidence of absence. An authorized operator must read the
exact installed rule and verify ownership/content before any policy replacement
or installation. Approval gates remain: privileged policy installation,
deployment/activation, migrations against real data, and any real broker run.

## Safe Trading 212 error diagnostics

Broker failures emit allowlisted `code`, `endpoint`, `phase`, and HTTP status
fields. Scheduled sync logs also include the validated systemd invocation ID.
Raw exception messages, tracebacks, request URLs, provider bodies, account
identifiers and credentials are not emitted by these diagnostic paths. Unknown
errors use `unexpected_error`, rather than formatting arbitrary exception text.
The public sync-status file retains its existing restricted schema.

On the Surface, Geoff already has read access to the service journal; no broker
credential access or new sudo/Polkit grant is needed to diagnose these logs:

```bash
journalctl -u stocks-sync.service --since '2 days ago' --no-pager
systemctl show stocks-sync.service -p InvocationID -p Result -p ExecMainStatus
```

Interpret the fixed codes as follows:

- `account_summary_forbidden`, `endpoint=account_summary`, `http_status=403`:
  the key lacks read-only `account` scope. Enable that scope or replace the key
  in the protected broker configuration through the authorized operator. Never
  grant trading permissions or bypass required cash verification.
- `http_rate_limited`, `http_status=429`: avoid rapid repeated syncs and wait for
  the provider's rate window; do not treat this as an authentication failure.
- `positions_disappeared`: inspect broker evidence and use the explicit reviewed
  closure workflow; never infer automatic approval from missing positions.
- `cash_history_conflict` or `unsupported_cash_transaction_type`: reconcile
  source evidence without editing the ledger or silently dropping transactions.
- `transport_error` or `sync_timeout`: check connectivity/runtime budgets.

Alembic can disable application loggers at startup. The sync CLI explicitly
restores only its safe diagnostic logger after migrations; it does not enable
verbose HTTP or payload logging. These changes take effect only after the code
is released to the running deployment.

## Safe synthetic preview

No production database, broker credentials, authentication store, migration,
normal application lifespan, or external listener is used. The preview creates
an exclusive mode-0600 disposable DB with two explicitly synthetic accounts,
three deterministic snapshot dates, and **zero orders**. It refuses existing
output directories and worktrees containing `.env`/`backend/.env`. The analytical
GET routers are assembled directly, including lazy `_IncludedRouter` expansion
for installed FastAPI 0.141.1; every audited GET route must be present or startup
fails. All writes and provider-refresh routes remain unavailable. Auth/sync
header reads are explicitly synthetic: local authentication and disabled sync,
not a rehearsal of real passkey enrollment.

From an isolated worktree, using the existing shared venv:

```bash
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run build -- --outDir /home/geoff/.hermes/cache/scratch/stocks-preview-dist
/home/geoff/code/stocks/.venv/bin/python scripts/synthetic_preview.py \
  --dist /home/geoff/.hermes/cache/scratch/stocks-preview-dist \
  --output /home/geoff/.hermes/cache/scratch/stocks-preview-review \
  --port 8127
```

Open `http://127.0.0.1:8127`. Stop with Ctrl+C. There is no public exposure or
service installation. To recreate, choose a new output directory rather than
pointing this command at a real DB or overwriting an old fixture.

`verify_analysis_ui.py --zero-events` explicitly substitutes a tested zero-event
order journey for the order-heavy R3 journeys; it does not infer missing orders
as success. Its regular matrix remains separate and may surface unavailable
analytics/fixture prerequisites. Optional `create_app(..., security_config=...,
auth_store=...)` supports a supplied synthetic auth boundary without creating a
production passkey store or running startup migrations. Synthetic Basic auth
challenge/success and read-only mutation refusal are tested.

### Evidence for this source change

- RED tests were observed for aggregation, partial CLI failure, archive/read
  failure, A/B/A/A restoration, persisted provenance, inbox independence,
  cancellation terminal status, section failure, fsync durability, invalid
  status JSON, staged HL acceptance, next-timer lookup, incomplete coverage,
  publication failure, early attempts, and acknowledgment-after-commit.
- Existing frontend build completed after local `npm ci --ignore-scripts`;
  no frontend source files changed. The build warned only about bundle size.
- Real Chrome zero-event journeys passed at 390 and 1440 pixels against the
  loopback preview; the synthetic DB remained byte-identical.
- Full backend run: 1149 passed, two existing missing-private-HL-fixture
  failures (before the final isolated duplicate-validation regression). Those
  private files were not copied or fabricated. Final focused regression counts
  are in the commit report. The full visual browser matrix timed out at 180s;
  this is not full matrix acceptance. Separate real zero-event journeys passed.
- Production activation, installed rule content, real credentials, real broker
  observation and full visual matrix acceptance remain unverified/approval-gated.
