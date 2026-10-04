# Backend test trim audit

Base: `f475bf38f81e4a6610081eb0b0b48625f72dee32`. Preparation occurred in a detached worktree; the parent then integrated the reviewed changes into master. Backend changes are confined to `backend/tests` and this document. Production code, configuration, scripts, shared JSON fixtures and deployment remain unchanged. Independent review approved the partial trim plus all six obsolete module deletions and found no consequential coverage or dangling-import blockers.

**Status: integrated trim, not deployed.** Parent integrated both candidate patches into master and removed the six obsolete test modules through the normal main-session Git operation. The complete retained backend suite passed **982 tests, zero failures/skips, in 103.62 seconds** (JUnit103.602s). Compared with the measured1,328-test baseline at178.06s, this removes346 cases and observed74.44s (41.8%). The final run overlapped the frontend check, so timings remain observations, not statistically controlled guarantees. Independent source review and remote publication are separate gates.

## Measured comparison

Same interpreter, synthetic launcher, worktree and command, one baseline and one
final full backend run, with `--durations=40` and JUnit. No xdist or new mocks.

| Run | Passed | Failed / skipped | Pytest elapsed | JUnit suite time |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 1328 | 0 / 0 | 178.06 s | 177.681 s |
| Retained partial suite | 1235 | 0 / 0 | 154.87 s | 154.835 s |

93 collected cases removed (7.0%); observed elapsed saving 23.19 s (13.0%).
Single-run timings include load/cache variance: they are observations, not a
promised speedup. Both runs retain the same openpyxl long-sheet-title warning.

Reproduce from the repository root:

```sh
TMPDIR=/home/geoff/.hermes/cache/scratch \
/home/geoff/code/stocks/.venv/bin/python scripts/test_t212_synthetic.py \
  backend/tests -q --durations=40 --junitxml=RESULT.xml
```

The launcher clears inherited `PORTFOLIO_*`, forces an in-memory application DB,
and disables dotenv reads before configuration construction. Individual existing
file-backed tests use disposable synthetic databases. No credentials, provider
requests, live database or service mutations were used.

## Removed repetitions → retained failure signals

| Changed test module | Cases before → after | Removed → retained risk mapping |
| --- | ---: | --- |
| `test_matching_engine` | 26 → 14 | Literal normalization, similarity identity and method-label assertions; duplicate closed-instrument helper tests → numeric share-class/type boundaries, score thresholds/account distinction, real alias/manual/ignored/dry-run behavior, closed-instrument API regression and repeat alias resolution. |
| `test_performance_service` | 32 → 22 | Repeated pure-contribution/curve/monotonic drawdown checks and vague positive-gain assertions → hand-calculated Dietz interval/withdrawal/real-gain curve, risk metrics, payload behavior; independent performance regressions, return API, cash-flow integration and drawdown episodes unchanged. |
| `test_risk_service` | 33 → 28 | Separate NaN check, duplicate missing-date alignment, same-input/same-output and weak finite/survival checks → nonfinite engine rejection, actual aligned dates, covariance/Euler/cash/benchmark/degenerate boundaries; dated-FX/risk API regressions unchanged. |
| `test_cgt_service` | 32 → 29 | Ordinary March/January dates and repeated case-insensitive ISA example → exact 5/6 April boundary, same-day/30-day/pool matching, exemptions/losses and exempt-account aggregation. |
| `test_market_data_service` | 22 → 20 | Fixture copies of provider rows and a second missing-adjusted-close variant → missing-adjusted-close behavior, cache/upsert/refresh failures, source currency/GBP conversion, coverage and no-provider cache regression. |
| `test_deployment_tools` | 5 → 2 | Three setup-invalid-input repetitions → actual private hashed configuration, overwrite refusal and consistent WAL backup/missing-source behavior. This helper remains documented, so it was not deleted wholesale. Public startup validation remains in web tests. |
| `test_quality_owner_boundaries` | 27 → 20 | Preview × rejection product, simultaneous name+number change, duplicate empty collection examples → all four stale/wrong valuation rejections at apply, valid preview AND apply with writer exclusion, independent name/number/ambiguity/pin/alias boundaries and hostile public-report values. |
| `test_trading212` | 48 → 43 | Negative infinity, duplicate malformed fill-ID types and false boolean example → NaN/infinity, empty/non-scalar ID, true boolean, exact money/source currency mapping, missing cash/403 completeness, all pagination guards and routes. |
| `test_trading212_budget` | 18 → 15 | Repeated nonfinite retry header and nonpositive/nonfinite budgets → NaN, negative/header encoding/size, zero, excessive and boolean budget boundaries; wall-clock/shared deadline/retry tests untouched. |
| `test_trading212_transactions` | 8 → 6 | Middle fetch-method copies → first/last network failures with zero SQL/commits, fetch-before-write concurrency, reused-ID rollback, single physical commit and permission-denial tests. |
| `test_ui_rehearsal` | 8 → 5 | Fixture self-comparison, synthetic geometry-copy assertions and extra named-scroll browser rehearsal → real rendered tick geometry negative control, isolated read-only DB, browser allowlist and startup/deadline tests. |
| `test_web_security` | 150 → 112 | Unsafe-method × origin Cartesian product (42 → 12), duplicate protected route/peer/deep-link examples → every unsafe method, every origin category, route classes, IPv4/IPv6/mapped/non-IP peers; all passkey, crypto, authority, body-limit, traversal, cancellation, throttling, security-header and broker-boundary tests retained. |

No parametrizations were combined into loops to manufacture lower test counts.
The origin matrix and closure matrix remove redundant combinations, not distinct
boundary assertions. Fixtures shared with frontend tests are unchanged.

## Obsolete risk vs current high-risk coverage

The following six obsolete modules were removed by the parent after reviewing the relevance evidence below. Native tool approval blocked the child's attempt, so the child correctly delivered only a tested partial patch; that historical refusal was not counted as a deletion or saving:

- `test_isolation_completion.py`, `test_isolation_host.py`,
  `test_isolation_migration.py`, `test_isolation_probe_schema.py`;
- `test_passkey_cutover.py`, `test_surface_installer.py`.

They account for 253 baseline cases and 58.157 s summed JUnit case time (not a
measured post-removal saving). Their cross-imports form a legacy test-helper
cluster; no remaining application imports depend on it. Source/runtime relevance
was traced rather than inferred from security labels:

- `docs/simple-release.md` explicitly records completed one-time setup and says
  not to rerun it. The current `deploy/simple_release/stocks_release.py` uses
  standard-library imports, not `broker_isolation.py` or `passkey_cutover.py`.
- Legacy `deploy/install-surface.sh` and `deploy/upgrade-surface.sh` immediately
  refuse install/upgrade/activate before their old provisioning logic. Their bulk
  installer help/path/provisioning tests are not normal future-release coverage.
- Legacy migration/resume/supersession schema/identity matrices are obsolete
  operational authority, not application financial/auth behavior. Their removal
  would not imply permission to execute those legacy commands.

Compact current protection already remains: `test_isolation_deploy.py` tests
legacy activation refusal and isolated unit identities; `test_broker_isolation.py`,
`test_sync_deploy_artifacts.py`, `test_sync_policy.py`, `test_t212_service.py` and
`test_t212_release_contract.py` cover current web/worker/control boundaries.
`test_deployment_database.py` and `test_cash_flow_migration.py` are deliberately
retained: application startup migrations, DB URL override/percent/out-of-repo
resolution, SQLite pragmas and actual ledger schema/data preservation are still
live risks. Current simple-release tests under root `tests/` are outside this
backend-only edit/run and were not claimed as reverified.

## Retained-test negative controls

A disposable pytest plugin outside the repository injected runtime mutants while
exercising existing retained tests (production files never edited):

| Mutant | Retained test | Observed failure |
| --- | --- | --- |
| Missing `app.trading212_cli` module lookup | `test_master_export_contains_installed_worker_entrypoint` | Installed worker entrypoint assertion. |
| Remove dedicated request/status routes | `test_master_exports_isolated_request_and_status_routes` | Missing POST route assertion. |
| Multiply GBP values by 100 | `test_positions_to_rows_maps_primary_currency_values_and_cash` | 19500 != 195. |
| Treat EUR summary as GBP | `test_positions_to_rows_rejects_non_gbp_account` | Currency rejection did not raise. |
| Physical commit immediately after snapshot | `test_diagnostic_annotation_cannot_prevent_owner_rollback` | Persisted ImportBatch count 1 != 0. |
| Accept every Basic credential | `test_public_all_routes_require_basic_auth` | Six protected-route cases fail (e.g. 200 != 401). |

All six final mutants were killed by assertion failures, with no collection/setup
errors. Earlier exploratory rollback/join-mode mutants survived the chosen
fetch-failure test, which fails before writes; that is NOT credited as rollback
coverage. The final premature physical commit is checked against the real
late-import rollback test. Final unmutated full suite passed afterwards/alongside
these process-isolated probes. Changed modules also pass scoped Ruff F401 and
`git diff --check`.

Evidence outside Git: `backend-trim-before.{log,xml}`,
`backend-trim-after.{log,xml}`, `backend-trim-mutant-*.{log,xml}` and
`backend_trim_mutants.py`, under `/home/geoff/.hermes/cache/scratch`.
