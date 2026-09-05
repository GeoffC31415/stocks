# Portfolio Experience and Insight Implementation Plan

> **For Hermes:** Use the `subagent-driven-development` skill to implement this plan task-by-task, with RED → GREEN → REFACTOR and independent spec/quality review. Keep bounded implementation slices under parent control; do not dispatch the whole project as one unattended task.

**Goal:** Turn Stocks into a compact, attractive, trustworthy portfolio briefing that explains what changed, why, how reliable the result is, and where to investigate.

**Architecture:** FastAPI owns financial calculations, account/date scope, canonical security identity, and availability metadata. React renders typed results through shared design/chart primitives and URL-backed investigation state. Preserve separate actual snapshot performance, order-derived estimates, and current-composition market-data proxies; never silently substitute one for another.

**Tech stack:** Existing FastAPI, Pydantic v2, async SQLAlchemy, SQLite/Alembic, NumPy, pytest, React 19, TypeScript, TanStack Query, React Router, Tailwind, Recharts, Framer Motion, Vitest/Testing Library, and local Chrome/Playwright. No new UI/chart framework is required.

**Repository:** `/home/geoff/code/stocks`.

**Status:** Implementation in progress on `feature/portfolio-experience`; see task evidence below. This is the single replacement for the former root-level improvement plan and progress ledger. Existing code is a starting point, not proof that any acceptance criterion below has passed.

---

## 1. Scope, starting evidence, and guardrails

### What already exists

Do not rebuild these as if absent: workspace/mobile navigation; account filtering; instrument deep links; order date filters; allocation donut and backend allocation endpoint; classification coverage; snapshot attribution; chain-linked Dietz code; raw-value chart toggle; DRIP-proxy Income page; market-price/FX cache models; and a partially implemented risk service.

The working tree on 2026-09-04 is dirty on `feature/analysis-risk-forecast`. Preserve all existing changes, including untracked service/tests and the intentional deletion of the old browser allocation calculator. Never reset, clean, stash, or commit the entire tree merely to start this plan.

### Review evidence, not an evergreen baseline

The preceding review inspected source, live read-only API responses, and seven routes at 1440px and 390px:

- Dashboard: approximately 3494px high at desktop, 5857px at mobile; Performance began around y=1111 on desktop.
- Mobile document widths: Holdings 943px, Income 551px, Orders 652px in a 390px viewport. Dashboard width passed but a chart tab was clipped outside its card.
- Performance: duplicate-date axis labels occupied the same coordinates; negative drawdown ticks appeared above zero.
- Live performance API: complete flow-adjusted return unavailable, with an unusable-interval note, but an adjusted curve and drawdown still published. The UI hid the explanatory note.
- Combined allocation listed the same EQQQ security as separate account positions.
- Live risk response: 0% covered non-cash value, zero aligned observations; current gate is 80% and 126 observations. Do not represent this as ready.
- Browser DOM/geometry checks succeeded; image-based visual inspection was unavailable. Screenshots alone are not visual approval.

The retired ledger recorded 229 backend and 59 frontend passing tests, with inherited ruff/mypy debt. Those are historical reports, not freshly verified release results. Regenerate the baseline in T00 and compare diagnostic identities, not counts alone.

### Non-negotiable decisions

1. **Keep the removed value-walk graph removed.** Retain one compact, accessible attribution breakdown. Do not reintroduce the SVG waterfall or duplicate it in a second chart.
2. This is a personal analytical product, not a trading-advice engine. Distinguish facts, user-configured rules, and hypothetical scenarios. No automatic buy/sell instructions.
3. Do not rename broker identifiers, infer canonical equivalence from display names alone, or infer fund constituents from classification metadata.
4. Actual snapshot performance, position gain against cost, money-weighted return, and current-composition proxy risk must have distinct labels, periods, and methods.
5. Backend owns totals and validity. Never reconstruct authoritative aggregates from a capped browser list. Formatting and visual geometry may be client-side.
6. Every account/date filter must reach query keys, API parameters, service calculations, row counts, totals, and drill-down links. Declare exceptions visibly.
7. Missing data is not zero. Invalid metrics get a reason, not a raw-return fallback, invented flat segment, or stale cached number presented as fresh.
8. GET analytics remain cache-only and side-effect-free. Provider refreshes are explicit, bounded operations. Unsupported history is not cash.
9. No live service restart, deployment, production build-directory overwrite, provider refresh, package installation, migration, or personal-data edit without explicit approval. Use isolated rehearsal first.
10. Before implementation involving the database, verify Git exclusion, create and verify a consistent SQLite backup outside the repository, and use temporary/read-only copies. Never launch normal startup migrations against the live DB just to test a UI.
11. Currency allocation means **source value currency**, not underlying FX exposure. Product-level classification is not fund look-through.
12. Preserve old routes via redirects and existing `inst` links. Never lose the current investigation when switching between summary and detail.

### Deliverables and release boundaries

- **R1 — Trust and usability:** T00–T09, including consistent performance, accessible explanations, shared scope, and responsive layouts.
- **R2 — Compact briefing:** T10–T14, including the dashboard, attention, attribution, drawdown episodes, and events.
- **R3 — Investigation and allocation:** T15–T22, including security exposure, targets, scenarios, holdings, drill-downs, Orders, and Income.
- **R4 — Acceptance and documentation:** T23. Apply its checks to every earlier release too.
- **Gated extensions:** D01–D04. These are explicitly deferred from R1–R3; their readiness rules and implementation boundaries remain here rather than in a competing plan.

Ship complete vertical slices; do not build every backend feature first and leave the UI disconnected.

---

## 2. Product and technical contracts

### 2.1 Dashboard hierarchy

At 1440×1000 the first screen should include the balance/period header, key available metrics, and the main performance plot or its honest unavailable state. Proposed layout:

```text
Portfolio overview                    Account • Period • As of
Portfolio value       Investment return       Net external flows
Primary performance chart             What changed
                                      Main contributors / detractors
Allocation summary                    Needs attention, if any
Explore holdings                      Full analysis
```

Use a single-column mobile order: header → primary metrics → short change explanation → performance → allocation → attention/detail links. Aim for a default dashboard no more than 2200px tall on desktop and 3600px on mobile with the review fixture, excluding deliberately expanded details. These are design acceptance budgets, not a reason to hide warnings or clip content.

Move the full snapshot/deployment/reconstruction charts into Portfolio's performance workspace. Keep the full allocation list in Allocation, lifetime holding-return ranking in Returns, and detailed attribution in Snapshot changes. Keep the useful summaries and clear links on Dashboard.

### 2.2 Proposed metric contract

Add additive metadata first; migrate consumers before removing legacy fields. Mirror Pydantic models in `frontend/src/lib/api.ts`. This TypeScript shape is a complete target example, not a claim that these names already exist:

```ts
export type MetricReason = {
  code: string;
  message: string;
  actionHref: string | null;
};

export type MetricState = {
  status: "available" | "unavailable";
  value: number | null;
  unit: "GBP" | "percent" | "ratio";
  method: string;
  startDate: string | null;
  endDate: string | null;
  observations: number;
  reasons: MetricReason[];
};

export type AnalysisScope = {
  accountName: string | null;
  requestedStart: string | null;
  requestedEnd: string | null;
  effectiveStart: string | null;
  effectiveEnd: string | null;
  valuationDates: Array<{ accountName: string; date: string }>;
  warnings: string[];
};
```

Rules: unavailable ⇒ null value plus at least one reason; available ⇒ finite value; annualisation can be unavailable while cumulative return is available. An invalid common return chain invalidates its full-window curve/drawdown, unless a separately named valid subwindow is explicitly offered. No unnamed partial curve.

### 2.3 Shared scope and URL state

Use `account`, `period`, and optional `start`/`end` query parameters. Period options remain 1M/3M/6M/1Y/YTD/ALL initially; custom dates are accepted only after backend validation is implemented. URL state wins over stored defaults. Scope for historical analytics ends at the disclosed latest covered valuation date, not an implicit wall-clock date. Income may offer an explicitly labelled today-based trailing view with transaction-freshness warnings.

Preserve `tab`, `inst`, and order filters when composing links. Snapshot comparison retains its distinct from/to batch identifiers and displays “Latest snapshot comparison” unless the user explicitly selects another comparison. It does not pretend to match an arbitrary performance period.

### 2.4 Financial semantics and identity

- Reconstruct each account's latest state by valuation date, then import ID for same-account/same-date correction precedence. Consolidate all same-date updates before emitting one combined daily state. Prevent later historical imports moving current valuation backwards.
- Combined performance begins only once every selected account has coverage; disclose stale/misaligned account dates.
- Canonical security keys need verified identifiers/listings and currency/share-class distinctions. Same display name or similar ticker is insufficient. Keep unverified positions separate with a reason.
- Default combined allocation concentration to security level; preserve explicit account-position mode and constituent instrument IDs. Existing HHI is position/security-weight concentration, not underlying economic diversification.
- Current allocation remains cash-excluded in every dimension with disclosed denominator; show excluded cash separately. Group targets use that same denominator in this plan.
- Keep overlapping tags distinct from an exclusive allocation target set. Drift/what-if calculations require validated, disjoint membership or an explicit unavailable reason.

### 2.5 Design defaults

- Preserve the dark identity with solid base/raised surfaces. Reserve glass/blur for overlays and subtle header treatment, not every analytical card.
- Normal body/metric labels: 13–14px; metadata at least 12px where practicable. Page title 24–28px; section title 16–18px; primary balance about 36–44px. Keep tabular numerals.
- One interactive accent; neutral capital/value; green/red only for signed outcomes; amber for uncertainty/attention. Category colours are keyed by stable category identity, not rank.
- Default card padding 16–20px, 16–24px section spacing, one consistent radius scale. Financial tables align numeric values right.
- Compact chart currency labels (£250k, £1m); exact precision remains available on demand. Do not silently change financial rounding to achieve visual reconciliation.
- Aim for WCAG AA text contrast, visible focus, touch-friendly primary actions, keyboard/touch popovers, and reduced-motion support. Colour is never the sole encoding.

---

## 3. Execution method and commands

### Per-task workflow

Each numbered task is a deliverable with small implementation slices. Execute one slice at a time; split further if it cannot be implemented and verified in a short bounded session.

1. Add the named failing regression/acceptance test (one behaviour per test).
2. Run the exact test selection below and record the expected semantic failure; missing infrastructure alone does not prove a regression.
3. Implement the smallest passing change; do not couple unrelated cleanup.
4. Rerun targeted tests, then applicable broader gates. Review independently for specification compliance and financial/code quality.
5. Record evidence beside the task checkbox. Stage only owned paths/hunks. Commit the slice only after permission to commit the dirty tree is settled; never `git add .`.

All commands below are to be run from the repository root unless stated otherwise. They are planned verification commands, not results reported by this document.

```bash
# Whole-suite gates; inspect test isolation first in T00.
.venv/bin/pytest -q
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
make lint
make typecheck

# Keep build output away from the live-served frontend/dist.
npm --prefix frontend run build -- --outDir /tmp/stocks-experience-dist

# Existing isolated SQLite-copy harness. Expand it in T00/T04/T23.
.venv/bin/python scripts/verify_analysis_ui.py \
  --database portfolio.db \
  --dist /tmp/stocks-experience-dist \
  --output /tmp/stocks-experience-ui
```

Do not use `make check` as a read-only gate: it depends on the mutating `format` target. Compare fresh ruff/mypy diagnostics against T00, allowing no new diagnostics; do not broadly reformat inherited code to silence the baseline. No claimed pass count until real execution returns it.

---

## 4. Implementation tasks

### T00 — Establish a safe, reproducible baseline

**Status:** [x] Baseline established; defects reproduced, not release-approved. See [verification evidence](../verification/portfolio-experience.md#t00--safe-baseline) for fresh gates, safety checks and the failing 28-view browser matrix. **Dependencies:** none. **Review coverage:** cross-cutting.

**Objective:** Preserve the dirty tree and reproduce the review issues in isolated, repeatable tests.

**Files:** Modify `scripts/verify_analysis_ui.py`; create `backend/tests/test_experience_contracts.py`; create `docs/verification/portfolio-experience.md`. Inspect `pytest.ini`, the module-local DB/client fixtures in `backend/tests/test_risk_panel_api.py` and `backend/tests/test_portfolio_service.py`, `Makefile`, and application lifespan before running anything. There is no shared `conftest.py` at this baseline.

**Slices:**
1. Record branch/status and hashes of pre-existing modified/untracked files. Inspect the test DB configuration. Back up the live DB using SQLite online backup, verify integrity and logical equivalence, and confirm it stays Git-ignored.
2. Run baseline tests/static checks in isolation; retain complete diagnostics outside the repository if they contain private data. Put only sanitised summaries in verification documentation.
3. Extend the existing harness with route-specific GET allowlists, read-only copied DB, blocked mutation requests, immediate child-failure detection, deadline-bound readiness, and cleanup. Never permit startup migrations.
4. Capture current defects: performance validity mismatch, repeated-date labels, inverted drawdown, mobile overflowing routes and clipped tabs. Keep fixture-based checks alongside private live-copy rehearsal.

**Verify:** `.venv/bin/pytest backend/tests/test_experience_contracts.py -q`; whole-suite commands above; harness against isolated build. Expected initially: named new acceptance assertions expose current defects; baseline failures are recorded, not hidden or recategorised as success.

**Done when:** reproduction is deterministic, original files/data are untouched, and future acceptance checks cannot pass merely by rendering a loading page or an empty response.

### T01 — Canonicalise valuation dates and performance validity

**Status:** [x] Canonical daily states, common validity and metric/scope metadata implemented. [Evidence](../verification/portfolio-experience.md#t01--canonical-dates-and-common-validity): 253 backend / 59 frontend tests; no new static diagnostic identities. **Dependencies:** T00. **Review coverage:** initial performance defect; 15, 16, 17.

**Files:** Modify `backend/app/services/portfolio_service.py`, `backend/app/services/performance_service.py`, `backend/app/schemas.py`; tests `backend/tests/test_portfolio_service.py`, `backend/tests/test_performance_regressions.py`, `backend/tests/test_experience_contracts.py`.

**Slices:**
1. Add fixtures for same-date account imports, same-account corrections, accounts beginning on different dates, and a historical import arriving last. Assert one chronological state per date and stable current valuation.
2. Reconstruct complete same-date account state before calculating combined intervals. Trace which shared callers inherit the change, including allocation and attribution, and preserve their boundary semantics.
3. Test that `_interval_dietz_returns`, cumulative KPI, wealth curve, and drawdown share the same canonical input and validity decision. Do not fix only the length guard by silently discarding a financial interval.
4. Test no-gain contributions, withdrawals, invalid denominators, missing account coverage, zero-length intervals, non-finite inputs, and true total loss. Expose a structured reason for any invalid chain.
5. Add additive metric/scope metadata. Preserve separate unavailable reasons for short annualisation windows or undefined ratios.

**Verify:** `.venv/bin/pytest backend/tests/test_portfolio_service.py backend/tests/test_performance_regressions.py backend/tests/test_experience_contracts.py -q`.

**Done when:** raw and adjusted series use one point per date; valid adjusted endpoint/index and cumulative KPI reconcile before rounding; invalid chains cannot publish a full-window numeric drawdown. Account boundary changes cannot masquerade as market gain.

### T02 — Render truthful metric, empty, and error states

**Status:** [x] Truthful UI metric/loading/error/empty states implemented. [Evidence](../verification/portfolio-experience.md#t02--truthful-ui-states): 253 backend / 69 frontend tests and frontend typecheck pass. **Dependencies:** T01. **Review coverage:** 13, 15, 16, 34.

**Files:** Modify `frontend/src/lib/api.ts`, `frontend/src/components/PerformancePanel.tsx`, `frontend/src/components/PortfolioReturnCard.tsx`, `frontend/src/routes/Overview.tsx`; create `frontend/src/components/AnalysisStatus.tsx`, `frontend/src/components/__tests__/AnalysisStatus.test.tsx`; extend `frontend/src/components/__tests__/PerformancePanel.test.tsx` and create `frontend/src/routes/__tests__/Overview.test.tsx`.

**Slices:**
1. Feed unavailable metric fixtures with non-empty legacy curves; require the reason and no misleading full-window plot. Test short-history annualisation separately from broken cumulative performance.
2. Render compact per-metric explanations, with retry only for fetch errors and repair links only when an actual destination exists.
3. Distinguish loading, error, empty account, partial data, stale data, and valid zero balance. A summary fetch failure must not become “Welcome, import your portfolio.”
4. Replace generic performance “typical” ranges/ratings with method, observed period, sampling, and limitations. Explain a zero risk-free assumption rather than calling a Sharpe automatically good or weak.

**Verify:** `npm --prefix frontend test -- --run AnalysisStatus PerformancePanel PortfolioReturnCard Overview`; `npm --prefix frontend run typecheck`.

**Done when:** every dash has a meaningful accessible reason; errors cannot look like valid empty results; distinct return concepts cannot share an ambiguous label.

### T03 — Repair performance and drawdown chart geometry

**Status:** [x] Chart joining, sparse ticks, observation markers and drawdown geometry corrected. [Evidence](../verification/portfolio-experience.md#t03--snapshot-chart-geometry): 73 frontend tests; chart geometry passes at 320/390/768/1440px (T04 layout failures remain). **Dependencies:** T01–T02. **Review coverage:** initial chart defects; 11, 17.

**Files:** Modify `frontend/src/components/PerformancePanel.tsx`, `frontend/src/lib/chartDates.ts`; create `frontend/src/lib/performanceChart.ts`, `frontend/src/lib/__tests__/performanceChart.test.ts`; extend `frontend/src/components/__tests__/PerformancePanel.test.tsx` and `scripts/verify_analysis_ui.py`.

**Slices:**
1. Unit-test joining portfolio/raw/benchmark values into one display row per timestamp without overwriting valid named series. Date joining is presentation-only; backend resolves financial same-date state.
2. Render sparse, deterministic date ticks appropriate to width. Show observation dots and linear/step geometry appropriate to snapshots, not a smooth implied daily path.
3. Remove the reversed drawdown Y-axis; zero at top, negative values below. Emphasise the adjusted index baseline at 100 without clipping extrema. Preserve the clearly named raw-value opt-in overlay.
4. Browser-test actual tick bounding boxes, tick duplicates, zero/trough vertical ordering, valid data extent, and no line connecting unavailable intervals. A mocked Recharts test is insufficient.

**Verify:** `npm --prefix frontend test -- --run performanceChart PerformancePanel`; isolated browser harness at 390/768/1440px.

**Done when:** adjacent visible axis labels do not overlap, dates are not duplicated, losses go down, and a sparse history does not imply continuous measured values.

### T04 — Repair responsive containers and navigation affordances

**Status:** [x] Responsive containers, scroll regions and reachable controls implemented. [Evidence](../verification/portfolio-experience.md#t04--responsive-containers-and-reachable-controls): 80 isolated browser checks / 966 focus checks pass; 254 backend / 74 frontend tests. **Dependencies:** T00. **Review coverage:** mobile defects; 29.

**Files:** Modify `frontend/src/routes/Holdings.tsx`, `frontend/src/components/HoldingsTable.tsx`, `frontend/src/components/IncomeAnalysisPanel.tsx`, `frontend/src/components/OrderHistorySection.tsx`, `frontend/src/components/ChartPanel.tsx`, `frontend/src/components/WorkspaceTabs.tsx`, `frontend/src/layout/Topbar.tsx`; extend `scripts/verify_analysis_ui.py`.

**Slices:**
1. Add regression checks for Holdings, Income, Orders, Overview, Allocation, Returns, and Classifications. Include long security/account names and an empty/error case.
2. Fix grid/flex min-widths and wrapping controls; constrain wide tables to explicitly scrollable containers. Do not apply root `overflow-x:hidden` as a substitute.
3. Give chart/workspace tabs a complete narrow-screen path: wrapped buttons or scrollable strip with visible overflow affordance and focus scrolling.
4. Test 320/390/768/1440px and a desktop zoom equivalent. Test reachability of every tab/button, not just document width. Preserve existing mobile navigation.

**Verify:** isolated build plus browser harness; `npm --prefix frontend test -- --run WorkspaceTabs Topbar MobileNav`.

**Done when:** document width equals viewport width on every tested route; off-screen table content is intentionally scrollable; no clipped controls; keyboard focus reveals the active control.

### T05 — Introduce a quieter, consistent surface and typography system

**Status:** [x] Solid surface tokens and shared semantic metric/header layouts implemented. [Evidence](../verification/portfolio-experience.md#t05--surfaces-and-typography): 77 frontend tests; 80 browser checks; migrated metric contrast ≥6.76:1. **Dependencies:** T04. **Review coverage:** 7, 8, 10.

**Files:** Modify `frontend/src/index.css`, `frontend/tailwind.config.js`, `frontend/src/components/StatCard.tsx`, `frontend/src/components/HeroKpi.tsx`; create `frontend/src/components/SectionHeader.tsx`, `frontend/src/components/MetricCard.tsx`, `frontend/src/components/__tests__/MetricCard.test.tsx`.

**Slices:**
1. Add semantic tokens for base/raised/overlay surfaces, text emphasis, borders, spacing, and radii using §2.5 defaults. Test component semantics and variants, not raw class-string snapshots.
2. Replace pervasive glass backgrounds with solid cards. Preserve subtle overlay treatment where it helps stacking; avoid nested outlined cards for every row.
3. Establish shared section-header/actions and metric-card layouts. Migrate one panel first, inspect it, then migrate remaining panels in small batches.
4. Increase important explanations/labels to readable sizes and contrast; keep tabular numbers and sensible content widths.

**Verify:** `npm --prefix frontend test -- --run MetricCard`; full frontend/typecheck; browser comparison of Overview, Allocation, Holdings, Income. Measure contrast and inspect desktop/mobile screenshots when vision/manual review is available.

**Done when:** primary and secondary information have clear hierarchy, calculations are unchanged, and no page gains unreadable tiny text to meet height budgets.

### T06 — Standardise colours, number formats, legends, and chart tooltips

**Status:** [x] Shared formats/tooltip/legend and stable allocation colours implemented. [Evidence](../verification/portfolio-experience.md#t06--formats-colours-and-chart-primitives): 85 frontend tests; 80 browser checks including every allocation dimension and exact-value toggle. **Dependencies:** T05. **Review coverage:** 9, 10, 11, 23.

**Files:** Modify `frontend/src/lib/formatters.ts`, `frontend/src/components/ChartPanel.tsx`, `frontend/src/components/InstrumentDetail.tsx`, `frontend/src/components/AllocationDonut.tsx`; create `frontend/src/lib/chartTheme.ts`, `frontend/src/components/ChartTooltip.tsx`, `frontend/src/components/ChartLegend.tsx`, `frontend/src/lib/__tests__/formatters.test.ts`, `frontend/src/lib/__tests__/chartTheme.test.ts`.

**Slices:**
1. Test currency axes, exact-detail currency, signed changes, near-zero/negative-zero display, null values, dates, and percentage precision. Never use display-rounded values in reconciliation.
2. Key category colour to stable dimension/category identity. Test that sorting and filtering do not recolour surviving categories; ensure accessible “Unclassified” styling.
3. Centralise legend/tooltip structure and apply semantics consistently. Colour changes do not remove signed values, labels, or line-style distinctions.
4. Add donut table swatches; right-align numeric cells and choose a meaningful first-column heading for every dimension. Avoid an unexplained duplicated HHI headline.

**Verify:** `npm --prefix frontend test -- --run formatters chartTheme AllocationDonut`; full frontend/typecheck; colour/legend checks under all allocation dimensions.

**Done when:** the same quantity/category looks consistent across routes, £1m is formatted compactly, and exact values remain accessible.

### T07 — Accessible definitions, motion, and navigation focus

**Status:** [x] Immediate balance, shared keyboard/touch definitions, reduced motion and route/skip focus implemented. [Evidence](../verification/portfolio-experience.md#t07--definitions-motion-and-focus): 254 backend / 90 frontend tests; 80 expanded browser cases pass. **Dependencies:** T05. **Review coverage:** 12, 13.

**Files:** Modify `frontend/src/components/HeroKpi.tsx`, `frontend/src/components/AuroraBackground.tsx`, `frontend/src/components/SegmentedControl.tsx`, `frontend/src/components/PerformancePanel.tsx`, `frontend/src/layout/AppShell.tsx`; create `frontend/src/components/MetricInfo.tsx`, `frontend/src/lib/metricGlossary.ts`, `frontend/src/components/__tests__/MetricInfo.test.tsx`, `frontend/src/components/__tests__/HeroKpi.test.tsx`.

**Slices:**
1. Test immediate final balance rendering; remove the count-up animation. Add reduced-motion behaviour to ambient/route/selection animation.
2. Replace hover-only explanations with named buttons and popovers usable by Enter/Space, touch, Escape, and outside click. Return focus on dismissal; prevent off-screen popovers.
3. Centralise definitions for Dietz, money-weighted return, CAGR, drawdown, HHI, and DRIP proxy. Include method/period where dynamic, not one misleading universal definition.
4. Add skip-to-main and route-heading focus management without disrupting back navigation or active text input.

**Verify:** `npm --prefix frontend test -- --run MetricInfo HeroKpi`; browser keyboard-only path and emulated reduced motion at desktop/mobile.

**Done when:** all explanations are reachable without hover, displayed balance is immediately real, and reduced-motion users do not get continuous decorative movement.

### T08 — Share account/period scope and persist investigation state

**Status:** [x] URL-first account/performance-period scope, validation, history preservation and contextual Income settings implemented. [Evidence](../verification/portfolio-experience.md#t08--url-first-analysis-scope): 264 backend / 104 frontend tests; 80 browser cases including scoped requests and Back/Forward at 390/1440px. **Dependencies:** T01–T02. **Review coverage:** 4, 16, 31.

**Files:** Modify `frontend/src/layout/Topbar.tsx`, `frontend/src/layout/AppShell.tsx`, `frontend/src/state/usePreferences.ts`, `frontend/src/routing.tsx`, `frontend/src/lib/api.ts`, `backend/app/routers/portfolio.py`, `backend/app/schemas.py`; create `frontend/src/state/useAnalysisScope.ts`, `frontend/src/state/__tests__/useAnalysisScope.test.tsx`; extend `frontend/src/__tests__/routing.test.ts` and `backend/tests/test_experience_contracts.py`.

**Slices:**
1. Test URL parsing/validation for account, supported periods, start/end ordering, unknown accounts, and malformed inputs. Legacy links retain their original identifiers and unrelated query parameters.
2. Implement URL-first scope with stored defaults as fallback, using disclosed valuation dates. If custom dates are not yet supported by a service, reject/disable them rather than silently ignoring them.
3. Include scope in query keys and endpoint parameters. Expose requested/effective dates and partial-coverage warnings from backend.
4. Preserve period/filter state through tabs and back/forward. Put DRIP heuristic configuration in a contextual Data/Income setting rather than a permanently prominent unexplained pound amount.

**Verify:** `npm --prefix frontend test -- --run useAnalysisScope routing Topbar`; `.venv/bin/pytest backend/tests/test_experience_contracts.py -q`.

**Done when:** changing account/period cannot leave stale results under new labels; explicit exceptions retain their own clearly labelled period.

### T09 — Centralise overview scope and current-value summaries

**Status:** [x] Account-scoped authoritative summaries, valuation dates and cash-excluded group denominators implemented. [Evidence](../verification/portfolio-experience.md#t09--authoritative-current-summaries): 266 backend / 105 frontend tests; 80 browser cases. **Dependencies:** T01, T08. **Review coverage:** 4, 16, 34.

**Files:** Modify `backend/app/services/portfolio_service.py`, `backend/app/routers/portfolio.py`, `backend/app/schemas.py`, `frontend/src/lib/api.ts`, `frontend/src/routes/Overview.tsx`, `frontend/src/layout/Topbar.tsx`, `frontend/src/routes/Holdings.tsx`; extend `backend/tests/test_portfolio_service.py`, `backend/tests/test_order_account_filtering.py`, `frontend/src/routes/__tests__/Overview.test.tsx`.

**Slices:**
1. Add account-scoped summary fixtures and reconciliation identities for value, invested value, cash, book cost, P&L, and groups. Use historical-import precedence from T01.
2. Move Overview's account-filtered aggregate rebuild to authoritative API results; do not duplicate allocation calculation logic in React.
3. Return per-account valuation dates and scope-aware freshness. Topbar must not label a selected account with another account's latest date.
4. Trace Holdings group-target badges and position queries to the same scope; do not compare a filtered denominator with unfiltered group totals.

**Verify:** `.venv/bin/pytest backend/tests/test_portfolio_service.py backend/tests/test_order_account_filtering.py -q`; `npm --prefix frontend test -- --run Overview Topbar`.

**Done when:** all-account totals reconcile with scoped account totals under the same valuation policy; detail counts cannot accidentally become authoritative totals.

### T10 — Rebuild the compact dashboard and performance workspace

**Status:** [x] Compact briefing and separate Performance workspace implemented. [Evidence](../verification/portfolio-experience.md#t10--compact-briefing-and-performance-workspace): 266 backend / 107 frontend tests; 90 browser cases; dashboard 1338px desktop / 2864px mobile. **Dependencies:** T02–T09. **Review coverage:** 1, 2, 3, 5, 14.

**Files:** Modify `frontend/src/routes/Overview.tsx`, `frontend/src/routes/PortfolioWorkspace.tsx`, `frontend/src/components/HeroKpi.tsx`, `frontend/src/components/AttributionSummaryCard.tsx`, `frontend/src/components/AttributionWaterfall.tsx`, `frontend/src/components/ChartPanel.tsx`; create `frontend/src/routes/PerformanceWorkspace.tsx`; extend `frontend/src/routes/__tests__/Overview.test.tsx`, `frontend/src/components/__tests__/AttributionWaterfall.test.tsx`, and routing tests.

**Slices:**
1. Add structural tests for one balance, one primary return, one compact attribution breakdown, and no value-walk SVG. Use the §2.1 hierarchy rather than stacking every existing panel.
2. Reduce hero height and remove the null trend chip. Use actual snapshot history for the optional small value sparkline, with dates; hide it when insufficient. Never use current-price reconstruction as the hero trend.
3. Remove duplicate attribution tiles, retaining signs, dates, reconciliation, notes, and contributor links. Make detailed breakdown expandable if necessary, but never hide a material warning.
4. Add a Performance tab under Portfolio for full performance, raw snapshots, deployment, and reconstruction. Rename reconstruction “Past holdings valued at today's prices”; do not overlay historical benchmark returns on this non-performance series.
5. Keep a compact allocation summary and links to detailed Allocation/Returns/Snapshot changes. Test height budgets with warnings and unavailable states included.

**Verify:** `npm --prefix frontend test -- --run Overview AttributionSummaryCard AttributionWaterfall routing`; isolated browser acceptance at 390/1440px.

**Done when:** primary plot/status is within the first desktop viewport, the dashboard meets default height budgets without clipping, and every relocated view remains directly reachable.

### T11 — Add data-confidence and needs-attention summaries

**Status:** [x] Cache-only data confidence, scoped evidence-backed attention and local reminder controls implemented. [Evidence](../verification/portfolio-experience.md#t11--data-confidence-and-attention): 273 backend / 111 frontend tests; 100 browser cases. **Dependencies:** T02, T08–T10. **Review coverage:** 6, 34, 35 readiness.

**Files:** Create `backend/app/services/data_quality_service.py`, `backend/tests/test_data_quality_service.py`, `frontend/src/components/DataConfidencePanel.tsx`, `frontend/src/components/AttentionList.tsx`, and matching tests in `frontend/src/components/__tests__/`; modify `backend/app/routers/portfolio.py`, `backend/app/schemas.py`, `frontend/src/lib/api.ts`, `frontend/src/routes/Overview.tsx`, `frontend/src/routes/DataWorkspace.tsx`.

**Slices:**
1. Return snapshot freshness, transaction first/last coverage dates, classification coverage by value/count, matching issues, market-history readiness, and metric-blocking reasons without a provider call.
2. Represent each attention item with stable ID, fact/rule category, evidence, scope, severity, and a valid action link. Do not claim transaction completeness merely because some orders exist.
3. Display a small healthy status when no issues; expand only relevant exceptions. A market-data readiness warning must not dominate unrelated healthy holdings analysis.
4. Allow personal rule tolerances/dismissal for non-critical reminders; never permanently dismiss a broken-calculation warning. Scope dismissal to the unchanged evidence, not just a holding name.

**Verify:** `.venv/bin/pytest backend/tests/test_data_quality_service.py -q`; `npm --prefix frontend test -- --run DataConfidencePanel AttentionList`.

**Done when:** users can explain why a metric is missing and reach the repair workflow; no alert suggests an unrequested trade or invents certainty.

### T12 — Make contribution analysis period-aware and drillable

**Status:** [x] Canonical dated contribution boundaries, unknown-flow gating, reconciliation and matching comparison drill-downs implemented. [Evidence](../verification/portfolio-experience.md#t12--dated-contributions-and-source-comparisons): 277 backend / 113 frontend tests; 110 browser cases. **Dependencies:** T01, T08–T10. **Review coverage:** 3, 19, 30.

**Files:** Modify `backend/app/services/attribution_service.py`, `backend/app/schemas.py`, `frontend/src/components/AttributionSummaryCard.tsx`, `frontend/src/routes/Diff.tsx`, `frontend/src/lib/api.ts`; extend `backend/tests/test_snapshot_attribution.py` and `frontend/src/components/__tests__/AttributionSummaryCard.test.tsx`.

**Slices:**
1. Test distinct-date snapshot comparison, account boundaries, flows, new/closed holdings, unknown flow components, and reconciliation to closing value.
2. Expose signed pound residual contributions, explicit comparison dates, uncertainty, and source links. Call residuals estimated market movement, not proven pure price effects.
3. Add percentage-point contributions only after a documented denominator/method and additive reconciliation test exist; otherwise mark that field unavailable. Never divide by net portfolio movement near zero.
4. Make contributor/detractor rows links preserving account and selected comparison; full detail opens the matching snapshot comparison rather than a default period.

**Verify:** `.venv/bin/pytest backend/tests/test_snapshot_attribution.py -q`; `npm --prefix frontend test -- --run AttributionSummaryCard`.

**Done when:** each mover can be investigated, values reconcile, and limitations remain visible without duplicate tiles or charts.

### T13 — Explain drawdowns as episodes

**Status:** [x] Observed drawdown episodes and URL-backed chart-only episode zoom implemented. [Evidence](../verification/portfolio-experience.md#t13--observed-drawdown-episodes): 290 backend / 117 frontend tests; 110 browser cases including episode zoom/reset. **Dependencies:** T01–T03, T08, T10. **Review coverage:** 20.

**Files:** Modify `backend/app/services/performance_service.py`, `backend/app/schemas.py`, `frontend/src/lib/api.ts`; create `frontend/src/components/DrawdownEpisodes.tsx`, `backend/tests/test_drawdown_episodes.py`, `frontend/src/components/__tests__/DrawdownEpisodes.test.tsx`; modify `frontend/src/routes/PerformanceWorkspace.tsx`.

**Slices:**
1. Pure-test peak, trough, first recovery, unrecovered episodes, tied peaks, flat history, and invalid chain. Report dates/elapsed calendar days and observation count.
2. Build episodes from the exact valid adjusted index, not account value or unrelated daily market prices.
3. Show a compact episode table linked to the chart window. Label recovery as observed between snapshots, not exact intraday recovery.

**Verify:** `.venv/bin/pytest backend/tests/test_drawdown_episodes.py -q`; `npm --prefix frontend test -- --run DrawdownEpisodes`.

**Done when:** maximum episode depth matches the KPI; incomplete/invalid history cannot produce a falsely precise recovery date.

### T14 — Add meaningful timeline events

**Status:** [ ] Planned. **Dependencies:** T08, T10, T12. **Review coverage:** 18, 30.

**Files:** Create `backend/app/services/timeline_service.py`, `backend/tests/test_timeline_service.py`, `frontend/src/components/TimelineEvents.tsx`, `frontend/src/components/__tests__/TimelineEvents.test.tsx`; modify `backend/app/routers/portfolio.py`, `backend/app/schemas.py`, `frontend/src/lib/api.ts`, `frontend/src/components/PerformancePanel.tsx`, `frontend/src/components/InstrumentDetail.tsx`.

**Slices:**
1. Test typed deposit/withdrawal/trade/import events and stable source IDs under account/date filtering. Distinguish valuation date, order date, and import time.
2. Add marker toggles with explicit event categories. Group crowded same-day events; do not fabricate causal explanations from coincident dates.
3. Open source orders/imports from keyboard/touch markers and an accessible event list. Keep historical import-time events separate from economic events when their timestamps differ.

**Verify:** `.venv/bin/pytest backend/tests/test_timeline_service.py -q`; `npm --prefix frontend test -- --run TimelineEvents`; browser crowded-event fixture.

**Done when:** events explain context without obscuring the chart and every marker maps to an actual record.

### T15 — Consolidate security exposure and explain concentration

**Status:** [ ] Planned. **Dependencies:** T01, T06, T09. **Review coverage:** 21, 22, 23.

**Files:** Create `backend/app/services/security_identity_service.py`, `backend/tests/test_security_identity_service.py`; modify `backend/app/services/allocation_service.py`, `backend/app/schemas.py`, `backend/app/routers/portfolio.py`, `frontend/src/lib/api.ts`, `frontend/src/components/AllocationAnalysisPanel.tsx`, `frontend/src/components/AllocationDonut.tsx`; extend `backend/tests/test_allocation_service.py` and allocation frontend tests.

**Slices:**
1. Test verified same-security positions across accounts, distinct listings/share classes/currencies, missing identifiers, and display-name collisions. Reuse reliable namespaced identity conventions already present in risk without conflating risk-factor and legal-security identity.
2. Add explicit `group_by=security|position` with constituent records, aggregation-confidence/reasons, scoped GBP values, top-one/top-five, and HHI. Combined view defaults to security; preserve position mode.
3. Require security/position modes to reconcile to identical non-cash totals. Retain unverified identities separately rather than guessing.
4. Label HHI as security/position-weight concentration. Remove generic low-risk implications from threshold labels; explain overlap/correlation limitations. Show intuitive top-exposure measures beside the technical index.
5. Add swatches/dimension headings from T06 and clickable category filters; expanding one security reveals accounts.

**Verify:** `.venv/bin/pytest backend/tests/test_security_identity_service.py backend/tests/test_allocation_service.py -q`; `npm --prefix frontend test -- --run AllocationAnalysisPanel AllocationDonut allocationGolden`.

**Done when:** verified duplicate EQQQ exposure is combined in security mode, totals remain invariant, ambiguous instruments stay separate, and HHI is not presented as proof of diversification.

### T16 — Make group targets and drift comparable

**Status:** [ ] Planned. **Dependencies:** T09, T15. **Review coverage:** 24.

**Files:** Modify `backend/app/routers/groups.py`, `backend/app/services/allocation_service.py`, `backend/app/schemas.py`, `frontend/src/components/GroupsSection.tsx`, `frontend/src/routes/Groups.tsx`, `frontend/src/components/HoldingsTable.tsx`; create `frontend/src/components/TargetDriftPanel.tsx`, `backend/tests/test_allocation_targets.py`, `frontend/src/components/__tests__/TargetDriftPanel.test.tsx`.

**Slices:**
1. Test target-set validation: exclusive memberships, sum-to-100 within declared tolerance, unassigned holdings, missing targets, and account scope. Preserve existing overlapping groups as descriptive tags rather than silently rewriting them.
2. Calculate actual/target weight, signed percentage-point drift, signed GBP gap, and user-configurable symmetric tolerance using one cash-excluded denominator.
3. Render actual-versus-target bars/dots with a neutral within-band state. Do not colour every overweight allocation as a warning by default.
4. Give users a path to resolve invalid target sets; never overwrite their memberships automatically. Correct Holdings badges to consume the same backend drift result.

**Verify:** `.venv/bin/pytest backend/tests/test_allocation_targets.py -q`; `npm --prefix frontend test -- --run TargetDriftPanel`.

**Done when:** target gaps are interpretable and account-consistent, with explicit unsupported states for overlapping or incomplete target sets.

### T17 — Add a contribution-only allocation scenario

**Status:** [ ] Planned. **Dependencies:** T16. **Review coverage:** 25.

**Files:** Create `backend/app/services/allocation_scenario_service.py`, `backend/tests/test_allocation_scenario_service.py`, `frontend/src/components/AllocationScenarioPanel.tsx`, `frontend/src/components/__tests__/AllocationScenarioPanel.test.tsx`; modify `backend/app/routers/portfolio.py`, `backend/app/schemas.py`, `frontend/src/lib/api.ts`, `frontend/src/components/AllocationAnalysisPanel.tsx`.

**Slices:**
1. Define a validated, non-persisting scenario request: non-negative contribution, explicit allocations by eligible target group, selected scope, and excluded-cash policy. Sum of allocations must equal contribution within currency tolerance.
2. Test conservation, zero contribution, invalid/overlapping groups, negative/non-finite inputs, and before/after drift. Pure maths: `after_value[g] = current_value[g] + allocation[g]`; weights use current invested total plus contribution.
3. Let users choose hypothetical amounts. Do not generate suggested trades, optimise allocation, subtract from real cash, or write portfolio state.
4. Display before/after comparison, assumptions, reset, and “Hypothetical contribution; no orders created.”

**Verify:** `.venv/bin/pytest backend/tests/test_allocation_scenario_service.py -q`; `npm --prefix frontend test -- --run AllocationScenarioPanel`; verify no mutation request or DB change.

**Done when:** hypothetical values reconcile and cannot be mistaken for actual holdings or trading recommendations.

### T18 — Improve holdings columns, names, and saved views

**Status:** [ ] Planned. **Dependencies:** T04, T06, T08, T09, T15. **Review coverage:** 27, 28, 31.

**Files:** Modify `frontend/src/components/HoldingsTable.tsx`, `frontend/src/routes/Holdings.tsx`, `frontend/src/state/usePreferences.ts`, `frontend/src/layout/AppShell.tsx`, `frontend/src/lib/api.ts`; create `frontend/src/lib/instrumentDisplay.ts`, `frontend/src/components/__tests__/HoldingsTable.test.tsx`, `frontend/src/lib/__tests__/instrumentDisplay.test.ts`; if persisted custom names are introduced, modify `backend/app/models.py`, `backend/app/routers/instruments.py`, `backend/app/schemas.py` and create a new Alembic revision during isolated implementation.

**Slices:**
1. Test default Security/Account/Value/Weight/Gain–loss/Recent change columns, scoped denominator, sorting, nulls, and search by displayed ticker/name/original identifier.
2. Add versioned saved column/sort preferences with reset; meaningful filters belong in URL state. Account column is prominent in combined view.
3. Introduce a short display-name resolver with ticker and original broker name available in detail. Any persisted user override is separate metadata, not a replacement for canonical identity or source name.
4. Add accessible sortable headers and optional classification/details columns. Keep period/basis clear for recent change versus gain against cost.

**Verify:** `npm --prefix frontend test -- --run HoldingsTable instrumentDisplay`; API/migration tests if persistence is added. Rehearse migration/rollback only on a copy.

**Done when:** holdings are scannable without losing source identifiers, weight is trustworthy, and saved preferences survive reload without overriding explicit links.

### T19 — Put instrument detail where the user acts

**Status:** [ ] Planned. **Dependencies:** T07–T08, T18. **Review coverage:** 29, 31.

**Files:** Modify `frontend/src/routes/Holdings.tsx`, `frontend/src/components/InstrumentDetail.tsx`, `frontend/src/routing.tsx`; create `frontend/src/components/InstrumentDetailDrawer.tsx`, `frontend/src/routes/__tests__/Holdings.test.tsx`.

**Slices:**
1. Test desktop inline detail and narrow-screen drawer driven by the existing `inst` URL parameter. Validate IDs without silently normalising malformed tokens.
2. Implement focus trap, named close/back, Escape dismissal, initial focus, and return to selected row. Direct-linked detail works with no prior row selection.
3. Preserve query/sort/scroll on close and back/forward. On account changes, clear or visibly reconcile an out-of-scope instrument; never show one account's detail under another's heading.
4. Give history/order requests separate loading/error/empty states and retry actions; no missing history drawn as zero.

**Verify:** `npm --prefix frontend test -- --run Holdings routing`; browser row-select/close/back sequence at 390/1440px.

**Done when:** selecting a mobile holding opens immediately visible detail without losing investigation state.

### T20 — Make every analytical drill-down preserve context

**Status:** [ ] Planned. **Dependencies:** T08, T12, T15, T18–T19. **Review coverage:** 19, 23, 30, 31.

**Files:** Create `frontend/src/lib/investigationLinks.ts`, `frontend/src/lib/__tests__/investigationLinks.test.ts`; modify `frontend/src/components/AttributionSummaryCard.tsx`, `frontend/src/components/AllocationAnalysisPanel.tsx`, `frontend/src/components/AllocationDonut.tsx`, `frontend/src/components/GroupPerformancePanel.tsx`, `frontend/src/components/IncomeAnalysisPanel.tsx`, `frontend/src/routes/Holdings.tsx`.

**Slices:**
1. Test link builders preserving encoded accounts, period, group/category identity, instrument constituents, and matching transaction/comparison filters.
2. Implement target filters before adding links. Category links must actually filter Holdings; group/Income links must actually filter matching rows.
3. Use real links for navigation and buttons for expansion; retain keyboard focus and browser navigation semantics.
4. Add a browser round trip from dashboard contributor → holding → orders → back, and allocation category → filtered holdings.

**Verify:** `npm --prefix frontend test -- --run investigationLinks routing`; expanded isolated browser harness.

**Done when:** every visible “Explore”/row/category link arrives at the promised scope, not a default unfiltered screen.

### T21 — Make order pagination and result totals explicit

**Status:** [ ] Planned. **Dependencies:** T04, T08, T20. **Review coverage:** 32.

**Files:** Modify `backend/app/routers/orders.py`, `backend/app/services/order_service.py`, `backend/app/schemas.py`, `frontend/src/lib/api.ts`, `frontend/src/components/OrderHistorySection.tsx`, `frontend/src/routes/Orders.tsx`; create `backend/tests/test_order_pagination.py`, `frontend/src/components/__tests__/OrderHistorySection.test.tsx`.

**Slices:**
1. Test stable date-plus-ID pagination with more than 100 rows, shared timestamps, search/type/account/date filters, and empty results. Apply filters before limit and use a consistent snapshot of count/totals where necessary.
2. Return `items`, filtered count, page/cursor metadata, and authoritative full-filter totals. Choose one pagination strategy and document it; do not infer `has_more` from UI counts.
3. Render “Showing X–Y of Z matching transactions” with accessible next/back or load-more. Clearly distinguish all-filter totals from any visible-row subtotal.
4. Preserve filters when paging and reset pagination appropriately when filters change; handle slow/error responses without mixing pages from different scopes.

**Verify:** `.venv/bin/pytest backend/tests/test_order_pagination.py backend/tests/test_order_account_filtering.py -q`; `npm --prefix frontend test -- --run OrderHistorySection orderFilters`.

**Done when:** every matching transaction is reachable, totals do not change merely because the page changes, and mobile pagination remains accessible.

### T22 — Make Income explain timing and change drivers

**Status:** [ ] Planned. **Dependencies:** T04, T08, T11, T20–T21. **Review coverage:** 33, 34.

**Files:** Modify `backend/app/services/order_service.py`, `backend/app/routers/orders.py`, `backend/app/schemas.py`, `frontend/src/lib/api.ts`, `frontend/src/lib/dripAnalysis.ts`, `frontend/src/components/IncomeAnalysisPanel.tsx`, `frontend/src/components/InstrumentDetail.tsx`, `frontend/src/components/OrderHistorySection.tsx`; create `backend/tests/test_income_analysis.py`, `frontend/src/components/__tests__/IncomeAnalysisPanel.test.tsx`; extend `frontend/src/lib/__tests__/dripAnalysis.test.ts`.

**Slices:**
1. Audit/reconcile stored DRIP classification, threshold-based retrospective proxy, and trailing-yield logic. Test explicitly classified non-DRIP purchases, threshold boundaries, account scope, incomplete history, and no dividends recorded. Expose the chosen basis consistently.
2. Add backend monthly proxy totals, same-calendar-period prior-year comparison, holding contributions to the change, and current/closed holding split. Leap-year and boundary dates must be explicit.
3. Do not compare a partial current year with a complete previous year. Disclose the latest transaction date and unknown missing history rather than counting unrecorded months as confirmed zero income.
4. Render timing/driver views compactly; link to matching purchases. Preserve the prominent “reinvestment proxy, not dividend ledger” qualification, including detail chips and Orders headings.

**Verify:** `.venv/bin/pytest backend/tests/test_income_analysis.py backend/tests/test_order_service.py -q`; `npm --prefix frontend test -- --run IncomeAnalysisPanel dripAnalysis`.

**Done when:** users can explain the change by period/holding, and no view relabels inferred small purchases as proven cash dividends.

### T23 — Complete help, integration, accessibility, and release evidence

**Status:** [ ] Planned. **Dependencies:** each release's selected tasks; full R3 depends on T00–T22. **Review coverage:** all.

**Files:** Modify `README.md`, `frontend/src/routes/Help.tsx`, `frontend/src/routes/__tests__/Help.test.tsx`, `scripts/verify_analysis_ui.py`; update `docs/verification/portfolio-experience.md` and task checkboxes in this plan. Add regression tests alongside their owning components/services.

**Slices:**
1. Update Help around user questions: current state, performance methods, period/scope exceptions, contribution interpretation, allocation identity, Income proxy, data confidence, and hypothetical scenarios. Include tested deep links.
2. Remove outdated README descriptions of routes/metrics; explain legacy redirects, renamed reconstruction view, and isolated verification commands.
3. Run full suite, fresh type/static baselines, isolated build, and browser matrix. Test desktop/mobile, keyboard/touch, reduced motion, long names, error/empty/partial/stale states, and account switching.
4. Audit visible text contrast and chart colour redundancy. Capture and inspect screenshots; if image/manual inspection is unavailable, report visual acceptance as outstanding rather than passed.
5. Measure route request count, response latency, and layout shift using the same fixture before/after. Use recorded baseline measurements to set regression budgets; do not invent performance improvements.
6. Independently review financial identities and cross-scope links. Check backup/integrity and original/live DB preservation. Commit only authorised changes. Deployment remains a separately approved operation with rollback instructions.

**Verify:** all commands in §3, plus the applicable release assertions in §6 (gated-extension assertions apply only when that extension ships). Expected: all new behaviour tests pass, no new static diagnostics, no uncaught page errors, complete navigation at every target width, and evidence for every checked-off task.

**Done when:** the release is usable end to end, the user-facing documentation matches it, and no checkbox is supported only by a source-code inspection or historical report.

---

## 5. Deferred, data-gated extensions

These extend review items 26 and 35. They are not prerequisites for the compact dashboard and must not hold up R1–R3. Do not show fabricated placeholders as working analytics. Synthetic fixtures prove code behaviour, not provider coverage.

### D01 — Prove market/FX history readiness and benchmark comparability

**Status:** [ ] Yahoo-first free-data route demonstrated on sample instruments; full-portfolio readiness NOT YET VALIDATED. **Dependencies:** T01 and T11 for integration; the isolated provider-validation slice can run independently. Review provider terms before persistent backfill; live refresh still requires explicit approval.

**Files:** Modify `backend/app/services/market_data_service.py`, `backend/app/services/market_data_coverage.py`, `backend/app/routers/market_data.py`, `backend/app/services/performance_service.py`, `backend/app/schemas.py`, `docs/market-data.md`; extend `backend/tests/test_market_data_service.py`, `backend/tests/test_market_data_regressions.py`; create `backend/tests/test_market_data_coverage.py`.

**Approach approved for planning:** pursue free Yahoo historical data first, not a paid feed. Reuse the existing provider/cache implementation where possible. Evaluate `yfinance` only if it materially improves the adapter; it is an unofficial client of the same source, not an independent fallback or rate-limit guarantee. Do not install it or replace the adapter merely to repeat a successful standard-library request.

**Fresh evidence — 2026-09-04:** sequential, unauthenticated requests to `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d` succeeded from this machine, with no API key/subscription. The first EQQQ probe was separate; the subsequent batch used two-second spacing and stopped on any HTTP 429.

| Requested symbol | Reported currency | Timestamp observations | Non-null adjusted closes |
|---|---|---:|---:|
| EQQQ.L | GBp | 507 | Series present; non-null count not measured |
| VUSD.L | USD | 507 | 505 |
| MU | USD | 502 | 502 |
| BA.L | GBp | 507 | 507 |
| VWRL.L | GBP | 507 | 504 |
| GBPUSD=X | USD (USD per GBP) | 524 | 519 |

The five batch responses and report were saved in `/tmp/stocks-free-data-probe/`; EQQQ evidence is the separate tool response, not part of that report. These are temporary evidence, not a durable cache. The batch spans roughly two years ending 2026-09-04; do not consume post-valuation or incomplete-session points in a model anchored to an earlier portfolio date. Observation counts and non-null adjusted-close counts do not establish finite/positive values, dividend correctness, aligned dates, licence rights, or the 80% portfolio-value gate. No portfolio DB write occurred. Earlier Yahoo 429/Stooq verification-page failures remain valid historical observations, not proof free data is permanently unavailable.

**Files, in addition to the existing paths above:** create `scripts/probe_market_history.py` and `backend/tests/test_market_history_probe.py` for reproducible bounded validation. For the manual fallback, create `backend/app/services/market_history_import_service.py` and `backend/tests/test_market_history_import.py`; extend `backend/app/routers/market_data.py` only after its import contract is tested. A UI import form is optional follow-up, not required to prove provider coverage.

**Implementation slices (each follows the §3 red/green/review cycle):**
1. **Make the probe reproducible.** Add offline fixtures for real response shapes, missing adjusted closes, errors, 429, malformed JSON, HTML disguised as success, and currencies. Probe script accepts explicit symbols/output directory and has bounded request count, pacing, per-request timeout and whole-run deadline. It writes only isolated evidence and never refreshes the live DB; stop on rate limiting, never rotate identities to evade it.
2. **Verify all current identities.** Build a source-to-provider mapping for every current non-cash security, benchmark and required FX pair; aggregate only verified duplicate exposure. Preserve original identifiers. The two specialist fund identifiers remain untested; report unresolved mappings rather than guess or assume exclusion is small enough to pass the gate.
3. **Backfill an isolated cache.** After terms review, request daily history sequentially, initially about two years, using the existing Yahoo adapter or a separately justified client. Retain provenance, raw/adjusted values, response currency, fetch time and revision metadata. Reject errors before cache promotion; retain previously valid data on failure.
4. **Validate the financial series.** Convert GBp/GBX correctly, use dated FX for USD series including London-listed VUSD.L, verify FX direction, filter to valuation date/completed observations, and exclude invalid/missing observations without invented forward fills. Audit corporate actions and dividend-adjustment basis; adjusted-close presence is not proof of a comparable total-return series.
5. **Measure portfolio readiness.** Generate covered/uncovered GBP value, unique securities, exclusions and reasons, actual intersection of valid dates, benchmark/FX basis, and valuation/staleness metadata. Apply the unchanged gate below. Persist a sanitised reproducible report in `docs/market-data.md`; do not declare readiness from the sample above.
6. **Refresh sparingly and serve offline.** Cache-first analytics; an explicit refresh control or separately approved daily/weekly schedule, not fetch-on-page-load. Use bounded retries/backoff, process-wide single-flight and atomic cache promotion. Refresh overlapping/full adjusted history periodically because corporate actions may revise old observations; audit revisions rather than blindly appending new dates.
7. **Provide a manual-data fallback.** Accept legitimately obtained broker/issuer CSV exports where available, with a declared schema for source, exact instrument ID, date, close, currency, adjustment basis and optional adjusted close. Validate provenance, duplicate/conflicting dates, units, finite values and coverage in a dry run before an approved import. Do not assume any broker or issuer actually offers the missing fund history until verified. Run imported data through the same quality gates; never silently splice incompatible sources/bases.
8. **Prove warm-cache operation.** With network disabled, analytics must still render valid cached results or precise unavailable/stale states. Test a 429/timeout during refresh leaves prior history intact. No dependency/package change or live refresh is authorised by this plan update.

**Free-source selection and limitations:** Yahoo is the practical first choice based on the successful probes, but unofficial access has no availability guarantee. Check Yahoo's applicable terms for intended personal use/storage; `yfinance`'s software licence is not a data licence. Twelve Data's London coverage is listed as Grow+, and Alpha Vantage's daily-adjusted endpoint is marked Premium, so neither is assumed to be a free equivalent for this portfolio. Stooq remains an unproven fallback after the earlier verification-page response. Do not purchase a plan or weaken the data-quality thresholds to get a green status.

**References checked during the review:** [yfinance project and usage caveats](https://github.com/ranaroussi/yfinance), [Twelve Data London coverage](https://twelvedata.com/exchanges/XLON), [Alpha Vantage endpoint documentation](https://www.alphavantage.co/documentation/). Recheck provider terms/entitlements before implementation.

Do not recreate existing cache models or install NumPy as if absent; inspect current dependencies first.

**Gate:** machine-readable holding, benchmark, and dated FX history covering at least 80% of current non-cash GBP value and at least 126 aligned daily observations. Report exclusions, actual aligned window, sources, adjustments, price/total-return basis, release timing/staleness, and all denominator values. A successful response for one symbol or an HTTP 200 HTML page is not coverage.

**Rules:** preserve exact requested symbols; map provider identifiers explicitly. Distinguish GBP/GBp/GBX; reject unknown currency or mixed price basis. Bound retries/deadlines and cross-request single-flight; failed refresh retains usable cache. No analytics GET triggers refresh. No live cache write until approval after isolated rehearsal.

**Benchmark acceptance:** actual portfolio/benchmark comparisons use the same currency, effective dates, and compatible return basis; disclose snapshot sampling and methodology. Never benchmark the current-price historical reconstruction. Proxy comparisons are labelled current-composition, not actual owned-portfolio outperformance. Realised relative statistics need at least 24 valid snapshot intervals; display limitations even then.

**Verify:** `.venv/bin/pytest backend/tests/test_market_data_service.py backend/tests/test_market_data_regressions.py backend/tests/test_market_data_coverage.py backend/tests/test_market_history_probe.py backend/tests/test_market_history_import.py -q`; measured isolated provider/cache report; rerun offline. Update `docs/market-data.md` with current evidence, not assumptions. Expected: offline tests pass, failed refresh preserves cache, and the report explicitly passes or fails the unchanged value/observation gates. Successful probe downloads alone do not complete D01.

### D02 — Complete current-composition risk and historical loss analysis

**Status:** [ ] BLOCKED on D01. **Dependencies:** D01, T02, T06–T08, T11, T15.

**Files:** Modify `backend/app/services/risk_service.py`, `backend/app/services/portfolio_risk_service.py`, `backend/app/routers/portfolio.py`, `backend/app/schemas.py`, `frontend/src/lib/api.ts`, `frontend/src/routes/PortfolioWorkspace.tsx`; create `frontend/src/components/RiskAnalysisPanel.tsx`, `frontend/src/components/__tests__/RiskAnalysisPanel.test.tsx`; extend `backend/tests/test_risk_service.py`, `backend/tests/test_risk_regressions.py`, `backend/tests/test_risk_panel_api.py`, `backend/tests/test_review_risk_fixes.py`.

**Slices:** complete typed coverage/exclusions contract → audit pure covariance/benchmark maths → accessible risk table/contribution chart → correlation table with redundant colour → rolling volatility → historical VaR/ES. Each slice gets its own red/green tests and review before the next.

**Methods/limits:** current-composition daily GBP proxy; 252 trading-day annualisation; 126 aligned observations for covariance/beta/tracking error; alpha/Information Ratio only with documented method and at least 252 paired observations. Keep actual snapshot risk separate; sparse actual observations must not masquerade as daily measurements. Model request lookback is bounded to 126–1825 days and displayed factor limit to 2–20; validate benchmark selections against configured identities.

Use Euler volatility contributions: `sigma = sqrt(w.T @ covariance @ w)` and `RC_i = w_i * (covariance @ w)_i / sigma`. Signed hedging contributions are valid. Explicitly distinguish full-book weights and analysed-sleeve weights. Covered + uncovered + cash must reconcile to the full portfolio. Missing history never has zero volatility; cash does. Model metric labels name the analysed sleeve and exclusions.

Historical loss analysis uses 1-day and 21-trading-day compounded returns. Define quantile convention, overlap dependence, positive-loss sign, tail sample minimum, and minimum-observation gate per horizon before implementation. Do not assume 126 daily observations alone are enough for a stable 21-day tail estimate. ES is the stated empirical tail mean; rolling volatility uses complete 21-day windows.

**Verify:** `.venv/bin/pytest backend/tests/test_risk_service.py backend/tests/test_risk_regressions.py backend/tests/test_risk_panel_api.py backend/tests/test_review_risk_fixes.py -q`; `npm --prefix frontend test -- --run RiskAnalysisPanel`; warm-cache offline API/browser checks. Cover equal/negative correlation, singular/flat/cash-only series, insufficient overlap, bad dates/currency/basis, non-finite values, aligned staleness, and exact reconciliation.

**Done when:** useful explanatory risk outputs are backed by coverage and finite typed data, not just an available-looking panel.

### D03 — Add reproducible, clearly labelled scenario fans

**Status:** [ ] BLOCKED on D01–D02 and separate acceptance of model assumptions. **Dependencies:** D02.

**Files:** Create `backend/app/services/forecast_service.py`, `backend/tests/test_forecast_service.py`, `backend/tests/test_portfolio_forecast_api.py`, `frontend/src/components/ForecastPanel.tsx`, `frontend/src/components/__tests__/ForecastPanel.test.tsx`; modify `backend/app/routers/portfolio.py`, `backend/app/schemas.py`, `frontend/src/lib/api.ts`, `frontend/src/routes/PortfolioWorkspace.tsx`.

**Slices:** deterministic pure bootstrap → bounded API → assumptions/readiness view → percentile fan → runtime/memory measurement.

**Contract:** moving-block bootstrap, default block size 20 trading days; horizons 3/6/12 months; 1000–50000 paths; seed 0 default; loss threshold 1–80%. Report p05/p25/p50/p75/p95 plus separately labelled terminal-loss and within-path drawdown-breach probabilities. Fixed cache, parameters, and seed produce deterministic results within the declared model/library version.

**Financial boundary:** model the covered invested sleeve only, with cash shown separately and held constant. Unsupported holdings stay visible outside the forecast; do not plot an analysed-sleeve fan starting at the full portfolio value or apply cash dilution twice. Future flows default explicitly to zero. State price/total-return basis and current-composition/survivorship bias. Percentiles are scenarios, not targets, promises, or expected returns.

**Verify:** `.venv/bin/pytest backend/tests/test_forecast_service.py backend/tests/test_portfolio_forecast_api.py -q`; `npm --prefix frontend test -- --run ForecastPanel`. Test flat/negative returns, percentile ordering, seed reproducibility, cash handling, unsupported exposure, parameter validation before array allocation, and gated unavailable state. Measure maximum supported request latency/peak memory before setting regression budgets.

### D04 — Add verified fund look-through and overlap

**Status:** [ ] DEFERRED until dated licensed constituent data is available. **Dependencies:** T15 and an approved data contract; independent of daily-price readiness.

**Files:** Create `backend/app/services/fund_exposure_service.py`, `backend/tests/test_fund_exposure_service.py`, `frontend/src/components/FundExposurePanel.tsx`, `frontend/src/components/__tests__/FundExposurePanel.test.tsx`; extend `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/routers/portfolio.py`, `frontend/src/lib/api.ts`; create a new dated constituent-cache Alembic revision during isolated implementation.

**Slices:** prove source rights/identifiers/as-of coverage → cache dated constituent weights → canonical underlying security mapping → weighted look-through aggregation → pairwise overlap with documented formula → accessible exposure table.

**Acceptance:** show coverage and unknown residual; no leverage/derivative/short exposure silently normalised into a long-only assumption. Disclose stale holdings data and fund reporting dates. Keep benchmark/theme similarity as labelled metadata, not measured overlap. Do not claim full underlying currency exposure without the necessary instrument/hedging data.

**Verify:** `.venv/bin/pytest backend/tests/test_fund_exposure_service.py -q`; `npm --prefix frontend test -- --run FundExposurePanel`; fixtures for partially disclosed funds, nested funds, duplicates, unknown constituents, stale dates, and sums that fail reconciliation.

---

## 6. Acceptance matrix and release checklist

### Required behavioural assertions

| Area | Acceptance evidence |
|---|---|
| Financial consistency | KPI/index/drawdown share canonical dates, scope and validity; explicit unavailable reasons; finite JSON; before-rounding identities tested. |
| Scope | Two accounts with different start/latest dates; account switching; same-date imports/corrections; historical backfill; filtered groups/orders; URL/back-forward. |
| Responsive | 320/390/768/1440px route checks; document width bounded; tabs/actions reachable; intentional table scroll; mobile detail visible. |
| Chart accuracy | Unique sparse ticks, no overlap, drawdown zero above losses, observation markers, correctly labelled baselines/units, no invented bridges. |
| Dashboard | Default height budgets with fixture; primary chart/status within first desktop viewport; no duplicate value-walk graph/tiles; relocated views reachable. |
| Accessibility | Keyboard/touch definitions, visible focus, skip link, drawer focus return, reduced motion, readable contrast, non-colour encodings and text alternatives. |
| Loading/failure | Slow/failed API, retry, empty account, valid zero, partial/stale data, missing history, invalid analysis and unavailable provider all tested distinctly. |
| Allocation | Security/position identity conservation; ambiguous mappings; cash exclusion disclosed; source currency caveat; exclusive target validation; scenario conservation. |
| Investigation | Contributor/category/group/Income links apply their promised filters; every order page reachable; no totals computed from capped rows. |
| Safety | DB backup verified; isolated build/rehearsal; no automatic live migrations/refreshes; source/DB preservation; deployment approval separate. |
| Gated models (conditional) | For a release shipping D02/D03, D01 coverage must actually pass; verify proxy labels, signed contributions, cash/exclusion reconciliation, horizon-specific sample gates, and bounded resources. R1–R3 instead verify truthful blocked/unavailable states and no leaked model payload; they do not require provider readiness. D04 has its own constituent-data gate. |

### Each release report must contain

- Completed task IDs with commands and observed results; outstanding tasks remain unchecked.
- Fresh backend/frontend test counts and static-diagnostic delta identities.
- Build output path and confirmation live `frontend/dist` was not overwritten.
- Browser route/viewport matrix, interaction results, console errors, and layout measurements.
- Separate labels for screenshot capture, image/manual inspection, and numerical correctness.
- Data coverage/valuation dates without unnecessarily publishing account names or balances.
- Known limitations, changed schema/URL behaviour, migration rehearsal results if relevant, rollback path, and explicit deployment status.

---

## 7. Traceability to the accepted review

The review's six initial defects are covered by T01–T04 and T15. Every numbered improvement is mapped below so later implementation cannot silently omit an item.

| Review item | Improvement | Task(s) |
|---|---|---|
| 1 | Smaller hero, analysis above fold | T05, T10 |
| 2 | Deliberate first-screen hierarchy | T10 |
| 3 | Compact non-duplicated attribution | T10, T12 |
| 4 | Shared primary period and explicit exceptions | T08, T09 |
| 5 | Secondary detail off dashboard | T10 |
| 6 | Evidence-backed attention | T11 |
| 7 | Less glass/glow | T05 |
| 8 | Readable typography | T05 |
| 9 | Stable semantic/category colours | T06 |
| 10 | Shared card/chart primitives | T05, T06 |
| 11 | Consistent compact/exact formatting | T06 |
| 12 | Immediate balance, reduced motion | T07 |
| 13 | Touch/keyboard metric definitions | T07 |
| 14 | Honest hero sparkline/reconstruction | T10 |
| 15 | Reasons for unavailable metrics | T01, T02 |
| 16 | Distinct return concepts/methods | T01, T02, T08, T09 |
| 17 | Honest sparse chart geometry | T03 |
| 18 | Source-linked event annotations | T14 |
| 19 | Useful contribution analysis | T12, T20 |
| 20 | Drawdown episodes | T13 |
| 21 | Combined-security exposure | T15 |
| 22 | Concentration without false safety | T15 |
| 23 | Donut legend/heading/drill-down improvements | T06, T15, T20 |
| 24 | Comparable target drift | T16 |
| 25 | Contribution-only scenario | T17 |
| 26 | Data-backed fund look-through | D04 |
| 27 | Cleaner holdings columns | T18 |
| 28 | Readable names preserving identifiers | T18 |
| 29 | Immediate mobile detail | T04, T19 |
| 30 | Context-preserving drill-downs | T12, T14, T20 |
| 31 | Remembered/deep-linkable views | T08, T18, T19, T20 |
| 32 | Complete paginated Orders and scoped totals | T21 |
| 33 | Income timing/comparison/drivers | T22 |
| 34 | Compact data confidence | T02, T09, T11, T22 |
| 35 | Genuine advanced-risk readiness gate | T11, D01, D02, D03 |

### Work deliberately not added

No new decorative treemap, restored value-walk graph, generic AI market commentary, stock-price prediction, efficient-frontier optimiser, suggested trades, full tax-engine rewrite, intraday feeds, or automatic live imports. Findings outside this accepted review should be separately scoped rather than quietly folded into the redesign.

### Recommended next action

Begin T00, then T01–T04. T05–T07 may proceed after the layout reproduction exists; T08–T09 can proceed alongside visual primitives with separate file ownership. Integrate T10 only after validity, scope, and shared UI foundations are tested. Then complete T11–T22 in dependency order and run T23 for each releasable batch. Keep D01–D04 visibly blocked/deferred until their own evidence gates pass.
