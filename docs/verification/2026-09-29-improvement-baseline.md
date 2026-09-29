# UI/service improvement implementation baseline

## Scope and authorization

User approved implementing the saved plan in the stocks checkout. Production activation, host policy installation, and live broker refreshes remain separate approvals. No live credentials or database permissions are widened. Original unrelated dirty Barclays documentation is preserved.

Implementation branch: `feat/ui-service-improvements-20260929`.
Original checkout: `77160ef876db6bce8317d227e46678e7b1fe45cf`.
Reconciled source baseline: `076f76c` (descendant of original checkout, includes deployed passkeys, isolation and isolated upgrade tooling).
Live pointer at discovery: `/opt/stocks/releases/stocks-passkeys-31590ff`.

Source reconciliation used existing reviewed repository history rather than copying arbitrary production files. Deployed auth changes in backend config/main/security/passkeys/auth routes, sync-origin controls, frontend AuthProvider/AuthGate/API/Topbar and auth screens are retained.

## Effective runner, read-only discovery

- `stocks.service`: user/group stocks, supplementary stocks-data, loopback 127.0.0.1:8000, `/opt/stocks/current`, production environment path only inspected, no environment contents read.
- `stocks-sync.service`: user/group stocks-sync, supplementary stocks-data, isolated inbox/browser, brokers environment path only inspected, 15 minute timeout, CLI under current release.
- Web cannot read broker home; sync cannot read web home; narrow shared data/status paths retained.
- Timer base is weekday18:30 Europe/London, overridden to daily18:30; randomized delay2min remains effective. Neither enabled timer nor exit0 proves observation freshness.
- App and sync timer active at discovery. No service action executed.

## Reproducible preimplementation checks

Main checkout pinned dependencies were synchronized: missing Python webauthn2.8.0 installed in development venv, frontend npm ci. This did not alter live release dependencies.

- Backend full suite: **1105 passed,16 failed,1 warning**. Failures reproduce before feature implementation: absent private HL CSV fixtures (2), raw route introspection incompatible with installed FastAPI (portfolio returns, snapshot attribution, rehearsal), legacy installer tests contaminated by host isolation guard (10), Barclays cancellation test loses in-memory tables on connection replacement (1).
- Frontend typecheck: pass.
- Frontend full suite: **212 passed,1 failed** across62 files. Recovery secret-leakage assertion serializes undefined Node localStorage; must repair deterministic test environment rather than waive security assertion.
- Production frontend build: pass, isolated scratch output. Initial JS **1090.20kB**, gzip **321.69kB**, CSS43.32kB; Vite chunk warning recorded.
- Ruff:29 existing findings.
- Mypy:28 findings in initial run, including3 missing-webauthn imports before dependency synchronization; rerun required after dependencies and changes. Existing type issues are not automatically waived for release.

Full machine-readable tool outputs and isolated baseline dist: `/home/geoff/.hermes/cache/scratch/stocks-improvement-baseline/`. Private evidence stays outside Git. Logs can expire and are not a durable release attestation.

## Data and evidence limits

No production database was read or copied. Work uses synthetic in-memory/on-disk fixtures with explicit no-broker-network boundaries. Financial acceptance against an operator-approved consistent read-only production snapshot remains a separate gate. Historical development data is not asserted representative of current production.

Before completion, reconcile every A1–E5 task, integrate separately committed worktrees, run independent spec then quality review, rerun tests and full-route browser geometry/screenshots against an isolated fixture, and record pending live approvals honestly.
