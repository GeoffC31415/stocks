# Portfolio experience verification

## T00 — Safe baseline

Implementation branch: `feature/portfolio-experience`, starting at `fa34371`.
The starting working tree was clean (the plan's dirty-tree warning is historical).
No pre-existing modified/untracked files were present. Tracked-file SHA-256
manifest and complete diagnostics are in private evidence outside the repository.

### Safety

- `portfolio.db` and `portfolio.db.bak` both pass `git check-ignore`.
- SQLite online backup created outside the repository in a mode-0700 directory.
  Read-only source transaction, backup `integrity_check = ok`, complete logical
  dump equality, and unchanged source SHA-256 verified before implementation.
- Test fixtures inspected: module-local in-memory engines; HTTPX ASGI transports
  do not run lifespan. Baseline commands additionally set
  `PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory:`.
- `app.main` lifespan runs migrations. The rehearsal instead builds a separate
  app from audited GET routes, with its **own read-only dependency provider**;
  no copied original lifespan. Mutation methods are rejected server-side and
  browser requests are restricted by route-specific GET allowlists.
- Provider GETs/refreshes are not allowed. Offline font CSS uses system fonts;
  comparisons therefore do not claim identical typography to the historical review.
- Child failure detection, readiness deadline, terminate/kill cleanup and copied
  DB hash preservation are tested. No installation, live restart, migration,
  provider refresh, personal-data edit or deployment occurred.

### Fresh initial gates

| Command | Observed result |
|---|---|
| `.venv/bin/pytest -q` | 229 passed |
| `npm --prefix frontend test -- --run` | 59 passed, 23 files |
| `npm --prefix frontend run typecheck` | passed |
| `make lint` | inherited: 101 ruff diagnostics |
| `make typecheck` | inherited: 32 errors in 7 files |
| `npm --prefix frontend run build -- --outDir /tmp/stocks-experience-dist` | passed; existing large-chunk warning |

Full ruff JSON (path/code/message/location) and mypy diagnostics are retained
privately for identity comparisons, not merely count comparisons. `make check`
was not used because it runs mutating formatting. Live `frontend/dist` untouched.

### Reproduced defects (not passes)

`test_invalid_common_chain_cannot_publish_a_curve_or_drawdown` failed semantically:
a duplicate-date input gives an unavailable cumulative KPI but a nonempty partial
curve. Temporarily strict-xfailed for T01, not counted as a passing acceptance test.
The rendered synthetic SVG fixture detects repeated/overlapping date labels and
inverted losses. Six harness safety/geometry tests pass.

The isolated browser command ran all seven routes at 320/390/768/1440px. It
**exited nonzero: 11 of 28 route/width combinations failed**, retaining all
measurements/screenshots instead of stopping at the first defect. Required API
responses and content headings were observed on all routes; no API/page errors.

| Route | 320px document | 390px document | 768px document | 1440px document |
|---|---:|---:|---:|---:|
| Overview | 320 | 390 | 768 | 1440 |
| Holdings | 900 | 900 | 908 | 1440 |
| Income | 524 | 524 | 768 | 1440 |
| Orders | 620 | 620 | 768 | 1440 |
| Allocation | 320 | 390 | 768 | 1440 |
| Returns | 320 | 390 | 768 | 1440 |
| Classifications | 320 | 390 | 768 | 1440 |

Overview reproduces invalid performance with a published curve, duplicate and
overlapping ticks, and inverted drawdown at all widths; clipped controls at
320/390px. Default height: 3478px desktop, 5825px at 390px. Performance heading:
y=1110.5 desktop, y=1707.5 at 390px. These are a new offline-font baseline.
Screenshots captured; image/manual visual acceptance is **outstanding**.
Numerical correctness and successful geometry checks are separate claims.

### Reproduction

```sh
PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  .venv/bin/pytest backend/tests/test_experience_contracts.py backend/tests/test_ui_rehearsal.py -q
npm --prefix frontend run build -- --outDir /tmp/stocks-experience-dist
.venv/bin/python scripts/verify_analysis_ui.py \
  --database /path/to/verified-private-backup.db \
  --dist /tmp/stocks-experience-dist --output /tmp/stocks-experience-ui
```

Private evidence location for this session is recorded in
`/tmp/stocks-experience-evidence-path`; do not commit its contents or screenshots.
## T01 — Canonical dates and common validity

Regression tests first failed for duplicate same-day states, a backfill replacing
current value, and another account's imports creating phantom observations.
The strict T00 xfail was removed after its semantic assertion passed.

Shared `valuation_service.py` now replaces touched account snapshots in
(date, import ID) order, consolidates each date, and carries untouched accounts
forward. Current snapshots, raw timeseries, performance and the boundary Dietz
summary use it. Allocation inherits corrected current state (including stable
value/ID ordering); all allocation goldens pass. Existing explicit closed flags
remain honoured by current-position consumers. Snapshot attribution retains its
distinct batch-ID boundary semantics; its tests still pass, and period-aware
comparison improvements remain T12, not silently included here.

KPI/index share full-precision chain endpoints; duplicate/non-increasing dates,
missing/non-finite values, unusable denominators and numerical overflow invalidate
the common chain. Primary drawdown never falls back to raw values. True terminal
loss remains -100%; one return interval no longer claims zero volatility.
Structured per-metric metadata distinguishes short annualisation, insufficient
intervals, undefined ratios and invalid chains. Scope discloses account valuation
dates and carry-forward/coverage warnings. Missing flow queries are null, not zero.
Python metadata is mirrored in `frontend/src/lib/api.ts`; nullable flow display is
safe pending T02's full status migration.

Verification: full backend **253 passed**; full frontend **59 passed**;
frontend typecheck passed. Ruff/mypy diagnostic identities compared with T00:
no new identities after fixing the one introduced dict-style diagnostic. New
services are small and single-purpose; portfolio service shrank by removing
three duplicate reconstruction loops. `git diff --check` passed. UI geometry is
not claimed fixed by this backend change. No schema migration/deployment.

## T02 — Truthful UI states

The two new PerformancePanel tests first failed because unavailable metadata
was ignored and short-window reasons were hidden. They now pass: metadata wins
over populated legacy curves/numbers; broken chains suppress adjusted plots and
drawdown; short annualisation alone leaves cumulative performance visible.
`AnalysisStatus` exposes reasons, actual supplied repair links and fetch-error-only
retry actions. All six performance metrics have per-metric unavailable reasons;
method, observed period, sampling, coverage warnings and backend notes are visible.
Generic typical ranges/ratings were removed. Definitions now use keyboard/touch
native disclosure instead of inaccessible hover-only text (T07 will unify these).

Overview tests distinguish pending, fetch failure, successful empty selection,
empty selected account, valid dated zero balance and partial secondary failures.
Summary/return fetch failures do not become welcome/import prompts or stale numbers.
Account aggregate rebuilding remains explicitly T09; this task only prevents it
from publishing a zero balance when its instrument query fails or is pending.

Verification: full backend **253 passed**; frontend **69 passed in 25 files**;
frontend typecheck and diff whitespace check passed. No backend/static changes in
this slice. Chart geometry and compact dashboard budgets remain T03/T10. No live
build, database or service was changed.

## T03 — Snapshot chart geometry

`performanceChart.ts` joins named series without duplicate timestamps or
punctuation-based benchmark-key collisions. Missing values are not replaced with
zero. Sparse ticks use available pixel/calendar distance, date formatting is UTC,
index extent includes 100 and extrema, and snapshot lines are linear with visible
observation dots. The reversed drawdown axis is removed. Unavailable adjusted
chains remain suppressed; raw values require explicit opt-in and do not connect
across missing observations.

Verification: full frontend **73 passed in 26 files**, frontend typecheck passed;
harness safety/geometry **6 passed**. Isolated build succeeded at
`/tmp/stocks-experience-dist` (existing chunk-size warning). The 28-view browser
rehearsal now finds **no duplicate/overlapping date ticks, inverted drawdown, missing
observation markers or clipped observation extents at any width**. It measured
15 actual performance observation dots and four drawdown ticks at each width.
Nine route/width combinations still fail on T04's known overflow/clipped-control
issues, so the overall browser command correctly remains nonzero. Screenshots
captured; visual styling acceptance still outstanding, not inferred from geometry.

Remaining release tasks are tracked only in the implementation plan. This is
verification evidence, not a second progress ledger. R1–R3 are not released.
