# Deployment completion-state redesign implementation plan

> **For Hermes:** Use subagent-driven-development with strict TDD and independent specification then security review. The user approved this focused redesign; no live execution is authorized.

**Goal:** Remove cleanup-dependent completion authorization. Stale evidence from a failed or interrupted transition must not, by itself, permit broker scheduling or passkey cutover.

**Architecture:** A single strict versioned transition record identifies a candidate, not an authorization. Consumers independently validate matching filesystem configuration and fresh running-service identity before any mutation. A caught transition failure attempts stop; a later consumer refuses stopped, restarted, rebooted, drifted, or ambiguous state. No cleanup flag deletion is needed for safety.

**Tech stack:** Python stdlib, pytest, synthetic files and mocked host adapters. No new dependencies.

## Scope and decisions

Baseline: 84cb56d in /home/geoff/code/stocks-completion-work. This includes the previously reviewed cutover owner check and schedule-order documentation. Do not edit other worktrees or live systems.

The design exploration is /tmp/stocks-completion-redesign-plan.md. This implementation plan deliberately narrows its suggestions to the completion defect: do not add full executable-release inventory machinery, automatic authenticated-login/namespace tooling, or a permanently refusing readiness stub. Existing immutable release staging, actual namespace checks, authenticated owner health checks, and separate schedule catch-up approval remain mandatory operational gates; current anonymous boundary health checks must never be relabeled authenticated verification.

### Core invariants

- No legacy completion/pending marker authorizes a new-format operation. Reject missing/unknown/ambiguous format; no automatic evidence upgrade.
- Immutable versioned manifest and installed marker bind one bundle/transition ID. The mutable strict transition record binds manifest digest, phase, stage, and, for a verified candidate, observed boot and web InvocationID plus effective-unit fingerprint. Record phase preparation before mutating transition state.
- Publish through an exclusive same-directory temporary file, flush/file-fsync/close, atomic replace, directory-fsync, metadata/content readback. Never delete the authoritative candidate as a safety mechanism after failure. Preserve private evidence; diagnostic errors must not reveal secrets.
- A verified candidate is only eligibility for fresh checks. Use existing release/configuration coherence checks with independently saved hashes and owner/path checks; retain immutable staging as an explicit prerequisite rather than inventing a new deployment system.
- Consumers require fresh active/stable web with matching boot and InvocationID, unchanged effective unit configuration, inactive worker and quiescent timer where applicable, and bounded existing read-only health checks. Unknown/missing probe values refuse. Recheck identity/coherence immediately before mutations. Never start/reload/repair the web service to satisfy readiness.
- A failed transition that stops web cannot pass resume/cutover. A manually restarted web cannot inherit old eligibility. If failure cleanup itself fails but all independently checked current state is safe, a later explicitly approved operation is a new readiness decision, not a declaration that the old process succeeded. This limit must be documented honestly.
- Shared root-controlled advisory locking serializes cooperating activation/rollback/resume/cutover commands. It cannot protect against unrelated privileged administrators; retain operational exclusion of other writers. Validate lock path/owner/mode and reject contention.
- Rollback preparation overrides prior activation eligibility before layout mutation. Successfully verified rollback may supersede failed activation without deleting evidence. Restored inactive web is not resume-ready.
- Resume remains explicitly approved, never automatic, and restores saved enabled/active state with readback. Failure during timer mutation attempts safe stop/disable and reports unconfirmed cleanup honestly. Never promise to undo a job already triggered.
- Cutover consumes the same validated activation context, under the same lock; no separate marker-only path. Preserve recent real passkey authentication, owner checks, private backups, no automatic Basic restoration, and second preflight. Cutover can run after explicitly restored timer state; therefore define consumer-specific timer readiness rather than making the documented order impossible.

## Task 1 — Reproduce the failure (RED)

Files: backend/tests/test_isolation_migration.py, backend/tests/test_isolation_host.py.

Use actual pending unlink followed by KeyboardInterrupt and failed completion invalidation for both phases. Model actual service state in FakeSystem: stop changes readiness. Feed persisted evidence to a fresh consumer; assert zero timer-mutating commands. Keep a legacy-refusal regression when the obsolete writer is removed.

## Task 2 — Implement the state model (vertical RED/GREEN slices)

Files: deploy/broker_isolation.py, new backend/tests/test_isolation_completion.py, migration tests.

Implement strict parsing, manifest binding, candidate publisher and phase selection. Test corrupt/truncated/duplicate JSON, wrong schema/types, unsafe metadata/links, missing evidence, preparation states, rollback supersession. Test failures before and AFTER real replace/fsync/close/return boundaries; do not replace real operations with only pre-operation exceptions. Preserve private recovery evidence without cleanup-dependent authorization.

## Task 3 — Wire transition and resume safety

Files: deploy/broker_isolation.py and migration/host tests.

Implement shared lock, durable preparing/candidate transitions, consistent stop-unconfirmed handling, fresh readiness and pre-mutation recheck. Test stopped/restarted/rebooted services, effective configuration drift, unavailable probes, active worker, unexpected timer activity, interruption during checks, lock contention, timer mutation/readback/cleanup failures. All host commands mocked. Successful cases must use explicit coherent evidence, not a universal mock returning active/true.

## Task 4 — Update passkey consumer in the same candidate

Files: deploy/passkey_cutover.py, backend/tests/test_passkey_cutover.py.

Replace legacy completion checks with shared selection/readiness/lock. Test legacy refusal before writes, interrupted-transition/stopped-web refusal, rollback mismatch, changed identity, second-preflight drift, and the intended schedule-before-cutover flow. Retain all existing passkey/TLS/ownership/recovery regressions.

## Task 5 — Audit, documentation and reviews

Files: docs/broker-isolation.md, docs/passkey-cutover.md, new docs/completion-state.md if useful.

Search all completion consumers. Explain candidate vs authorization, visibility vs durability, limits under SIGKILL/power loss/storage failure, v1 refusal/manual recovery, lock scope and live gates. No claim of deployment readiness from mocks. Run relevant suites, scoped Ruff and diff check. Commit only reviewed-scope files. Parent will independently inspect/test, then obtain SPEC and security reviews before integration.

## Safe execution

Use /home/geoff/code/stocks-security/.venv/bin/python -B (already installed, production-equivalent interpreter). Run as non-root. Set PYTHONDONTWRITEBYTECODE=1, PYTHON_DOTENV_DISABLED=1, PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory:. Before importing application modules set pydantic_settings.sources.DotEnvSettingsSource._read_env_files = lambda self: {}. Use pytest -q -p no:cacheprovider and only synthetic fixtures. Existing CLI --help/unprivileged-refusal test has been inspected and can run as non-root; no privileged/service/broker invocation is permitted.

Required suites: test_isolation_completion.py, test_isolation_migration.py, test_isolation_host.py, test_isolation_deploy.py, test_broker_isolation.py, test_passkey_cutover.py; expand relevant sync/rehearsal regression after these pass. Report actual RED and GREEN outputs and exact scope; do not inherit previous counts.
