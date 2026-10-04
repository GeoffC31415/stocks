# Trading 212 service sync

The Data page's **Sync Trading 212** button requests a fixed, isolated systemd
worker in public deployments. It never gives the web process broker credentials,
never accepts a service name or force option, and never places orders.

## Runtime contracts

- Authenticated, same-origin `POST /api/sync/trading212/request`, with no body or
  query arguments. `GET` on the same route polls the correlated request.
- The existing `PORTFOLIO_SYNC_SERVICE_TRIGGER_ENABLED=true` setting enables the
  service controls. Local manual sync retains its existing behavior.
- Unit: `stocks-t212-sync.service`; worker: `python -m app.trading212_cli`.
- Protected environment: `/etc/stocks/trading212.env` (root-owned, mode 0600),
  containing only the Trading 212 API key/secret and the fixed portfolio database
  URL. Account-summary, portfolio, order-history and transaction-history read
  scopes are needed. Trading permissions are not needed.
- The worker uses the existing shared `sync-run.lock`, so it cannot overlap a
  scheduled combined import. It does not start browser fetches, process CSV inbox
  files, or run migrations.
- Worker reports go to `/var/lib/stocks-status/trading212`, readable by the web
  process via `stocks-data`. Request markers live in the web control directory's
  `trading212` subdirectory.
- The polkit rule authorizes only user `stocks` to **start** the exact unit. It
  grants no unit edit, stop, restart, timer or arbitrary-command permission.
- Missing credentials are a failure, not a successful skipped sync. Timeout and
  interruption reports remain terminal where possible. Public reports redact
  private details; logs contain only fixed sanitized diagnostics.

## Verification

Test synthetic systemd commands and request authentication without production
side effects. Rehearse real broker imports using a WAL-aware disposable database
copy before an attended production activation. Deploy via the installed pinned
release controller, preserving its recovery record. Treat any explicit broker
credential rotation as a narrowly reviewed host-policy change; do not discard
controller state or re-adopt a release to bypass policy-drift protections.

After activation, verify all of the following separately:

1. Root-installed code and current release match the pinned revision/bundle.
2. Credentials remain protected and absent from the web process environment.
3. `stocks-t212-sync.service` exits successfully and its new report has only the
   Trading 212 step, no inbox files, and `ok: true`.
4. Authenticated Data-page button requests and polls that service, with matching
   request ID and terminal report. Busy/unknown states must not claim success.
5. A repeat after the provider rate-limit window does not duplicate imports.
6. Scheduled sync configuration and the release controller's rollback metadata
   remain intact. Code rollback does not roll back portfolio data.

The UI waits at most 20 minutes; an unknown UI state is not proof that the worker
failed or stopped. Inspect the exact unit/status instead of blindly retrying.

## Dedicated policy validation and interrupted activation

The original code-only release controller does **not** fingerprint the additional
Trading 212 unit, rule or environment. The attended extension installs a separate
root-only gate. Run it before and after any future release or code rollback:

```sh
sudo /usr/bin/python3 -I /usr/local/sbin/stocks-t212-verify
```

It refuses changed unit/rule/environment/worker content, untrusted ownership or
unreviewed unit drop-ins. If a future change intentionally modifies these files,
review and update the separate pinned policy explicitly; do not weaken or discard
the original release controller's baseline.

Activation fsyncs config files **and their parent directories**. Before rotating
private config it records root-only intended new bytes and an intent record,
while preserving the original release recovery record. If activation stops,
first inspect the code-only controller status and dedicated unit journal. Do not
rerun `--apply`: it intentionally refuses a changed current release or existing
installation.

For an interruption specifically during the recorded config rotation, run the
already verified, root-staged installer with `--recover-policy`, not `--apply`.
It locks both the release operation and shared sync lock, verifies the current
release, original operation, unchanged public unit policy and Caddy config, then
publishes only the exact recorded new broker/production configs and their
verified fingerprint. It does not deploy code, discard rollback records, install
services or start imports. Dedicated activation after that remains an attended
inspection/recovery step. Intended private copies are deleted after successful
live verification; keep failed-operation recovery files root-only.
