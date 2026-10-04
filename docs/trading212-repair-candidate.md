# Trading 212 repair — master source restored, NOT deployed

## Parent integration evidence

The independently reviewed candidate was integrated into master with all 18 files matching the candidate manifest. The integrated source passed 1,328 backend tests, 266 frontend tests, frontend typecheck and production build. Independent review additionally exercised 104 control/reliability tests, 99 provider/transaction tests and 5 ImportPanel tests, and approved source integration—not production activation.

The exact retained worker bytes are an accepted, narrow formatting exception for compatibility with the installed policy. Existing, baseline-reproduced Ruff/mypy debt is unchanged; no broad quality waiver or clean full-lint pass is claimed. Remote publication and home-script preparation must be verified separately. Owner preview acceptance, protected worker-policy verification and production activation remain outstanding.

The sections below preserve the preparation evidence and gates; references to the detached worktree or uncommitted candidate describe its historical preparation, not an alternative deployment source.

## Source and scope

- Isolated detached worktree: `/home/geoff/code/stocks-t212-repair`.
- Base master: `222b4b45785348d2e9e253e212a120ddb16091fe`.
- No commit/push, sudo, credential access, production DB access or deployment performed. Main source working tree was observed clean and unchanged.
- Retained release used once as recovery evidence: `578d10250d8a8c0de767232f94e35b20986de31b72902755cd47fe078b64739b`. It is NOT a future deployment source.
- Sole release source must be pushed/verified `origin/master`; sole deployment entrypoint is `/home/geoff/deploy-stocks-master`. The parent owns integration and deployment approval. Its fresh `backend/app` export explains why absent master integration cannot survive a release. No historical deployment sequence is inferred beyond the observed source divergence.

## Repair

Recovered dedicated `app.trading212_cli`, authenticated same-origin empty-body `/api/sync/trading212/request` POST/GET, fixed-unit control/status selection and source-owned sanitized provider diagnostics. Shared `sync-run.lock`, invocation correlation and separate public report namespace are retained. No worker migrations, browser fetch, inbox imports or other broker execution.

Frontend preserves master standalone heading, description, Barclays manual upload, import force behavior, classifications and other unrelated features. Public/service mode requests the dedicated worker and polls its terminal status rather than using the forbidden direct provider sync; local mode keeps its existing direct path. Web broker credentials remain absent.

The installed unit's NONSECRET Environment sets `PORTFOLIO_SYNC_STATUS_DIR=/var/lib/stocks-status/trading212` for the dedicated worker. The web consumer uses parent-status-dir + `trading212`. Synthetic producer/consumer tests reflect these separate settings. Do NOT append `trading212` again inside the worker or modify the installed unit to compensate. Worker bytes are exactly retained implementation, SHA256 `5d59610868880114e733142522b277cc00a24952b24c4e80b2c3af2a775dac30`; existing protected policy digest was not read or verified.

## Verification evidence

- RED master integration: four service tests failed (missing module, route404, unsupported controller selector), then40 service/diagnostic tests passed after recovery.
- RED diagnostics:36 tests failed before recovery; all36 passed after.
- Master-export contract: two tests fail on the clean base checkout, pass on candidate (required module and isolated POST/GET).
- Frontend RED public button disabled without web credentials; candidate exercises real api methods and records only dedicated request POST plus status GETs. No direct/all-broker sync.
- Full backend FINAL after all code/assertion/launcher changes: **1328 passed**, one existing synthetic XLS sheet-title warning; log `/home/geoff/.hermes/cache/scratch/t212-final-backend.log`. Final focused repair run: **44 tests passed** (including the constructor-time dotenv safety regression). Coverage includes unauthenticated401, cross/duplicate-Origin403, direct public provider403, no database dependency, fixed unit, shared lock, missing credentials failure and sanitized correlated report. The launcher now disables constructor-time `_read_env_files`, not just `__call__`; a forbidden file-reader spy was observed RED before that correction. Final corrected-launcher smoke separately proved accepted→running→completed and the disposable DB byte-identical; its owned smoke process was stopped.
- Full frontend: **71 files / 266 tests passed**; log `/home/geoff/.hermes/cache/scratch/t212-full-frontend.log`. Final focused ImportPanel:5 passed. `npm --prefix frontend run typecheck` and `npm --prefix frontend run build` passed.
- Ruff:25 errors, byte-identical diagnostics to clean baseline. Mypy:25 errors in6 files, identical error lines to clean baseline (candidate checks86 source files vs85). These are inherited gates, NOT clean passes or waived release requirements.
- Formatting: whole backend baseline87 unformatted files; candidate87. Restored worker is newly present/unformatted and intentionally retained byte-for-byte to avoid unnecessary worker-policy hash drift; recovered provider service removed one old unformatted path. No mass formatting performed. Parent/reviewer must decide the narrow formatting disposition explicitly.
- `git diff --check` passed.
- Real Chrome on built `/data`: button enabled despite configured=false; exactly one synthetic POST to `/api/sync/trading212/request`; accepted→terminal; button re-enabled; no page errors; manual Barclays button present. Desktop screenshot inspected and readable. Mobile390px document width390px, no horizontal overflow; full-page screenshot has existing sticky overlay obscuring manual-upload controls at the captured scroll position. Mobile visual acceptance is not claimed complete; no unrelated UI redesign attempted.

## Synthetic preview

Running loopback server: `http://127.0.0.1:8128/data`.
Process `proc_53cb3f946aad` was explicitly handed to parent; parent owns cleanup.

Preview uses EXCLUSIVE synthetic fixture `/home/geoff/.hermes/cache/scratch/t212-preview-fixture/synthetic.db`, opened read-only by existing audited GET harness. Dedicated POST is a simulated fixture and never invokes worker/systemd/broker/DB writes. All other writes refused. It is a UI preview, NOT host service/auth/provider verification. No real portfolio displayed.

Restart command (choose a NEW output directory; existing fixture directory is refused):

```
/home/geoff/code/stocks/.venv/bin/python /home/geoff/code/stocks-t212-repair/scripts/preview_t212.py --output /home/geoff/.hermes/cache/scratch/t212-preview-NEW --port 8128
```

Screenshots: `/home/geoff/.hermes/cache/scratch/t212-preview-desktop.png`, `/home/geoff/.hermes/cache/scratch/t212-preview-mobile.png`.

## Parent integration / remaining gates

1. Geoff accepts isolated synthetic preview; one scoped independent review of complete changed/new files, frontend transitions and credential-isolation/report paths. Resolve/explicitly disposition baseline quality debt and preserved-worker formatting; do not call all gates clean.
2. Parent integrates candidate files into MASTER only, reruns synthetic backend/frontend checks on integrated source, commits/pushes if authorized and verifies exact `origin/master` SHA. Local-only master is insufficient: home script fetches remote master. Generated preview data/build/dependency links are NOT source changes to integrate.
3. Parent prepares exclusively through `/home/geoff/deploy-stocks-master`; verify freshly exported candidate contains/imports `app.trading212_cli`, isolated routes and built frontend request path before any activation. The new `test_t212_release_contract.py` guards master against the original omission; a home-script preflight may be proposed separately, not changed here.
4. Recheck installed worker/web identity, policy, precise status/control paths and runtime readability with authorized bounded disposable service-identity rehearsal. Existing `/usr/local/sbin/stocks-t212-verify` policy includes worker SHA; unchanged worker should avoid gratuitous drift but actual protected-policy match remains unverified. Do not read credentials, add web broker credentials, alter unit/isolation or use live broker sync as rehearsal.
5. Fresh production approval/native admin attendance and exact home-script activation are parent only. Follow that script's current expected-live safeguards and verify original process exit, exact deployed master source/artifacts, backend/proxy/timer, authenticated owner UI and dedicated request/status behavior after approved deployment. Live broker permission/success is still unknown; credentials were NOT tested. No unapproved schedule catch-up or database changes.
