# Broker isolation: candidate deployment and recovery runbook

**Not activated.** This change is a migration candidate, not proof that the live
service is isolated. Complete the privileged disposable-host rehearsal and the
integration/permission gates below before approving production activation.
Keep `https://solarpi.hopto.org:5000`, its proxy, and all other services unchanged.
Do not use either legacy installer to activate these unit templates.

## Layout and integration contract

| State | Identity / permissions | Purpose |
|---|---|---|
| `/var/lib/stocks` | stocks:stocks 0700 | Website-private state only |
| `/var/lib/stocks/auth.sqlite3` | stocks:stocks, private ancestor | Website authentication store |
| `/var/lib/stocks/control` | stocks:stocks, private ancestor | Fixed-service trigger markers |
| `/var/lib/stocks-sync` | stocks-sync:stocks-sync 0700 | Worker HOME, browser, inbox, downloads |
| `/var/lib/stocks-data` | root:stocks-data 2770 | Shared portfolio database |
| `portfolio.db` inside shared data | stocks:stocks-data 0660 | Both services may write; UMask=0007 preserves writable WAL/SHM |
| `/var/lib/stocks-status` | stocks-sync:stocks 2750 | Worker writes, web only reads sanitized status |
| `last-sync.json` inside status | inherited stocks group, 0640 | Allowlisted report, no raw provider exceptions |
| `/etc/stocks/{production,brokers}.env` | root-owned 0600 | Read by systemd, not by either service user |

The unit adds only supplementary `stocks-data`. Neither identity may belong to
the other's private group. Shared portfolio access is intentional: this is broker
credential isolation, not read-only portfolio access or protection from a worker
altering portfolio data.

Web environment: `PORTFOLIO_DEPLOYMENT_MODE=public`,
`PORTFOLIO_AUTH_MODE=basic`,
`PORTFOLIO_AUTH_DATABASE_PATH=/var/lib/stocks/auth.sqlite3`,
`PORTFOLIO_SYNC_CONTROL_DIR=/var/lib/stocks/control`, and
`PORTFOLIO_SYNC_SERVICE_TRIGGER_ENABLED=false` initially.
The auth settings are implemented by the separate passkey-backend change; merge
and test that change before deployment. **Do not switch to passkey mode before
real owner enrollment and recovery have been verified.**

Both services receive
`PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:////var/lib/stocks-data/portfolio.db` and
`PORTFOLIO_SYNC_STATUS_DIR=/var/lib/stocks-status`. Worker receives only broker
configuration plus its own paths and local deployment mode, never website auth
settings. The web does not read the worker inbox. Local development preserves
existing inbox/status defaults and direct broker routes; public direct broker
routes return 403 before DB/provider dependencies.

## Safe development checks (no credentials, portfolio, or network)

From the checkout, using an existing development interpreter:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHON_DOTENV_DISABLED=1 \
PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: PYTHONPATH=backend \
/home/geoff/code/stocks-security/.venv/bin/python -B -c '
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files = lambda self: {}
import pytest
raise SystemExit(pytest.main([
  "backend/tests/test_broker_isolation.py",
  "backend/tests/test_isolation_deploy.py",
  "backend/tests/test_isolation_migration.py",
  "backend/tests/test_isolation_host.py",
  "backend/tests/test_isolation_completion.py",
  "backend/tests/test_passkey_cutover.py",
  "backend/tests/test_sync_control.py", "-q", "-p", "no:cacheprovider"]))'
bash -n deploy/install-surface.sh deploy/upgrade-surface.sh
systemd-analyze verify deploy/stocks.service deploy/stocks-sync.service deploy/stocks-sync.timer
python3 deploy/broker_isolation.py --help
```

Tests use disposable SQLite/WAL trees and mocked host commands. They do not prove
actual Linux users, mount namespaces, browser compatibility, or live permissions.
The full suite has known unrelated missing-private-fixture, FastAPI lazy-route,
and installed-service preflight failures; do not bypass the installer safeguards.

## Preparation and mandatory review gates

1. Stage a complete immutable release in `/opt/stocks/releases/RELEASE`, with a
   system-interpreter venv (not a `/home` symlink), built frontend, backend auth
   integration, migrations, and these templates. Never copy `.env`, portfolios,
   inboxes, or profiles into code. Review root ownership and non-writability of
   release, `/opt/stocks`, `/etc/stocks`, and `/var/backups/stocks` ancestors.
2. Inventory *effective* service configuration and all systemd drop-ins. Reject
   overrides of users/groups, env, state paths, sandbox, ExecStart, or UMask.
   Template verification alone does not detect every unsafe inherited override.
   Ensure no cron/manual/other service can restart a writer during migration.
3. Rehearse activation and rollback on a disposable root-capable host with mock
   brokers. The helper is host-guarded for `geoff-Surface-Pro-4`; tests exercise
   its filesystem adapters rather than changing that production guard.
4. Review strict environment parsing privately. Unknown keys, duplicate keys
   across files, expansion, escaping, or multiline syntax fail closed. Do not
   print values or source either file. Resolve ambiguity manually, retaining
   root-only originals. Existing auth mode must be Basic; nonstandard old paths
   require a separate reviewed migration.
5. Ensure all relevant state is on the same filesystem as the private recovery
   bundle. Profile symlinks, hardlinks, sockets, and other special files are
   refused, including stale browser lock symlinks: review them offline after
   stopping browser processes; never automatically follow or delete them.
6. Validate SQLite read/write and WAL creation as both service identities in the
   disposable rehearsal, including file recreation in both orders. Validate
   denied access to the opposite state/env, raw profile exports and old backups.
   Test inside the effective systemd mount namespace as well as DAC. Auth DB and
   its sidecars must remain under the web-private directory. No real provider
   login is part of smoke tests.

## Explicit operator commands (not run by this development task)

Run from an approved interactive root terminal only after all gates pass. Replace
NEW and OLD with exact installed release names. `preflight` is the read-only dry
run; it reads existing config without printing values and changes no service.

```sh
python3 /opt/stocks/releases/NEW/deploy/broker_isolation.py preflight \
  --release /opt/stocks/releases/NEW --expect-current /opt/stocks/releases/OLD
python3 /opt/stocks/releases/NEW/deploy/broker_isolation.py activate \
  --release /opt/stocks/releases/NEW --expect-current /opt/stocks/releases/OLD \
  --confirm ISOLATE
```

Activation records timer enabled/active state, root-only originals and hashes,
then disables the timer, stops web/worker, and rejects surviving service-UID
processes or open state descriptors. SQLite backup uses exclusive creation and
integrity checking. The entire former state tree (including unknown old browser
backups) is quarantined beneath the root-only bundle. Only the exact supported
browser/inbox and auth store are restored to their new owners. Installed files
are read back; DAC probes and systemd syntax checks must pass. Only web is started.
The HTTP/HTTPS smoke check verifies **401 and service stability only**, not DB
health, authenticated rendering, enrollment, or broker success.

Record the printed `/var/backups/stocks/isolation-...` recovery bundle path.
After activation independently inspect effective units, permissions, namespace
access, safe authenticated reads, and local dashboards. No broad polkit/sudo
permission is installed. Enable the web trigger only after reviewing the existing
fixed `stocks-sync.service` start permission and exercising it with a mock worker.

**The timer stays disabled even after success or rollback.** Restore its saved state **before final passkey-only cutover**, after isolation and authenticated application verification plus separate approval for a possible broker catch-up. The one-off resume helper verifies the Basic migration configuration; once cutover intentionally changes that configuration it refuses drift. Do not weaken that check. If scheduling is intentionally left disabled at cutover, a separately reviewed resumption procedure is required.

Resuming a `Persistent=true` timer may immediately execute a missed broker job. This is a
separate authorized action, not a smoke test. When ready:

```sh
python3 /opt/stocks/releases/NEW/deploy/broker_isolation.py resume-timer \
  --bundle /var/backups/stocks/isolation-BUNDLE --confirm RESUME-SCHEDULE
```

This restores the saved enabled/active state, not an unconditional enable/start.
Review catch-up behavior before running it. The migration never starts a browser
login directly and does not silently restore a previously active worker.

## Failure and rollback

Do not rerun activation blindly. Preserve the marker, bundle, current state, unit
files, and logs privately. Caught transition failures attempt to stop services;
if stop fails, the error explicitly leaves service state unconfirmed. Independently
inspect it rather than assuming isolation. There is no automatic rollback across
potentially changed schemas. Unknown partial transitions fail closed.

Completion uses a strict v2 `transition.json` candidate, not an activation-complete
or rollback-complete authorization marker. A candidate alone cannot authorize
schedule restoration or cutover: each consumer holds the shared lock, validates
release/configuration coherence, and freshly checks boot, web InvocationID,
effective units, service state and the anonymous boundary. Resume requires a
quiescent timer; cutover requires its verified saved state and an inactive worker.
Legacy/malformed/unknown records require manual recovery, never marker editing
or automatic upgrade. See completion-state semantics (historical document archived outside this repository; see documentation archive note) for
publication, interruption, lock and recovery limits.

```sh
python3 /opt/stocks/releases/NEW/deploy/broker_isolation.py rollback \
  --bundle /var/backups/stocks/isolation-BUNDLE --confirm RESTORE-PRE-MIGRATION
```

**This explicitly restores pre-migration data**, not the latest migrated DB. It
first stops services and quarantines *all current* web/worker/shared/status state
under `bundle/evidence`, and current config under `bundle/rollback-config`.
It validates saved config hashes, restores old state/config/units/release as a
coherent set, and restarts web only if previously active. Post-migration edits,
auth enrollment, sessions and broker changes remain in evidence, never silently
overwritten or discarded. Reconcile those offline before deciding which dataset
to serve. For a failure with accepted post-migration edits, prefer keeping the
site stopped while selecting a recovery strategy; this rollback is not a
latest-data merge. A second/partial rollback is refused for manual review.

A completed rollback leaves its marker and evidence in place, so a normal activation
continues to refuse a rerun. After correcting the cause and reviewing the preserved
rollback, a new release may explicitly supersede only that exact verified rollback:

```sh
python3 /opt/stocks/releases/NEW/deploy/broker_isolation.py preflight \
  --release /opt/stocks/releases/NEW --expect-current /opt/stocks/releases/OLD \
  --supersede-rollback-bundle /var/backups/stocks/isolation-ROLLED-BACK
python3 /opt/stocks/releases/NEW/deploy/broker_isolation.py activate \
  --release /opt/stocks/releases/NEW --expect-current /opt/stocks/releases/OLD \
  --supersede-rollback-bundle /var/backups/stocks/isolation-ROLLED-BACK \
  --confirm ISOLATE
```

The helper requires the installed marker, terminal verified rollback record, restored
release/configuration/state, and matching prior release. It records both sides of the
supersession and atomically replaces the marker; malformed, incomplete, drifted or
already-superseded evidence refuses. Never delete or hand-edit a marker to retry.

Do not merely repoint `/opt/stocks/current`: schema, environment, identities and
state layouts must move together. Do not delete recovery bundles or isolation
markers until independently verified recovery and an approved retention decision.
Legacy install/upgrade activation deliberately fails, including as root; a future
isolated-layout upgrader is required for subsequent unattended releases.
