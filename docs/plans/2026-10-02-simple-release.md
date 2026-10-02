# Simple Stocks Release Implementation Plan

> For Hermes: implement this isolated plan with TDD; use one implementation worker and one independent operational review, not a review swarm. Parent owns live acceptance and closure.

Goal: replace release-specific scripts with a small stable native-systemd operator tool, and safely ship the already-approved b6 application without changing its UI, authentication, database contents or broker scope.
Architecture: one administrator-installed controller, one release bundle/manifest, one locked operation record plus protected log. Provisioning/migration history is preserved but is not an ordinary release prerequisite. A fixed service-identity rehearsal must pass before the running website is stopped.
Tech stack: Python standard library for controller/packaging; existing systemd, Python runtime and application. No Docker/Kubernetes/new network service.

## Scope and boundaries

- Worktree `/home/geoff/code/stocks-simple-release`, branch `feat/simple-release-20261002`, base2a2f5ccc22f9c05da732be5ff736e2af3ef0d7e0. Do not touch other worktrees, private env/DB, old root protocols or interrupted r2 work.
- Source remains approvedb6 for the application. New code goes in `deploy/simple_release/`; tests in `tests/test_simple_release*.py`; operational docs in `docs/simple-release.md`.
- V1 supports code-only releases with equal migration/startup-schema inputs and backward-compatible storage. Unsupported schema/config changes refuse and require a separate migration procedure. Do not edit startup migrations/authentication/application code as a side effect of this release.
- Defer independent proxy-binary lifecycle and broader migration tooling. Restart the actual coupled backend/proxy correctly today; no unit/drop-in/auth changes in routine deploy.
- Human attends for bounded installation/rehearsal/activation approvals, not development. Before18:00 availability is flexible; after18:00 do not assume sustained attendance. All prompts require presence. No standing sudo.
- No historical boot/invocation pins, per-release executable generation, child-attestation chains, hard-coded backend dictionaries, or imported legacy deployment modules. No deletion/rewriting of old incident evidence.

## Operational contract

Illustrative CLI to implement: `prepare`, `inspect`, `adopt`, `deploy`, `status`, `rollback`, `rehearse`. No arbitrary command/SQL/hook option.

`prepare` runs unprivileged against the approved source/runtime bundle and writes a NEW private bundle. Build provenance and bounded manifest list source/artifact hashes, relevant compatibility digests, file types/modes and supported runtime. Release metadata is data, never executable root hooks. Canonical runtime files0644, directories0755, required executables0755; no secrets/state in the bundle; narrowly permitted venv interpreter/lib symlinks or safe materialisation. Do not chmod through external links.

Root-installed stable controller stages approved bundle bytes into a root-owned fixed release store. Verify caller-supplied digest from the trusted approval command, safe names/paths, regular-file/link policy, bounded copy, no overwrite, actual final permissions. Root never imports application code. Interrupted staging is diagnosable and leaves production alone.

One-time `adopt` records trusted current/previous target and stable effective unit/configuration fingerprints after administrator approval. Leave legacy evidence in place, retired as control input. Root-controlled state contains ordinary last-known-good release and operation IDs, not a proof of past process success. Each deploy checks current pointer, stable config, no overlapping operation, and actual present service/scheduler state. Fresh process identity is an in-operation observation only.

Before cutover, fixed `rehearse` starts the root-staged release as stocks and stocks-sync with appropriate UID/GID/groups and sandbox using disposable DB/auth/state, no production EnvFiles, no provider credentials, no production state access, and no outside network. Exercise real uvicorn/watchfiles imports, actual app lifespan, a DB-backed HTTP read and frontend asset. Distinguish matching-sandbox restrictions from mere UID switching. Import-only/geoff/root success is insufficient. A deliberately broken-start fixture must exercise actual failed systemd state and old-fixture restoration without touching live services.

Broker safety: reuse the application's stable sync-run flock and verify effective runner/path; pause timer without changing enable policy; never interrupt an active sync to deploy. Reject a near scheduled run before pausing, use a bounded maintenance window and restore timer only when a missed-run/catch-up cannot occur. If uncertain, restore website but leave scheduler paused and report explicit attention. Avoid adding a new broker scheduler framework; do not trigger a sync as a test.

Cutover: record recovery target and step before mutation, stop writer/web processes cleanly, atomically switch current pointer, start backend AND coupled proxy, check exact process/release, stable service state and HTTP boundary. Do not label401 as authenticated health. If it fails, stop the candidate, prove stopped even if systemd marks failed, narrowly reset the failed flag as needed, restore the independently trusted old release and verify web availability. Recovery does not require the failed candidate to validate, nor automatic DB restoration. Timer restoration is separate from web restoration. Interrupted/ambiguous state: status/reconcile before retry, no repeat deployment or removal of evidence.

Diagnostics: bounded root-private operation log, structured public-safe result with failed phase/unit/status/path/incidentID; no credential values, raw env dumps, private rows or arbitrary provider errors. Preserve useful stderr privately rather than /dev/null. One authoritative operation result, no supervisor certification hierarchy. A long-running systemd-managed operation is preferable to losing work with a terminal; finish with actual process result + independent live readback.

## Task 1 — Bundle and contract (TDD)

Create `deploy/simple_release/stocks_release.py` and `tests/test_simple_release.py`.
Start with `test_prepare_rejects_owner_only_runtime`: construct code file0600 and normalise a NEW bundle, require resulting read mode and unchanged bytes. Then tests for secret/state exclusion, traversal/link escape, wrong digest, existing output, source change during copy and source preservation. Run failing tests, implement minimal bounded safe preparation/staging, rerun. No code generated from manifest fields.

## Task 2 — State, preflight and recovery core (TDD)

Add isolated filesystem/host adapters for tests only. Cover expected-current mismatch, active sync, concurrent operation, failed-but-stopped vs running unit, candidate-start failure restoresold, invalid candidate does not block approved old recovery, scheduler uncertainty does not prevent web restoration, interrupted operation is inspectable and unsafe retry refuses. Exercise fault injection after actual pointer changes, not only mock-before-change. Root controller still requires explicit operator invocation and fixed service scope.

## Task 3 — Fixed real identity/sandbox rehearsal

Create `deploy/simple_release/runtime_probe.py` and `tests/test_simple_release_probe.py`. The probe runs only inside the unprivileged fixed transient unit, with synthetic local configuration. Do not execute app imports asroot. Real subprocess startup/HTTP/schema/asset tests, a corrupt/unreadable package regression, deadline and cleanup. Prepare fixed `systemd-run` unit arguments, environment and masks; show actual actor credentials and fixture paths in nonsecret evidence. Rootless tests do not establish root identity rehearsal; later run the same fixed command with administrator approval while production stays up.

## Task 4 — Small installer and runbook

Create `deploy/simple_release/install.sh` plus explicit root-owned policy defaults/install verification. One-time install is separately pinned/reviewed; future releases use the stable controller and digest, not new bootstrap programs. No sudoers grants. Write `docs/simple-release.md`: exact commands, supported code-only scope, full rehearsal/result interpretation, no implicit catch-up, emergency restoration and how to retire old control state without removing evidence. Build the actual b6-r2 readable artifact; compare application/file content with approved b6 and original runtime; mode/path differences explicit.

## Task 5 — Independent operational review

One reviewer challenges outcomes: real service account access, actual failed-state recovery, file/approval boundary, DB side effects, timer race, useful nonsecret diagnosis. Review the whole exact candidate and operator path. No whole-suite loops for every doc/hash change; focused tests during work, final relevant suite after integration. If implementation grows beyond a small understandable controller, reassess design before adding another layer.

## Task 6 — Attended real rehearsal, then release

Parent verifies source/artifact pins, installs only reviewed tooling afterapproval, rehearses successful and failed starts/restoration using disposable units/data (production remainsup), then activates approvedapplication in a separate explicitbounded action. Observe the original process, read actualpointer/services/schedule, and get owner-session portfolio/passkey smoke. Update concise pickup and report separate preparation/rehearsal/live states. Do not saydone until actualacceptance is verified.

## Development commands

Use `/home/geoff/code/stocks/.venv/bin/python -B -m pytest -c pytest.ini tests/test_simple_release*.py -q` from this worktree with PYTHON_DOTENV_DISABLED=1, PYTHONDONTWRITEBYTECODE=1, explicit PYTHONPATH=backend, synthetic PORTFOLIO_DATABASE_URL and scratch TMPDIR. New tests must not read live env/DB or call live mutating systemctl commands. Shell syntax and scoped Ruff. Git stage/commit exact files only; preserve application identity to b6.
