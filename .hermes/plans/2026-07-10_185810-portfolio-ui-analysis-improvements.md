# Portfolio UI and Analysis Improvements Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn the app from a collection of overlapping data screens into a compact, trustworthy personal portfolio workspace that answers: what is happening, why, what needs attention, and what should be reviewed next.

**Architecture:** Keep FastAPI, React, TanStack Query, and the existing database. Move account-aware calculations and financial metrics into backend services, expose one coherent analysis API, and reorganise the frontend around Dashboard, Portfolio, Activity, Tax, and Data maintenance. Preserve old URLs with redirects while consolidating their content into contextual tabs.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest, React 19, TypeScript, TanStack Query, React Router, Recharts, Tailwind, Vitest/Testing Library.

---

## Audit findings that drive the plan

### Current data/profile

- The live local database has 22 snapshots covering 2026-04-04 to 2026-07-05, 397 orders, 53 instruments (20 open), 3 accounts, 8 groups, and no unresolved orders.
- `ticker`, `sector`, `region`, and `asset_class` are populated for 0 of 53 instruments. Sector/region/asset allocation cannot yet produce useful output without a classification workflow.
- The app is explicitly single-user. Authentication, roles, audit-oriented navigation, and generic administration concepts are unnecessary.

### Organisation and redundancy

- Nine top-level routes compete for attention: Overview, Holdings, Orders, Positions, Import, Diff, Groups, Matching, and CGT.
- Holdings and Positions are two views of the same securities but use separate tables and separate mental models.
- Diff is a contextual detail of an import/snapshot, not a daily top-level destination.
- Groups are both portfolio analysis and configuration, but are placed under “Administration.”
- Matching is maintenance and currently has zero unresolved orders; it should appear when action is required rather than occupy permanent primary navigation.
- Import appears both in the sidebar and as a permanent topbar button.
- Overview repeats Cash deployed, DRIP, Sale proceeds, and Total orders from Orders without adding interpretation.
- Overview contains six different concerns in one 628-line route: account filtering, financial calculations, staleness, change detection, allocation, and performance.
- CGT defines a second local `StatCard` instead of using the shared component.

### Correctness and trust problems

- `Positions.tsx` does not apply the selected account to its position list.
- `Overview.tsx` applies account filtering to snapshot values but not to order analytics/cashflow. This can mix one account’s value with all accounts’ cashflows and return figures.
- `Orders.tsx` filters a client-side list capped at 500 orders, then reconstructs analytics in React. This will silently become incomplete and duplicates backend logic.
- “Effective return” is `current value + sales - cash deployed`; the displayed annualised figure treats total deployed cash as if invested on one date. It is not a defensible CAGR or money-weighted portfolio return.
- CGT sums all tax years and subtracts one hard-coded £3,000 allowance. Annual exemptions are per tax year, so “Taxable after exemption” can be materially wrong.
- The CGT allowance is hard-coded in the frontend as “2025-26,” while the page aggregates every year.
- The desktop sidebar is `hidden` below the `lg` breakpoint and there is no replacement mobile navigation.
- Market metadata and quote update APIs exist but are not exposed in the UI.
- Several decision badges in `HoldingsTable.tsx` use hard-coded frontend thresholds and labels such as “Top-up” and “Trim.” These are rules, not facts, and should be configurable/explainable.

---

## Product shape

### Primary navigation

1. **Dashboard** — value, reliable return, change attribution, attention items, concise allocation.
2. **Portfolio** — one security workspace with Holdings, Returns, Groups, and Closed tabs.
3. **Activity** — orders and snapshot changes; import history is contextual here.
4. **Tax** — tax-year-specific CGT analysis.
5. **Data** — import/fetch, matching exceptions, classifications, and personal calculation settings.

Keep a single prominent **Refresh/import** action in the topbar. Remove the duplicate sidebar Import item. Show a badge on Data only when matching/classification/import freshness needs attention.

### Dashboard hierarchy

1. Portfolio value and snapshot freshness.
2. Trustworthy return for selected account and period.
3. “Since the last snapshot”: contributions, withdrawals/sales, market movement, income proxy, and net value change.
4. “Needs attention”: stale snapshot, unresolved matching, missing classification, large allocation drift, and tax-year issues.
5. Performance chart with period selector and benchmark-relative result.
6. Allocation summary and top contributors/detractors.

Do not repeat order counts and raw transaction totals unless they explain a change.

---

## Phase 0 — Correctness before redesign

### Task 1: Make every analysis endpoint account-aware

**Objective:** Ensure the global account selector produces internally consistent data everywhere.

**Files:**
- Modify: `backend/app/routers/orders.py`
- Modify: `backend/app/services/order_service.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/routes/Overview.tsx`
- Modify: `frontend/src/routes/Orders.tsx`
- Modify: `frontend/src/routes/Positions.tsx`
- Test: `backend/tests/test_order_service.py`
- Create: `frontend/src/routes/__tests__/account-filtering.test.tsx`

**Steps:**
1. Add `account_name: str | None` to `/api/orders`, `/api/orders/positions`, and `/api/groups/performance` as needed.
2. Apply account filtering in SQL/service code before limits or aggregation.
3. Extend `api.getOrders`, `api.getOrderPositions`, and `api.getGroupPerformance` to accept `accountName`.
4. Pass `accountFilter` to analytics, cashflow, orders, positions, and group performance queries.
5. Delete the client-side reconstruction of `OrderAnalytics` in `Orders.tsx`; render backend results only.
6. Add backend tests with two accounts proving totals, positions, and the limited order list cannot leak across accounts.
7. Add a frontend test that changes the account preference and verifies all query keys and calls include the account.

**Verification:**
- `cd backend && ../.venv/bin/pytest tests/test_order_service.py -q`
- `cd frontend && npm test -- --run account-filtering`
- Manually select each of the three accounts and confirm Overview, Portfolio, Activity, and Tax totals all change consistently.

**Commit:** `fix: make portfolio analytics account-aware`

### Task 2: Replace misleading portfolio return labels and calculations

**Objective:** Provide a backend-computed portfolio return that respects cashflow timing and clearly identifies its method.

**Files:**
- Modify: `backend/app/services/order_service.py`
- Modify: `backend/app/services/portfolio_service.py`
- Modify: `backend/app/routers/portfolio.py`
- Modify: `backend/app/schemas.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/routes/Overview.tsx`
- Test: `backend/tests/test_portfolio_service.py`

**Steps:**
1. Add a `PortfolioReturnSummary` schema containing period start/end, start/end value, external contributions, withdrawals, Modified Dietz return, annualised return when valid, and data-quality notes.
2. Implement portfolio-level Modified Dietz using snapshot boundary values and only external cashflows. Treat DRIP as internal. Document the current assumption for sale proceeds because the data does not distinguish withdrawals from cash retained in an account.
3. Do not call the result CAGR. Label it “Money-weighted return (Modified Dietz).”
4. Add `/api/portfolio/returns?account_name=&from=&to=`.
5. Remove `effectiveReturn`, `effectiveReturnPct`, and `annualisedReturnPct` calculations from React.
6. Render `—` plus a concise explanation when the available data cannot support a defensible return.
7. Test no cashflows, same-day cashflows, multiple contributions, DRIP exclusion, and account filtering.

**Verification:** `cd backend && ../.venv/bin/pytest tests/test_portfolio_service.py -q`

**Commit:** `feat: add trustworthy portfolio return analysis`

### Task 3: Correct CGT presentation by tax year

**Objective:** Prevent cross-year aggregation and hard-coded allowance errors.

**Files:**
- Modify: `backend/app/services/cgt_service.py`
- Modify: `backend/app/schemas.py`
- Modify: `frontend/src/routes/CGT.tsx`
- Modify: `frontend/src/components/StatCard.tsx`
- Test: `backend/tests/test_cgt_service.py`

**Steps:**
1. Add a backend allowance table keyed by UK tax year, with an explicit fallback of `None` rather than guessing.
2. Return `annual_exempt_amount`, `net_gain`, and `gain_after_losses_and_exemption` on each tax-year summary.
3. Add a tax-year selector defaulting to the current/latest year with sales.
4. Make all headline cards reflect the selected tax year only.
5. Remove the frontend `const exemptGainAmount = 3000` and the all-years subtraction.
6. Reuse the shared `StatCard`; extend its tone API if necessary.
7. Add a visible “Estimate only” note and a data-completeness warning when unmatched or ignored taxable orders exist.
8. Add tests spanning at least two tax years with different exemptions.

**Verification:** `cd backend && ../.venv/bin/pytest tests/test_cgt_service.py -q`

**Commit:** `fix: calculate CGT allowance per tax year`

---

## Phase 1 — Simplify information architecture

### Task 4: Introduce the consolidated route structure

**Objective:** Reduce permanent navigation while preserving existing deep links.

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/layout/Sidebar.tsx`
- Modify: `frontend/src/layout/Topbar.tsx`
- Create: `frontend/src/routes/Portfolio.tsx`
- Create: `frontend/src/routes/Activity.tsx`
- Create: `frontend/src/routes/Data.tsx`
- Modify: `frontend/src/routes/Holdings.tsx`
- Modify: `frontend/src/routes/Positions.tsx`
- Modify: `frontend/src/routes/Orders.tsx`
- Modify: `frontend/src/routes/Import.tsx`
- Test: `frontend/src/__tests__/routing.test.tsx`

**Steps:**
1. Add routes `/portfolio`, `/activity`, `/tax`, and `/data`.
2. Make `/holdings`, `/positions`, `/orders`, `/import`, `/diff`, `/groups`, `/matching`, and `/cgt` redirect to the equivalent new tab/query string.
3. Change sidebar labels to Dashboard, Portfolio, Activity, Tax, Data.
4. Remove “Daily” and “Administration”; those categories are inappropriate for one user.
5. Keep one topbar Refresh/import action that opens `/data?tab=import`.
6. Add attention counts to Data using the existing matching summary and missing-classification count.
7. Add route tests for every legacy redirect.

**Verification:** `cd frontend && npm test -- --run routing && npm run build`

**Commit:** `refactor: consolidate portfolio navigation`

### Task 5: Build a responsive navigation shell

**Objective:** Make every route reachable below the desktop breakpoint.

**Files:**
- Modify: `frontend/src/layout/AppShell.tsx`
- Modify: `frontend/src/layout/Sidebar.tsx`
- Modify: `frontend/src/layout/Topbar.tsx`
- Create: `frontend/src/layout/MobileNav.tsx`
- Test: `frontend/src/layout/__tests__/navigation.test.tsx`

**Steps:**
1. Add a compact bottom navigation or menu drawer for Dashboard, Portfolio, Activity, Tax, and Data.
2. Collapse the topbar account selector into a select/menu on narrow screens.
3. Ensure DRIP settings and refresh/import remain reachable without horizontal overflow.
4. Add keyboard focus, active-route labels, `aria-current`, and 44px touch targets.
5. Test desktop and mobile route access.

**Verification:**
- `cd frontend && npm test -- --run navigation && npm run build`
- Browser widths: 390px, 768px, 1280px; verify no horizontal page scroll.

**Commit:** `feat: add responsive portfolio navigation`

---

## Phase 2 — One coherent portfolio workspace

### Task 6: Merge Holdings and Positions into Portfolio tabs

**Objective:** Let one row represent one security, with snapshot, cost, return, and income information available without switching pages.

**Files:**
- Modify: `frontend/src/routes/Portfolio.tsx`
- Create: `frontend/src/components/portfolio/PortfolioTable.tsx`
- Create: `frontend/src/components/portfolio/PortfolioDetailDrawer.tsx`
- Move/refactor: `frontend/src/components/HoldingsTable.tsx`
- Move/refactor: `frontend/src/components/PositionAnalysis.tsx`
- Move/refactor: `frontend/src/components/InstrumentDetail.tsx`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/components/portfolio/__tests__/PortfolioTable.test.tsx`

**Steps:**
1. Add tabs: Holdings, Returns, Groups, Closed.
2. Use one common instrument identity and selection state across tabs.
3. Holdings columns: security, account, value, weight, snapshot delta, unrealised P&L.
4. Returns columns: security, external cost, DRIP, current value, money-weighted return, drawdown.
5. Closed columns: proceeds, matched cost, realised gain, holding period.
6. Open a drawer/detail panel with history, orders, group memberships, metadata, and quote state.
7. Keep search, account selection, sorting, and selected instrument in URL parameters.
8. Remove duplicated standalone tables once parity is verified.

**Verification:** `cd frontend && npm test -- --run PortfolioTable && npm run build`

**Commit:** `refactor: unify holdings and position analysis`

### Task 7: Move Groups into portfolio context

**Objective:** Make groups useful for analysis and editing without a separate administration page.

**Files:**
- Modify: `frontend/src/routes/Portfolio.tsx`
- Refactor: `frontend/src/components/GroupsSection.tsx`
- Refactor: `frontend/src/components/GroupPerformancePanel.tsx`
- Modify: `backend/app/services/order_service.py`
- Test: `backend/tests/test_order_service.py`

**Steps:**
1. Combine group allocation, performance, targets, and membership editing in the Portfolio > Groups tab.
2. Show current weight, target, drift in percentage points, and rebalance gap in GBP.
3. Replace the current client-side account recomputation with an account-aware backend result.
4. Add “unassigned” as a first-class row so missing grouping is visible.
5. Keep edit controls inline because there is only one user and no approval workflow.

**Verification:** Backend group tests plus frontend build; group weights should sum to expected totals for each account.

**Commit:** `feat: integrate group analysis and targets`

---

## Phase 3 — Make the dashboard analytical

### Task 8: Add snapshot change attribution

**Objective:** Explain value changes rather than merely listing changed holdings.

**Files:**
- Create: `backend/app/services/attribution_service.py`
- Create: `backend/app/routers/analysis.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas.py`
- Create: `backend/tests/test_attribution_service.py`
- Create: `frontend/src/components/dashboard/ChangeAttribution.tsx`
- Modify: `frontend/src/routes/Overview.tsx`

**Steps:**
1. For two snapshot dates, calculate opening value, closing value, net external flow, sale proceeds, DRIP proxy, residual market movement, and reconciliation difference.
2. Return per-instrument contributors/detractors and data-quality flags.
3. Explicitly label DRIP as a reinvestment proxy because the dataset records purchases, not dividend declarations.
4. Replace the current “What changed” counts/top movers card with a waterfall-style summary and top reasons.
5. Link quantity changes to the relevant Activity orders and price/value movement to the Portfolio detail.
6. Test exact reconciliation and missing-order cases.

**Verification:** `cd backend && ../.venv/bin/pytest tests/test_attribution_service.py -q`

**Commit:** `feat: explain portfolio changes between snapshots`

### Task 9: Rebuild Overview as a focused dashboard

**Objective:** Remove raw-data redundancy and place decision-relevant information first.

**Files:**
- Modify: `frontend/src/routes/Overview.tsx`
- Create: `frontend/src/components/dashboard/PortfolioHeader.tsx`
- Create: `frontend/src/components/dashboard/AttentionList.tsx`
- Create: `frontend/src/components/dashboard/PerformancePanel.tsx`
- Create: `frontend/src/components/dashboard/AllocationSummary.tsx`
- Refactor: `frontend/src/components/ChartPanel.tsx`
- Refactor: `frontend/src/components/PerformersSection.tsx`
- Test: `frontend/src/routes/__tests__/Overview.test.tsx`

**Steps:**
1. Reduce Overview to orchestration and query composition; move sections into focused components.
2. Header: value, selected period return, account, and snapshot freshness.
3. Attention list: stale snapshot, matching exceptions, missing classification, large target drift, tax warning.
4. Change attribution immediately follows the header.
5. Performance panel: 1M, 3M, YTD, 1Y, since-inception selector; show portfolio return and relative benchmark result.
6. Allocation summary: top positions and group drift only; deep analysis links to Portfolio > Groups.
7. Replace “best/worst % movers” with top contribution/detraction where sufficient data exists.
8. Remove Cash deployed, DRIP reinvested, Sale proceeds, Total orders cards from Dashboard; keep them in Activity/Income context.

**Verification:** Overview component tests, production build, and a browser review at three responsive widths.

**Commit:** `refactor: focus dashboard on decisions and attribution`

---

## Phase 4 — Unlock deeper analysis from existing fields

### Task 10: Add a classification workflow

**Objective:** Populate the currently empty ticker/sector/region/asset-class fields so allocation analysis becomes useful.

**Files:**
- Modify: `frontend/src/routes/Data.tsx`
- Create: `frontend/src/components/data/ClassificationQueue.tsx`
- Modify: `frontend/src/components/portfolio/PortfolioDetailDrawer.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `backend/app/routers/instruments.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_instruments.py`

**Steps:**
1. Add Data > Classifications listing incomplete open instruments first.
2. Support inline ticker, asset class, sector, and region editing using the existing PATCH endpoint.
3. Add bulk apply for repeated funds/securities only where the user explicitly chooses it.
4. Show completion progress (currently 0/53 across all four metadata fields).
5. Expose quote refresh only for instruments with a ticker and show fetch date/error.
6. Do not automatically infer classifications without review; incorrect financial classification is worse than missing data.

**Verification:** Save, reload, and confirm each classification persists and appears in Portfolio detail.

**Commit:** `feat: add instrument classification workflow`

### Task 11: Add allocation and concentration analysis

**Objective:** Analyse concentration by holding, account, group, asset class, sector, and region.

**Files:**
- Create: `backend/app/services/allocation_service.py`
- Modify: `backend/app/routers/analysis.py`
- Modify: `backend/app/schemas.py`
- Create: `backend/tests/test_allocation_service.py`
- Create: `frontend/src/components/portfolio/AllocationAnalysis.tsx`
- Modify: `frontend/src/routes/Portfolio.tsx`

**Steps:**
1. Calculate weights, top-1/top-5 concentration, Herfindahl index, group target drift, and GBP rebalance gaps.
2. Return an explicit “unclassified” bucket for every taxonomy.
3. Add Portfolio > Allocation subview with a taxonomy selector.
4. Keep thresholds descriptive by default (“top position is 24%”), not prescriptive (“sell”).
5. Allow personal warning thresholds in Data > Preferences later, but do not hard-code investment advice.

**Verification:** Tests must prove weights reconcile to 100% excluding/including cash according to an explicit option.

**Commit:** `feat: add portfolio allocation analysis`

### Task 12: Add an income/DRIP analysis view

**Objective:** Make reinvested income trends visible while accurately describing data limitations.

**Files:**
- Modify: `backend/app/services/order_service.py`
- Modify: `backend/app/routers/analysis.py`
- Modify: `backend/app/schemas.py`
- Create: `backend/tests/test_income_analysis.py`
- Create: `frontend/src/components/portfolio/IncomeAnalysis.tsx`
- Modify: `frontend/src/routes/Portfolio.tsx`

**Steps:**
1. Aggregate DRIP-classified purchases by month/year, account, and instrument.
2. Add trailing-12-month DRIP proxy, growth vs prior 12 months, yield on current value, and yield on discretionary cost.
3. Label every amount “DRIP/reinvested-income proxy,” not dividends, because the source lacks declared/cash dividend records.
4. Add a threshold sensitivity indicator so totals visibly depend on the DRIP threshold.
5. Move the global DRIP threshold from the always-visible topbar into Data > Preferences, with a small context link from Income.

**Verification:** Test threshold boundaries, account filtering, and no-order states.

**Commit:** `feat: add DRIP income analysis`

---

## Phase 5 — Activity and maintenance cleanup

### Task 13: Combine orders, changes, and import history

**Objective:** Make Activity a chronological explanation layer rather than three disconnected routes.

**Files:**
- Modify: `frontend/src/routes/Activity.tsx`
- Refactor: `frontend/src/components/OrderHistorySection.tsx`
- Refactor: `frontend/src/components/ImportHistory.tsx`
- Refactor: `frontend/src/routes/Diff.tsx`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/routes/__tests__/Activity.test.tsx`

**Steps:**
1. Add Activity tabs: Orders, Snapshot changes, Imports.
2. Keep Diff as a nested comparison panel opened from Snapshot changes/Imports.
3. Add filters for account, date range, side, DRIP, and security.
4. Link each order to its Portfolio instrument detail.
5. Keep import/fetch controls in Data, while Activity shows the immutable history/results.

**Verification:** Frontend tests and legacy `/diff` redirect with query parameters preserved.

**Commit:** `refactor: combine portfolio activity views`

### Task 14: Make matching exception-driven

**Objective:** Hide complex matcher administration when there is nothing to resolve.

**Files:**
- Modify: `frontend/src/routes/Data.tsx`
- Refactor: `frontend/src/routes/MatchingAdmin.tsx`
- Create: `frontend/src/components/data/MatchingQueue.tsx`
- Modify: `frontend/src/components/MatchingWarningBanner.tsx`

**Steps:**
1. Show only an exception queue by default: unmatched, low-confidence, ignored, and reconciliation mismatches.
2. Move aliases and audit history into an Advanced disclosure.
3. Remove matching warning banners from every major route; use the Dashboard attention list and Data badge instead.
4. Split the 1,073-line route into queue, aliases, reconciliation, and audit components.
5. Preserve all existing resolver operations and audit history.

**Verification:** Resolve, reassign, ignore, and unmatch one test order; confirm query invalidation updates Dashboard/Data badges.

**Commit:** `refactor: make matching maintenance exception-driven`

---

## Phase 6 — Shared UI quality and guardrails

### Task 15: Add frontend tests and remove duplicated primitives

**Objective:** Make the redesign safe to evolve.

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Modify: `frontend/src/components/StatCard.tsx`
- Create: `frontend/src/components/PageHeader.tsx`
- Create: `frontend/src/components/DataTable.tsx`
- Refactor: affected routes/components

**Steps:**
1. Add Vitest, jsdom, and React Testing Library.
2. Add tests for route access, account filtering, empty/loading/error states, URL-backed filters, and key financial labels.
3. Replace CGT’s local StatCard and repeated page headers/select styles with shared components.
4. Add query error states; many current routes only handle loading or empty data.
5. Run TypeScript checking explicitly (`tsc --noEmit`) because Vite build alone does not provide complete regression coverage.

**Verification:** `cd frontend && npx tsc --noEmit && npm test -- --run && npm run build`

**Commit:** `test: add frontend coverage and shared UI primitives`

### Task 16: Remove hard-coded investment actions

**Objective:** Keep the app analytical without presenting brittle rules as recommendations.

**Files:**
- Modify: `frontend/src/components/HoldingsTable.tsx` or successor `PortfolioTable.tsx`
- Create: `backend/app/services/attention_service.py`
- Modify: `backend/app/routers/analysis.py`
- Create: `backend/tests/test_attention_service.py`
- Modify: `frontend/src/routes/Data.tsx`

**Steps:**
1. Replace “Top-up data” and “Trim data” with neutral facts: drawdown, gain, quantity unchanged, and target gap.
2. Move alert thresholds to a documented backend/personal preference model if the user wants them.
3. Every attention item must expose its evidence and be dismissible for this single-user installation.
4. Never generate buy/sell instructions from simple thresholds.

**Verification:** Tests prove alerts change when personal thresholds change and always include evidence.

**Commit:** `refactor: make portfolio alerts factual and explainable`

---

## Recommended implementation order

1. Tasks 1–3: correctness and financial trust.
2. Tasks 4–5: navigation and responsive access.
3. Tasks 6–7: unified Portfolio workspace.
4. Tasks 8–9: analytical Dashboard.
5. Task 10: classification; complete metadata for the 20 open instruments first.
6. Tasks 11–12: allocation and income analysis.
7. Tasks 13–14: Activity and Data maintenance consolidation.
8. Tasks 15–16: test coverage, shared primitives, and alert guardrails throughout (start Task 15’s tooling before major frontend refactors if practical).

## Deliberately deferred

- Multi-user authentication, permissions, teams, audit approval workflows, and cloud tenancy.
- Intraday/live trading views; the source data is snapshot- and order-history-based.
- Volatility, Sharpe ratio, beta, and daily VaR until reliable historical market prices exist. Sparse snapshots and current-price backfills cannot support these honestly.
- Automated buy/sell advice.
- Automatic security classification without user review.
- A precise tax liability estimate without taxable income/rate context and complete broker data.

## Final validation checklist

- All backend tests pass: `cd backend && ../.venv/bin/pytest -q`.
- Ruff/type checks pass using the repository’s configured commands.
- Frontend passes `npx tsc --noEmit`, Vitest, and `npm run build`.
- Account totals reconcile independently for all three accounts and the combined view.
- Portfolio value changes reconcile to attributed flows plus market movement.
- CGT headline cards display one selected tax year and that year’s allowance only.
- Every legacy route redirects without losing instrument/batch query parameters.
- All five primary destinations are reachable at 390px width.
- No headline metric is calculated ad hoc in React when a backend financial service should own it.
- Empty, stale, partial, and classification-missing states explain data quality rather than displaying confident but incomplete numbers.
