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

## T04 — Responsive containers and reachable controls

Grid children now shrink within their tracks; Holdings and Orders expose named,
keyboard-focusable horizontal scroll regions with visible instructions. Controls
wrap rather than being hidden at the root. History/workspace/account tabs wrap,
workspace arrow/Home/End navigation preserves query parameters and reveals focus.
The threshold popover is bounded on mobile. No root overflow-hiding rule was added.

The expanded isolated harness ran **80 checks, zero failures**: seven routes with
normal and synthetic long unbroken security/account names at 320/390/768/1440px,
plus 720 CSS pixels at device scale 2 (1440px desktop/200%-zoom equivalent). Empty
and failed summary fixtures were tested at all five widths. The fixtures alter
browser responses only, preserve numerical values/IDs, and cannot write the DB.
All documents stay within their viewport; chart accuracy checks remain green;
**966 visible control-focus checks** passed. All three history-chart tabs were
activated by keyboard. The original/copy data remained read-only; no page errors
or unexpected API failures. Expected injected 503s are explicitly distinguished.

Full gates: **254 backend tests**, **74 frontend tests**, frontend typecheck pass.
New backend fixture test is ruff-clean; inherited backend static debt is unchanged.
Two screenshots (mobile Holdings, desktop Overview) were image-inspected: the
intentional table scrolling is visible and the chart losses descend. This is
limited inspection, not complete contrast/visual acceptance. The dashboard is
still too tall and its old hero trend/duplicate summaries remain T10 work.
Screenshot capture now resets focus/scroll after interaction checks so fixed
navigation is captured at the top, not midway down a full-page focus screenshot.

## T05 — Surfaces and typography

Added semantic surface/text/border/radius/spacing tokens. Existing `.glass`
analytical cards now use solid surfaces rather than pervasive blur; overlays keep
an explicit separate treatment. `MetricCard` and `SectionHeader` provide named
semantic layouts. `StatCard` is a small compatibility adapter, so its consumers
migrate together without copying financial logic. Primary labels are 14px,
metadata 12px, and hero balance 36–44px. Header/secondary contrast was increased;
card glows and hover lift were removed. The hero's misleading trend source is
still explicitly pending T10, rather than silently relabelled in a styling task.

Verification: frontend **77 tests / 27 files**, frontend typecheck, build and diff
checks pass. The expanded **80 browser checks pass**. Computed foreground versus
opaque background contrast on migrated metric-card text has minimum **6.76:1**;
no migrated card has backdrop blur. A rendered synthetic fixture verifies that
the contrast check rejects insufficient contrast (rather than passing on absent
cards). These measurements are not a claim that every legacy chart label or
classification row has passed a full accessibility audit. Desktop Overview and
mobile Holdings images were inspected after resetting capture scroll/focus;
solid surfaces and improved labels are visible, without new document overflow.

## T06 — Formats, colours and chart primitives

Formatting regressions first exposed missing values rendered as £0 and invalid
dates rendered as “Invalid Date”. Shared formatters now distinguish missing/zero,
suppress negative zero, retain existing whole-pound display rounding, and offer
exact pennies and compact £250k/£1m axes. Dates are UTC. Exact formatting never
feeds calculations. Shared chart tooltip/legend components replace repeated
markup in the history/instrument/performance charts; tooltips show exact GBP or
explicit index units rather than silently mixing them.

Allocation colours are keyed to dimension/category identity; sorting/filtering
cannot recolour surviving categories. Unclassified stays amber. Donut centre now
shows invested value instead of a second HHI headline. Table headings match the
dimension, swatches match the sectors, numeric columns align right, and a
keyboard/touch button exposes exact amounts. Generic diversification implications
were removed from the concentration description; legal-security aggregation and
look-through remain T15/D04.

Verification: **254 backend / 85 frontend tests**, frontend typecheck/build pass.
All **80 browser checks pass**, including cycling every allocation dimension,
checking actual SVG slice colours against table swatches, and toggling exact
values at every width with long-name fixtures. Geometry/contrast checks remain
green. No static backend or database changes in this slice.

## T07 — Definitions, motion and focus

The new HeroKpi test first failed on its invented £0 count-up starting value.
Hero now renders the final amount synchronously, including updates. Shared
`MetricInfo` popovers use named buttons/dialogs, explicit context, bounded viewport
placement and focus return. A central glossary covers Dietz, estimated
money-weighted return, CAGR, volatility/ratios, drawdown, HHI and the DRIP proxy.
Performance, return, allocation and Income definitions use it.

Added skip-to-main, visible focus, reduced-motion ambient/route/selection handling,
and route-heading focus that does not steal active input or back-navigation focus.
Route focus waits for loaded headings instead of focusing an old exiting route.

Verification: **254 backend / 90 frontend tests**, frontend typecheck/build pass;
**80 browser cases pass**, now including Enter/Space activation, Escape and close
focus return, outside-pointer dismissal, mobile touch activation, popover bounds,
skip-link focus and computed reduced-motion animation checks. Backend diagnostic
identity comparison still has **101 inherited ruff / 32 inherited mypy errors,
zero new identities**. Original SQLite and verified backup SHA-256 hashes match
the starting manifest. All builds targeted `/tmp/stocks-experience-dist`, never
the ignored live-served output; no deployment/restart/provider refresh occurred.

Remaining release tasks are tracked only in the implementation plan. This is
verification evidence, not a second progress ledger. R1–R3 are not released.

## T08 — URL-first analysis scope

Account and performance period now come from the URL, with validated stored
preferences used only for missing defaults. Defaults are materialised into the
current history entry; explicit selections and workspace tabs push history so
Back/Forward restores the investigation. Primary navigation and legacy redirects
retain encoded identifiers and unrelated filters. Unknown accounts, repeated
scope parameters, malformed dates and unsupported custom dates show an explicit
invalid-scope state instead of silently broadening the analysis. Custom dates
remain disabled; transaction date filters retain their separate meaning.

Performance and the portfolio return card include account/period in query keys
and API requests. Both resolve the period relative to the latest valuation,
not wall-clock time. The existing performance contract exposes requested and
effective dates, account valuation dates and coverage warnings. API validation
returns 422 for unsupported/ambiguous scope and reversed explicit return dates.
Current snapshots, lifetime holding returns, latest snapshot comparisons,
transaction filters and today-based Income explicitly disclose their exceptions.
The Topbar no longer labels a selected account with another account's latest
date; authoritative selected-account freshness remains the T09 deliverable.
DRIP threshold editing moved to Data → Analysis settings, with the proxy
qualification and a scoped link back to Income.

Safety: a new consistent SQLite online backup was created and integrity/logical
contents verified outside the repository before DB-related work. Tests use
synthetic in-memory databases without application lifespan. The original DB's
SHA-256 is unchanged; the rehearsal report confirms its read-only copy is
unchanged. No schema migration, personal-data edit, provider refresh, installation,
service restart or deployment was performed.

Evidence:
- RED: the new API regression selection initially returned **9 semantic failures,
  1 pass**: invalid scope was ignored or produced 500, and the return card ignored
  the requested period. Fixture setup was corrected before recording that result.
- `.venv/bin/pytest -q`: **264 passed**.
- `npm --prefix frontend test -- --run`: **104 passed** in 35 files, including
  encoded account/identifier preservation, invalid/custom dates, URL precedence,
  history restoration, contextual settings and removal of old plotted metrics
  while another account/period request is pending.
- `npm --prefix frontend run typecheck`: passed.
- `make lint` / `make typecheck`: still **101 inherited ruff / 32 inherited mypy**
  diagnostics; filename/code/message identity comparison found **zero new**.
- Isolated build: `/tmp/stocks-t08-dist`; live `frontend/dist` was not overwritten.
- Expanded isolated browser harness: **80 cases, 0 failures** at
  320/390/720/768/1440px. At 390/1440px it additionally changes period/account,
  verifies response scope and URL agreement, and exercises Back/Forward.
  Evidence and screenshots: `/tmp/stocks-t08-ui`. An initial desktop test used
  an accessibility locator for a deliberately hidden mobile select; the fixture
  locator was corrected, then the complete matrix rerun successfully.
- Screenshots captured; image/manual visual approval remains outstanding.

Review: URL parsing is isolated from financial services; backend remains the
source of period dates and calculations. No new financial calculation was added
in React. Scope controls reuse existing preferences and tabs rather than adding
another state store or UI framework. New implementation modules remain under
110 lines; the API type/client file only gains the additive period parameter.
T09–T23 and the deferred extensions remain unchecked and unimplemented here.
