# Stocks UI and Service Improvement Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after approval.

**Goal:** Make the portfolio easier to understand and investigate on desktop/mobile, while making refresh results and financial data trustworthy.

**Architecture:** Retain React/TanStack Query/Recharts and the FastAPI service. Improve the existing workflows rather than adding more pages. Keep authoritative financial calculations server-side and retain service-account isolation; no broker secrets or live database permissions for the chat agent.

**Tech Stack:** React 19, TypeScript, Tailwind, Recharts, Vitest/Testing Library, FastAPI, SQLAlchemy/SQLite, pytest, Playwright, systemd/Polkit.

**Status:** Implementation authorized by Geoff on 29 September 2026; in progress on `feat/ui-service-improvements-20260929`. Geoff requires a testable preview before production and is unavailable for several hours. Production deployment, privileged policy installation, live broker refreshes, and real-data migration are **not authorized** by this implementation approval. Existing unrelated dirty documentation is preserved. This audit plan supplements previously accepted roadmaps. Baseline evidence is recorded in `docs/verification/2026-09-29-improvement-baseline.md`; every A1–E5 acceptance task must be reconciled before sign-off.

**Preview acceptance gate:** Prepare a separately built, isolated local preview using explicitly labelled synthetic data (or an independently approved read-only representative snapshot). Do not connect it to production database, broker credentials, scheduled jobs or production authentication state. Provide Geoff the tested access/start instructions and a concise review checklist. Keep `/opt/stocks/current`, existing services, public proxy configuration and forwarding unchanged until he tests and separately approves a release.

---

## 1. Evidence and limits

Inspected 29 September 2026:
- Running release: `/opt/stocks/releases/stocks-passkeys-31590ff` via `/opt/stocks/current`.
- Checkout: `/home/geoff/code/stocks`, commit `77160ef`; the checkout is not the running release.
- Live app active; broker sync timer enabled/active. A timer being active or a service exiting zero does not establish account freshness.
- Public site reached at `https://solarpi.hopto.org:5000`; sign-in requires a passkey. Authenticated production screens and live records were not accessed.
- Built checkout UI into an isolated scratch directory. Eight route/viewport checks used a consistent read-only copy of the historical development database: Overview, Holdings, Performance, Allocation at 390px and 1440px. Source database checksum remained unchanged; no broker requests, startup migrations, or production writes.
- Six checks passed the harness contracts. Two Performance checks rendered but failed a fixture-dependent source-order navigation expectation: the tested window had no source-order link. This is not proof of a broken production link.
- All eight measured routes had no document-wide horizontal overflow. This does not mean every UI workflow is ideal.
- Overview, PerformancePanel and stylesheet source matched the deployed versions; Topbar differed. Production adds authentication/passkey code not present in the checkout. Preserve those differences during implementation.
- Visually inspected desktop/mobile Overview and desktop Holdings screenshots. The mobile Overview was 3578px tall with the primary chart starting near 1500px; desktop Overview chart started near 844px in a 1000px-high rehearsal viewport. These are observations on one historical fixture, not universal layout measurements.
- Backend findings below are code-traced risks; no assertion that live account records are currently corrupted. Live account/cash/market-data completeness remains unknown.
- Full frontend/backend test suites were not run for this audit. An isolated frontend production build succeeded, with a roughly 1.07 MB minified initial JavaScript chunk and the Vite chunk-size warning.

Private evidence stays outside Git at `/home/geoff/.hermes/cache/scratch/stocks-review-evidence/`. Do not commit screenshots, historical balances, raw account identifiers, or DB copies. Scratch evidence may expire; rerun acceptance checks before implementation sign-off.

## 2. Recommended direction

Keep the current dark visual language, but move from a text-heavy analytical report to a calm portfolio workspace. Improve hierarchy before changing branding.

### Overview: answer five questions in order
1. **Can I trust this view?** Compact freshness strip: verified observation age, mixed valuation dates, partial refresh, and critical issue count. State the difference between last checked and last valuation.
2. **What is my portfolio worth?** One dominant portfolio-value metric; secondary selected-period return and net external flows with explicit dates/method.
3. **How has it performed?** Main chart immediately after the KPI row; one concise caveat plus a labelled methodology disclosure.
4. **What changed?** Compact latest-snapshot reconciliation and top contributors; its own dates remain visibly separate from the selected performance period.
5. **Where should I investigate?** Allocation highlights, actionable exceptions, links to holdings and detailed analysis.

Desktop composition:
- Header/account/period controls + compact freshness strip.
- Dominant value and two quieter supporting metrics.
- Main chart beside a short 'Latest snapshot changes' panel.
- Allocation and relevant exceptions below; methodology/evidence on demand.

Mobile composition:
- Compact controls and freshness.
- Portfolio value, two secondary metrics in a readable compact arrangement.
- Chart, then latest changes, then allocation.
- Expandable 'Calculation and data limitations' sections rather than repeated paragraphs before the chart.

Keep essential caveats visible: carried-forward valuations, estimated/proxy flows, actual covered dates, unavailable calculations, and a snapshot series not being a daily measured path. Never hide a critical warning in an accordion or imply deposits are investment gains. Use progressive disclosure for repeated explanations, not for validity failures.

### Holdings: a full-width investigation workspace
- Full-width table when no holding is selected; remove the permanent empty detail pane.
- On selection, use a closable drawer or deliberate split view on sufficiently wide desktops; retain the accessible mobile detail dialog and deep-linked `inst` selection.
- Default columns: name, account, value, weight, unrealised gain/loss. Classification and technical columns are optional.
- Use readable account aliases in display only; preserve canonical account identity and legacy import fingerprints.
- Visible active-filter chips, filtered count versus account-scope count, and an explicit clear-filters action.
- Separate resetting sort/columns from clearing investigation filters. Account/period must survive either action.

### Navigation and design system
- Keep existing Dashboard, Portfolio, Activity, Tax, Data, Help destinations; do not add another analytics landing page.
- Rename 'Returns' to 'Holding returns' where it means lifetime holding returns; keep selected-period portfolio performance distinct.
- Consistent typography, numeric alignment, spacing, border strength, positive/negative semantics, and readable secondary text. Keep a restrained cyan accent; colour must not be the sole signal.
- Validate six-item mobile navigation at 320/390px and 200% zoom before deciding whether Help/Tax belong under a More menu. Existing mobile navigation is present, not missing.
- Preserve skip links, reduced motion, focus management, safe-area padding, accessible allocation tables, and legacy route redirects.

## 3. Priority findings

### P0: financial integrity gates before new analytical claims

**F01: Omitted Trading 212 positions can become closed holdings.**
Evidence: deployed `backend/app/services/trading212.py:216–256` passes mapped rows directly into snapshot ingest; `import_service.py:341–355` closes absent prior instruments. Implement independently verified completeness or an explicit reviewed closure path; do not permanently block genuine sales without a supported resolution workflow.

**F02: Unavailable Trading 212 cash can disappear from reconstructed valuation.**
Evidence: `trading212.py:220–255` tolerates denied account summary and preserves the CASH identifier; `import_service.py:344–346` preserves its open status only, while `valuation_service.py:69–72` replaces the account snapshot state. Reject the incomplete observation or carry forward last verified cash with explicit stale provenance. Open instrument status alone is insufficient.

**F03: HL parser/download pairs are not uniformly fail-closed.**
Evidence: deployed `hl_parser.py:41–48,81–88,101–102,183–202`; `fetchers/hl.py:148–159`. Validate finite values and every nonempty export row; reconcile export counts/totals; stage holdings/activity as a coherent account batch. Independent brokers may still succeed independently.

### P1: truthful states and daily usability

**F04: A successful service exit is not a successful refresh.**
Evidence: deployed `sync_cli.py:77–79` accepts any ok/unchanged step; `sync_runner.py:203–213` reports empty inbox as unchanged. Add complete/partial/failed/no-op/disabled outcomes and distinguish verified unchanged broker observations from 'nothing to import'. Rejected files must be visible failures/attention, not silently treated as success.

**F05: Loading/errors can look like an empty holdings list.**
Evidence: checkout `frontend/src/routes/Holdings.tsx:31–38,58,106–113`, `components/HoldingsTable.tsx:47`; similar defaults in `routes/Groups.tsx`. Pending, empty, filtered-empty and failed must be separate, with retry actions and independently qualified unavailable weights.

**F06: Filter/reset behaviour is misleading.**
Evidence: `frontend/src/lib/holdingsView.ts:13–32`, `components/HoldingsTable.tsx:29`, `lib/investigationLinks.ts:5–11`. Display active investigation filters and implement correctly labelled clear/reset actions.

**F07: Refresh freshness and status are fragmented.**
Evidence: deployed `routers/sync.py:110–139`, `sync_control.py:180–207`. Snapshot date, last verified check, last attempt, service state and next scheduled run are different concepts. Publish one safe structured status contract with account/section coverage and actionable reason codes. Record unchanged observations; detect same-day A→B→A as a new latest observation rather than historical duplicate.

**F08: Dashboard hierarchy and empty holdings pane reduce usability.**
Evidence: visually inspected rehearsal screenshots; `routes/Overview.tsx:54–87`, `components/PerformancePanel.tsx`, `routes/Holdings.tsx:104–119`. Repeated methodology precedes the chart; the unselected detail pane consumes two of five desktop grid columns.

### P2: resilience, accessibility and performance
- Inbox read/archive exceptions can bypass later independent brokers and terminal reporting: deployed `sync_all_service.py:144–192`, `sync_runner.py:197–220`.
- Bound Trading 212 runtime/retries/history pagination to service budgets; honour Retry-After without unbounded retry. Preserve cancellation-safe transactions.
- Complete workspace tab semantics or use navigation links consistently; unknown tab values must select the displayed view. `frontend/src/components/WorkspaceTabs.tsx:28–52`, `routes/PortfolioWorkspace.tsx:21–40`.
- Preserve account/period in the classification CTA: `components/AllocationAnalysisPanel.tsx:106` currently uses an unscoped URL.
- Decouple independent raw snapshot history from order/reconstruction failures; avoid eager queries for unused history modes. `routes/PerformanceWorkspace.tsx:29–35,56–59`.
- Add drawdown point inspection and an accessible observation table; source-backed timeline links must remain usable when a category has zero events.
- Reconcile deployed service-account isolation and daily timer settings with checkout templates. Do not deploy older shared-identity templates over hardened live units.
- Route-split the current initial bundle only after recording load/request/layout-shift baselines.

## 4. Delivery sequence and task map

Each implementation task follows test-first steps: write failing acceptance test, run it, make the smallest implementation, rerun targeted tests, then make a scoped commit. Break migration/schema work into separate reviewed changes. Paths below are relative to the checkout unless stated otherwise; reconcile deployed release deltas before applying them.

### Gate A — Baseline and integrity (F01–F03)
**A1: Establish deployed-source baseline.** Record frontend/auth/backend differences, effective systemd units and existing tests without secrets. Obtain an operator-approved consistent read-only live DB snapshot or sanitized representative fixture; no permission widening. Create `docs/verification/2026-09-29-improvement-baseline.md`. Compare fixture calculations and record known limitations.
**A2: Snapshot omission test/gate.** Modify `backend/app/services/trading212.py`; extend `backend/tests/test_trading212.py`, `test_trading212_transactions.py`. Omit one otherwise valid position and assert no closures or partial snapshot/orders/cash writes. Add positive genuine-closure resolution test.
**A3: Missing-cash test/policy.** Modify Trading 212 ingest and, if carrying cash, canonical valuation/provenance handling. Extend `test_trading212_cash.py`, `test_portfolio_service.py`. Prior verified cash + 403 must reject transaction or preserve visibly stale qualified cash, never silently lower valuation.
**A4: Strict HL parsing.** Modify `backend/app/services/hl_parser.py`; extend `test_hl_parser.py` for NaN/infinity, invalid headers, truncated nonempty rows and totals mismatch.
**A5: HL batch atomicity.** Modify `backend/app/fetchers/hl.py`, `services/sync_runner.py` and canonical import boundary as needed. Extend `test_sync_runner.py`, `test_sync_all_service.py` for second-download/final-import failure and full rollback within that broker batch.
**Acceptance:** isolated regressions reproduce and then resolve the risks. Confirm no production writes and no changes to economic event fingerprints without migration/deduplication analysis.

### Gate B — Truthful UI states and control semantics (F05–F06)
**B1:** Loading/error/empty/filtered-empty states in `routes/Holdings.tsx`, `routes/Groups.tsx`, `components/HoldingsTable.tsx`; extend `routes/__tests__/Holdings.test.tsx`, create `routes/__tests__/Groups.test.tsx`.
**B2:** Filter chips and split clear/reset controls; modify `lib/holdingsView.ts`, `components/HoldingsTable.tsx`; extend `lib/__tests__/holdingsView.test.ts`, `components/__tests__/HoldingsTable.test.tsx`, `investigationIntegration.test.tsx`.
**B3:** Complete tabs and unknown-tab validation; modify `components/WorkspaceTabs.tsx`, `routes/PortfolioWorkspace.tsx` and sibling workspaces as needed; extend `WorkspaceTabs.test.tsx`, create `routes/__tests__/PortfolioWorkspace.test.tsx`.
**B4:** Scope-preserving classification navigation; modify `components/AllocationAnalysisPanel.tsx`; extend its test and `state/__tests__/useAnalysisScope.test.tsx`.
**Acceptance:** forced API failure cannot display 'No instruments match'; keyboard navigation is coherent; clear filters preserves account/period; scoped links survive account changes.

### Gate C — UI redesign slice (F08)
**C1:** Produce two static Overview/Holdings layout variants using labelled demo data, not fabricated real holdings. Select a direction before component implementation. Keep existing analytical methods and deep links.
**C2:** Split PerformancePanel into chart summary and methodology disclosure; modify `components/PerformancePanel.tsx`, `routes/Overview.tsx`; extend `components/__tests__/PerformancePanel.test.tsx`, `routes/__tests__/Overview.test.tsx`. Show invalid-state reasons above the chart; do not render a valid-looking curve when calculation is unavailable.
**C3:** Compact latest-change panel with separate comparison dates and expandable evidence; modify `components/AttributionSummaryCard.tsx`; extend its tests.
**C4:** Make unselected Holdings full width and selected details deliberate; modify `routes/Holdings.tsx`, `components/HoldingDetailPanel.tsx`, `HoldingsTable.tsx`; retain focus return, URL selection and mobile dialog tests.
**C5:** Consistent display density/type tokens; modify `src/index.css`, `layout/Topbar.tsx`, `MobileNav.tsx`, shared metric/table controls. Preserve deployed auth/logout controls. Add readable 'Holding returns' label and update embedded Help/tests.
**Acceptance targets:** at 390×844, main Overview chart starts within the initial viewport on the agreed representative normal fixture; at 1440×900 the main trend is visible without scrolling. Severe-warning fixtures may legitimately add height and must remain explicit. No document overflow at 320/390/720/1440px; key touch controls target 44px; keyboard/200% zoom checks pass. Empty selection must not reserve a large detail column. Shorter copy must not alter calculations or obscure critical limitations.

### Gate D — Refresh reliability and safe WhatsApp operation (F04,F07)
**D1:** Define refresh result/section status schema and outcome tests; modify `services/sync_runner.py`, `sync_cli.py`, `routers/sync.py`; create `backend/tests/test_sync_cli.py`, `test_sync_freshness.py`; extend `test_sync_runner.py`, `test_sync_control.py`.
**D2:** Add durable last-attempt/verified-observation/valuation/coverage provenance, with migration tests if persisted. Model unchanged observations separately from duplicate import payloads; test next-day unchanged and A→B→A→A. Decide schema after Gate A coverage inspection.
**D3:** Isolate inbox filesystem failures, terminal reporting and bounded provider retries; extend `test_sync_all_service.py`, `test_sync_runner.py`, Trading 212 client/transaction tests. A committed import followed by archive failure must not be misreported as rollback or silently lost.
**D4:** Add freshness strip and Data refresh status using safe reason/action codes; modify `components/DataConfidencePanel.tsx`, `components/ImportPanel.tsx`, `layout/Topbar.tsx`, API types. Show complete/partial/failed/no-op and next run rather than a green generic success.
**D5:** With one-time operator approval, install/test a root-owned start-only Polkit rule for `geoff` and exact `stocks-sync.service`. Keep web-trigger and operator rules distinct. No general passwordless sudo, service restart authority, secret access or live DB access. Test negative authorisations synthetically and verify one authorised end-to-end refresh with correlated terminal report. Update deployment artifacts and operator documentation.
**Acceptance:** failed brokers + empty inbox cannot report complete refresh; scheduled activity appears correctly; stale valuation is not confused with recent verification; WhatsApp can start only the permitted service and report its actual outcome. Broker login lockout/pause markers stay intact.

### Gate E — Finish and maintain
**E1:** Independent history-view states/lazy queries; `routes/PerformanceWorkspace.tsx`, `components/ChartPanel.tsx`; extend workspace tests and create ChartPanel tests.
**E2:** Dated drawdown tooltip and accessible exact observation table; `components/PerformancePanel.tsx`, chart utilities/tests. Do not manufacture daily points from sparse snapshots.
**E3:** Update `scripts/verify_analysis_ui.py` route assembly and fixture contracts: the current rehearsal first returned API 404s under the installed router behaviour; assembling audited GET routes directly from raw routers restored the audit rehearsal. The Performance source-order journey must deliberately seed an order fixture or test the zero-event state, not assume every portfolio window contains an order. Add harness tests that assert required API routes exist and fixture preconditions are explicit.
**E4:** Route code splitting with preserved loading-space geometry and measured bundle/request/CLS budgets; `frontend/src/App.tsx` and current route boundaries. Preserve passkey startup flow in the deployed baseline.
**E5:** Align checked-in deployment isolation/timer policy with live configuration; extend `backend/tests/test_isolation_deploy.py`, `test_isolation_host.py`, `test_sync_policy.py`, `test_deployment_tools.py`. Rehearse without live broker login.

## 5. Verification and release policy

From repo root, planned gates (not claimed executed by this audit):
- `PYTHONPATH=backend .venv/bin/pytest backend/tests` using explicitly isolated test databases and no broker network credentials.
- `.venv/bin/ruff check backend/` and `.venv/bin/mypy backend/app/ backend/alembic/`; record existing failures separately, introduce no new debt.
- From frontend: `npm run typecheck`, `npm run test -- --run`.
- Build outside live served assets: `node node_modules/vite/bin/vite.js build --outDir "$TMPDIR/stocks-acceptance-dist"`.
- After repairing the rehearsal harness and supplying a approved read-only representative DB: `.venv/bin/python scripts/verify_analysis_ui.py --database /approved/read-only/snapshot.db --dist "$TMPDIR/stocks-acceptance-dist" --output "$TMPDIR/stocks-acceptance-evidence"`.
- Capture and visually inspect Overview, Holdings selected/unselected, Performance and Data on mobile and desktop. Browser screenshots, geometry, accessibility, numerical reconciliation and unit tests are separate acceptance layers.
- Test stale, mixed-date, partial, no-op, disabled, auth-expired, no-data, filtered-empty and network-failure states; never use unavailable values as zero.
- Independent security/correctness review; stage exact source and exclude all secrets/data/screenshots. No deployment without separate approval, verified restorable backup for schema changes, rollback release, and read-back of the running release and key routes.

## 6. Effort and scope decisions

Planning estimates, not commitments:
- Gate A: 2–4 engineering days depending on export completeness and real-closure evidence.
- Gate B: 1–2 days.
- Gate C: 3–5 days including layout variants and mobile/keyboard verification.
- Gate D: 3–5 days, with provenance migration and provider limits as principal uncertainty.
- Gate E: 2–3 days, depending on deployment drift and performance measurements.

Layout variants and UI work can proceed against isolated fixtures in parallel with integrity fixes; do not ship richer financial conclusions before Gate A passes. Suggested first visible milestone: full-width Holdings, honest error/filter states, and chart-first Overview—not new analytics.

Defer: real-time trading-terminal UI, automated buy/sell recommendations, constituent fund look-through without holdings data, new Sharpe/VaR claims from sparse snapshot history, user/role abstractions for a single-user app, and blanket permission relaxation.
