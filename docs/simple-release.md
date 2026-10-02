# Stocks simple release — candidate for one operational review

**PREPARED, NOT DEPLOYED.** No administrator installation, real service-account
systemd rehearsal, production mutation or authenticated owner acceptance has been
performed by this implementation worker. Those gates belong to the parent/operator.
The restored old site and legacy incident records must remain untouched during review.

## What this version does

One stable, root-installed standard-library controller; release manifests are data.
Commands: `prepare`, `inspect`, `adopt`, `rehearse`, `deploy`, `status`, `rollback`.
No hooks, arbitrary command/SQL options, generated controller, supervisor, standing
sudo rule, database restoration, provider smoke, unit rewriting or historical proof chain.

V1 is **code-only**. The complete Alembic tree and exact main/database/models/config/
passkeys/security/requirements-production.txt/Caddyfile bytes must match the trusted
current release. The sync CLI `_run` and `file_lock` function **bodies**, excluding
annotations/comments, must also match. The approved old and b6 releases satisfy this.
Changing a startup-schema input refuses; introducing migrations or changing proxy
lifecycle needs a separate reviewed procedure. This does not claim arbitrary future
application changes are storage-compatible: review those changes before approving a digest.

The coupled backend/proxy are both stopped and explicitly started. Production verification
requires stable PIDs, process executable/release paths, zero restarts and TLS `/api/health`
**401**. That is an anonymous authentication boundary, **not authenticated health**.
Owner-session portfolio/passkey checks remain mandatory after activation.

## Frozen artifact and provenance

- Approved application: `b6b43113a6d1be7e40472d27baa22a7c31b8116b`.
- Read-only original: `/home/geoff/.local/share/stocks-release-ready/20261001-b6b4311/release`.
- Original manifest SHA256: `d1a3092b38c7b4929a4fefc4d5ba7b05daeb709d6865fc395594f123f60815c9`.
- **New bundle:** `/home/geoff/.local/share/stocks-release-ready/simple-20261002-b6-r3`.
- **New manifest SHA256:** `4c9c2d60bf202c524fbfb7874ec279ffd8acb174794e5789720dc3e1e250180b`.
- All 4,247 inventory entries retained: 3,768 regular files, 475 directories, four
  fixed venv links. Regular-file bytes total 319,197,758. Every regular-file hash
  matches both original bytes and the original manifest; no application content changes.
- 2,059 regular-file mode changes: new modes are 3,743 files0644 and 25 files0755.
  Original modes included 1,990 files0600 and 53 files0711. Directories0755; venv bin
  regular files and Caddy0755; other regular files0644. Bundle container0700.
- Links are only `.venv/bin/python -> /usr/bin/python3`, python3/python3.14 -> python,
  and `.venv/lib64 -> lib`. Never chmod through a link. Supported runtime CPython3.14.4.
- Earlier **simple** r1/r2 preparation artifacts are superseded, not operator inputs.
  They are unrelated to, and do not supersede, the protected interrupted legacy r2 work.

`prepare` is unprivileged and never edits its source. Bounded descriptor reads and a
trusted manifest digest protect admission: no traversal, arbitrary links, special files,
state/secret paths, overwrite or unbounded copy. Limits: 20,000 entries, 256MiB/file,
1GiB total, 8MiB manifest. Root stages under `/opt/stocks/simple-releases/DIGEST`;
partial staging is retained and a mismatch refuses. Actual root ownership and readable,
non-app-writable permissions are checked before cutover, not inferred from manifest modes.

For historical old-release adoption, inventory only the actual Python/Caddy/frontend-dist
runtime, excluding its unused frontend node_modules and release-era deployment scripts.
Do not interpret that as approval to execute legacy scripts. New bundle admission checks
its **entire** inventory. The controller never imports application or legacy deployment code.

## Verification already exercised without privilege

`tests-review.log` and `tests-review.xml` beside the new bundle: **50 passed in11.16s**.
Scoped Ruff and `bash -n` passed. The application tree remains equal to approved b6.

The tests exercise actual filesystem pointer publication followed by injected failure,
compensation, corrupt-candidate-independent rollback, interrupted status/retry refusal,
shared flock exclusion, active-worker refusal, timeout stderr retention, failed-but-stopped
PID/cgroup logic, schema guards, mode checks, manifest limits and source-change checks.
They read real public systemd properties, including typed empty hook arrays, but never
mutate real units or read private configuration/database contents.

Real CPython3.14.4 uvicorn/watchfiles startup, app lifespan/Alembic, disposable SQLite,
`GET /api/portfolio/summary` and an exact frontend asset passed inside rootless bwrap.
Corrupt-watchfiles and deliberate broken startup failed as expected. This runs as
**Geoff UID1000**, with isolated filesystem/network, **not stocks/stocks-sync**.
The unchanged installed old runtime imports successfully as nonowner; the failed
installed b6 runtime still reproduces watchfiles `PermissionError`. Neither was modified.

Reproduce relevant tests from this worktree:

```sh
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend \
PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: \
TMPDIR=/home/geoff/.hermes/cache/scratch \
/home/geoff/code/stocks/.venv/bin/python -B -m pytest -c pytest.ini \
  tests/test_simple_release.py tests/test_simple_release_probe.py tests/test_simple_release_operational.py -q
```

These integration tests intentionally use this host's public old runtime and the above
prepared bundle; they are not generic CI fixtures and do not claim privileged coverage.
The previously passing full application suite was not rerun for tooling-only changes.

## One independent review, then attended installation

Review the complete controller, probe, installer, tests and this runbook together. Focus
on real UID/groups and path traversal, root-copy authority, failed-unit cleanup, clock/timer
races, schema side effects and useful private diagnostics. Do not add a review swarm.
The controller/probe include the small operational-review corrections below; no imported old deployment
framework. Any correction changes the tool pins and needs the same review refreshed.

Current tool SHA256 pins:

| File | SHA256 |
|---|---|
| stocks_release.py | `620cd9d3b4850210dba39c36a66e69a3d81ec6c969a03db941527bceafa94561` |
| runtime_probe.py | `8e2b3e683963bbe124687919cf92052dd5e757eb94e87736bf3e3d04c0c0cefa` |
| install.sh | `3e70f2b82a22ffb3892216fbad0dac6ef2d1de2ed5088ef034180b68dec5256e` |

**Do not run the following until independent review and explicit administrator approval.**
Approval must bind these literal trusted pins, not hashes freshly read from mutable files.
This one-time bootstrap reads the pinned installer bytes into memory, then runs those bytes;
the installer likewise verifies and installs the controller/probe bytes it actually read.
It creates only the new tool/store/state paths and a CLI symlink, no units or sudoers.
It refuses existing/partial installations rather than overwriting them.

```sh
sudo /usr/bin/python3 -I -c '
import hashlib, os, stat, subprocess
p="/home/geoff/code/stocks-simple-release/deploy/simple_release/install.sh"
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
with os.fdopen(fd,"rb") as f:
    s=os.fstat(f.fileno())
    if not stat.S_ISREG(s.st_mode) or s.st_size>32768: raise SystemExit("installer type/size")
    b=f.read(32769)
if hashlib.sha256(b).hexdigest()!="3e70f2b82a22ffb3892216fbad0dac6ef2d1de2ed5088ef034180b68dec5256e": raise SystemExit("installer pin")
raise SystemExit(subprocess.run(["/bin/bash","-s","--",
"/home/geoff/code/stocks-simple-release/deploy/simple_release",
"620cd9d3b4850210dba39c36a66e69a3d81ec6c969a03db941527bceafa94561",
"8e2b3e683963bbe124687919cf92052dd5e757eb94e87736bf3e3d04c0c0cefa"],
input=b,env={"PATH":"/usr/bin:/bin","LANG":"C"},check=False).returncode)
'
```

Administrator must read back installed hashes/owners/modes before proceeding.
Stable executable: `/usr/local/sbin/stocks-release`, code `/usr/local/lib/stocks-release`.
State root `/var/lib/stocks-release` is0711 to permit service identities to traverse to
individual0700 disposable fixtures; state/log files are0600. No secret values are emitted.
Root commands refuse when invoked from app-source rather than the installed controller.

## Attended real rehearsal: production stays up

```sh
sudo /usr/local/sbin/stocks-release rehearse \
  --bundle /home/geoff/.local/share/stocks-release-ready/simple-20261002-b6-r3 \
  --digest 4c9c2d60bf202c524fbfb7874ec279ffd8acb174794e5789720dc3e1e250180b
```

The fixed native transient units run as `stocks` and `stocks-sync`, with primary groups
and `SupplementaryGroups=stocks-data`, no capabilities, NoNewPrivileges, private network,
ProtectHome/ProtectSystem and explicit production config/state/backup masks. No production
EnvironmentFile is used. The fixed probe independently checks identity/groups/capabilities
and loopback-only network. Its child environment contains only synthetic local configuration. PrivatePIDs/PrivateIPC
and an empty read-only /run exclude host process and IPC authority. A fresh host pathname
socket canary remains listening during each actual native probe; the probe must fail to
connect with ENOENT and prove a different PID namespace plus a private procfs view
before application code runs. This is tested with both reachable/shared negative controls.
Real startup migrations run **only against disposable DBs** in owned fixture directories.

A copied disposable runtime has watchfiles changed to0600 (never the approved runtime).
Only a disposable `rehearsal/recovery-ID/current` pointer moves to it. Its actual systemd
unit must reach failed/exit-code/1 with PermissionError; zero MainPID/ControlPID and empty
cgroup are required before exact reset-failed. The pointer is restored to the healthy
fixture and real startup runs again. Records, logs and disposable DBs remain for review.
Successful oneshot units use RemainAfterExit to retain inspectable process results, then
are explicitly stopped. Failed or ambiguous rehearsal refuses before any production stop.

**Pending empirical gate:** parent must execute this exact systemd sandbox on the host,
verify UID997/GID980 and UID995/GID979 plus stocks-data, actual good/failed/restored results,
unit collection behavior, path masks and absence of production DB/provider access. Rootless
results and mocked systemd tests are not substitutes. Do not proceed if this gate fails.

## Adopt once; activate separately

Adoption observes the current immutable runtime, actual process/release/HTTPS boundary,
root-owned configuration and stable unit policy. It records that current target as its
initial last-known-good. Legacy incident/current/v3-rollback objects are **not consumed,
rewritten, deleted or used as executable authority**. No metadata attestations are chained.

```sh
sudo /usr/local/sbin/stocks-release adopt \
  --expected-current /opt/stocks/releases/stocks-passkeys-31590ff
sudo /usr/local/sbin/stocks-release status
```

Adopt/deploy require the existing daily18:30 Europe/London timer, enabled, with2min
randomized delay, and a safe pre-run window. The effective worker must remain exactly
`python -m app.sync_cli --only barclays`; no HL/provider scope changes are made.
The root-approved private configuration is fingerprinted without outputting values.
A missing, changed or busy existing `sync-run.lock` refuses; the controller never replaces
that inode or creates a root-owned substitute in the inbox.

For attended activation, a systemd-managed operator process survives terminal loss. Parent
must retain and observe this original invocation/exit; never infer success from a marker
alone. Use the unique name below once, not a blind retry:

```sh
sudo /usr/bin/systemd-run --unit=stocks-release-operation-20261002 \
  --wait --property=Type=exec --property=RuntimeMaxSec=20min \
  --property=StandardOutput=journal --property=StandardError=journal \
  /usr/local/sbin/stocks-release deploy \
  --bundle /home/geoff/.local/share/stocks-release-ready/simple-20261002-b6-r3 \
  --digest 4c9c2d60bf202c524fbfb7874ec279ffd8acb174794e5789720dc3e1e250180b \
  --expected-current /opt/stocks/releases/stocks-passkeys-31590ff
sudo /usr/local/sbin/stocks-release status
```

Deploy rechecks current/policy/compatibility, repeats rehearsal, then rechecks before
pausing. It holds both its operation flock and the installed CLI's existing sync-run flock.
An active worker refuses and is **never killed**. It pauses the timer without changing enable
policy and saves the recovery target/phase before stopping either web unit or publishing.
The maintenance deadline is300s and safely before the earliest unrandomized next run;
publication after that window refuses and triggers old-web recovery. Individual commands
are bounded. Web recovery is allowed to outlast the scheduler window: availability first,
no forced timer restart. Clock jump/reboot/expired window/uncertain timer => leave paused.
There is no implicit catch-up and no broker run as a test.

## Outcome, diagnosis and emergency code rollback

- Exit0: requested operation completed; for deploy, independently read back pointer,
  backend/proxy PIDs, stable states, timer and owner-session checks before saying live.
- Exit2 / `restored`: candidate failed; old web verified restored. **Not deployed**.
- Exit3 / `attention`: inspect recorded current target and failed phase; timer may be
  paused or web restoration unconfirmed. Do not assume either is healthy.
- Exit1, signal, timeout or missing process result: inspect original operator unit and
  `status`; do not launch another deploy. `running`/`attention` blocks ordinary retries.

One authoritative `/var/lib/stocks-release/state.json` contains the current operation,
last-known-good and failure phase/unit/log path. Root-private operation logs are bounded
at8MiB and preserve stderr (including timeout partial output); public JSON excludes raw env,
private rows and provider errors. Exact failed transient/production flags are cleared only
after stopped proof, never blanket `reset-failed`. Legacy logs/markers are left intact.

To recover an interrupted deployment, inspect `status`, use its exact operation ID and
**currently observed** pointer. The following is a template requiring those two observed
values, not a command to run with guessed substitutions:

```sh
sudo /usr/local/sbin/stocks-release rollback \
  --operation EXACT_ID_FROM_STATUS --expected-current EXACT_OBSERVED_POINTER
sudo /usr/local/sbin/stocks-release status
```

Rollback validates only the independently recorded old release and stable host policy,
not a broken candidate, then stops/proves candidate processes, restores the pointer and
starts both web units. It never restores a database. Scheduler restoration is separately
conditional; if unsafe it remains paused and reports attention. Do not enable/start the
timer manually to clear attention without a separate explicit missed-run/catch-up decision.
No force, marker deletion, re-adopt-to-bypass, private DB edit or legacy rollback command.

## Remaining gates

1. One independent operational review of the exact committed candidate and literal pins.
2. Attended pinned installation and actual service-identity success/failure/restore rehearsal.
3. Fresh bounded activation approval; original process exit and independent live readback.
4. Owner authenticated portfolio/passkey acceptance. Before18:00 availability is useful;
   do not assume continuous operator attendance after18:00 or start an investigation then.

## Operational review corrections (review refresh pending)

R1: native rehearsal now has PrivatePIDs=yes, PrivateIPC=yes and
TemporaryFileSystem=/run:ro. The actual nonroot native probe verifies PID namespace/procfs
isolation and a negative live-host pathname-socket canary, without connecting to the real
system bus. Disposable rootless negative controls independently prove that the same check
rejects a visible host socket or shared PID namespace. No rootless claim substitutes for
the actual installed service-identity gate.

R2: timer restoration rechecks its boot/wall/monotonic window AFTER blocking observations
and immediately before start, reserving20s for bounded start/readbacks within the already
conservative saved deadline. Start, timer readback and worker readback use5s bounds. Full
timer policy/next-run and worker quiescence are read back; uncertainty attempts timer stop
and leaves attention, never a worker kill or catch-up approval.

R3: backend/proxy start happens once, then readiness polls to a60s monotonic deadline with
bounded observations. Wrong release/executable fails immediately; delayed HTTP readiness
can succeed without restarting units. Exhaustion remains a real failure and compensation
uses the same bounded wait for the known-good release.

Parent observed timer late-start/budget tests RED (2 failures), readiness RED (1 failure),
and missing native socket/PID controls RED (4 failures), then GREEN after local fixes.
Exact final suite/results are retained in the parent correction evidence; no privileged
installation/rehearsal or production mutation performed during these corrections.
