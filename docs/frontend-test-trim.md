# Frontend test trim: measured, risk-led

## Parent integration verification

Integrated into master with the backend trim. The complete retained suite passed214 tests with zero failures/pending; the two-worker npm command took45.40s, and typecheck/build passed. Independent review approved the risk-led removals; it explicitly accepted the documented marker-legend gap, not a claim that helper tests cover component wiring. Earlier matched candidate timings below remain the apples-to-apples comparison; this additional integrated run overlapped backend execution.

Production source remains unchanged. Built CSS differs only by removal of `.order-1{order:1}`, which had appeared solely in removed test assertions; no remaining frontend source references it. No other CSS rule changed or was added. Deployment remains separate and was not performed.

## Scope and result

Base: `f475bf38f81e4a6610081eb0b0b48625f72dee32`, detached worktree; no production source, dependencies, package scripts, backend fixtures, or deployment changes. Removed redundant assertions/tests rather than hiding them with skip, exclusion, retries, timeouts, or a smaller selected test command. There was no numeric target. Kept expensive tests when they protect a likely consequential failure.

| Measurement | Before | After |
|---|---:|---:|
| Test files passed | 71 | 63 |
| Tests passed | 266 | 214 |
| Failed / pending / todo | 0 / 0 / 0 | 0 / 0 / 0 |
| Vitest duration | 61.94s | 49.04s |
| Whole npm command wall time (`time -p` real) | 62.85s | 49.80s |
| User / system CPU time | 133.55s / 14.68s | 105.85s / 11.66s |
| Transform / setup / import | 3.17s / 4.39s / 17.34s | 2.96s / 4.14s / 14.93s |
| Test execution, accumulated | 25.48s | 21.24s |
| Environment setup, accumulated | 62.39s | 45.30s |

52 fewer tests (19.55%); 13.05s less wall time (20.76%). Environment setup fell 27.39%. Accumulated phase totals span both workers and are **not** additive wall-clock segments. One full baseline and one full retained run, not a statistical benchmark; host load/cache warming can affect the observed difference. Do not extrapolate to production or claim every saved second comes from test deletion.

## Reproduce and evidence

Both measured full-suite commands ran from `frontend`, on Node `v25.8.1`, installed Vitest `4.1.11`, with the same dependencies, reporter settings and `--maxWorkers=2` (the deployment runner's worker setting):

```sh
export PATH=/home/geoff/.local/share/stocks-build-tools/node-v25.8.1-linux-x64/bin:$PATH
/usr/bin/time -p npm test -- --run --maxWorkers=2 \
  --reporter=default --reporter=json --outputFile=/absolute/path/report.json
npm run typecheck
npm run build
```

Local evidence, outside the patch:

- Worktree: `/home/geoff/.hermes/cache/scratch/stocks-frontend-trim`.
- Reports: `/home/geoff/.hermes/cache/scratch/frontend-trim-{before,after}.json`.
- Full logs: `/home/geoff/.hermes/cache/scratch/frontend-trim-{before,after}.log`.
- Typecheck/build logs: `/home/geoff/.hermes/cache/scratch/frontend-trim-{typecheck,build}.log`.
- Machine-readable per-file count changes: `/home/geoff/.hermes/cache/scratch/frontend-trim-counts.json`.

Exact final summary:

```text
Test Files  63 passed (63)
     Tests  214 passed (214)
Duration  49.04s (transform 2.96s, setup 4.14s, import 14.93s, tests 21.24s, environment 45.30s)
real 49.80
user 105.85
sys 11.66
```

`npm run typecheck` (`tsc --noEmit`) exited 0. `npm run build` exited 0: Vite `7.3.6`, 2,955 modules transformed, built in 6.42s. An initial after-run invocation from the repository root failed with `Missing script: "test"` before Vitest started; it was corrected to `frontend` and is not a measurement. `docs/stocks-pickup.md` was absent at this base; the available release runbook was read, but no live state was inspected or changed.

## Timing-led environment change

Baseline DOM environment cost dominated even tiny helper suites: `routing` took 0.002s of assertions, `groupScope` and `orderPageApi` each 0.003s, `chartTheme` 0.003s, while every file booted jsdom. The twelve retained DOM-free suites below now explicitly declare `// @vitest-environment node`:

- `frontend/src/__tests__/routing.test.ts`
- `frontend/src/components/__tests__/holdingSignals.test.ts`
- `frontend/src/routes/__tests__/cgtPresentation.test.ts`
- `frontend/src/lib/__tests__/allocationApi.test.ts`
- `frontend/src/lib/__tests__/chartTheme.test.ts`
- `frontend/src/lib/__tests__/formatters.test.ts`
- `frontend/src/lib/__tests__/groupScope.test.ts`
- `frontend/src/lib/__tests__/holdingsView.test.ts`
- `frontend/src/lib/__tests__/instrumentBuyMarkers.test.ts`
- `frontend/src/lib/__tests__/investigationLinks.test.ts`
- `frontend/src/lib/__tests__/orderPageApi.test.ts`
- `frontend/src/lib/__tests__/performanceChart.test.ts`

No Vitest configuration or setup changes were necessary. Existing setup only imports `@testing-library/jest-dom/vitest`; registering its matchers works in Node without creating a DOM. Compatibility was exercised first: these twelve suites plus MobileNav passed 36 tests in 2.54s; the full retained run also passed. Request-builder tests stub fetch and do not exercise private-401 DOM dispatch. `auth/api.test.ts` deliberately remains jsdom because it listens to `window` events. All React interactions and router/cache hooks remain jsdom. Do not infer environment from `.ts` versus `.tsx` alone.

## Removal inventory and retained controls

Paths below are relative to `frontend/src`. Before/after counts are parsed from Vitest assertion results, not source-text test-call estimates.

| Test path | Before → after | Decision / retained control |
|---|---:|---|
| `components/__tests__/AllocationAnalysisPanel.test.tsx` | 8 → 7 | Drop duplicate scenario-heading mounting. Actual read-only scenario edit/reset/request behavior remains in AllocationScenarioPanel and allocationIntegration. Retain authoritative totals, classification count/value coverage, grouping, every dimension/account request, pending/error/empty and exact category links. |
| `components/__tests__/AnalysisStatus.test.tsx` | 3 → 0 | Delete isolated static reason/retry/link primitives; PerformancePanel checks unavailable reasons and no invented retry, AllocationAnalysisPanel exercises retry, Overview exercises import repair link. |
| `components/__tests__/AttributionSummaryCard.test.tsx` | 4 → 3 | Drop duplicate expanded-evidence placement test; successful summary still requires one **visible** table, exact boundaries/flows, mover links, no value walk, reconciliation and unavailable state. |
| `components/__tests__/AttributionWaterfall.test.tsx` | 6 → 2 | Opening/closing, reconciliation and single-table checks already run through the real parent. Keep signed contribution/withdrawal/residual rows and missing-component/reconciliation-not-zero. |
| `components/__tests__/ChartTooltip.test.tsx` | 2 → 1 | Drop passed-through static legend name. Keep actual exact financial value and missing-value display. |
| `components/__tests__/HoldingsTable.test.tsx` | 14 → 11 | Drop alignment-only test and no-input/empty-groups matrix duplicates. Keep positive/negative gap, neutral intent, unknown tolerance, in-band, unavailable, non-finite gap, valuation denominator, search/select, URL sorting/reset and empty/unavailable distinctions. |
| `components/__tests__/InstrumentDetail.test.tsx` | 3 → 0 | Delete chart-legend label tests, which did not inspect marker positions/dates. instrumentBuyMarkers retains real buy/sell UTC sorting/dedup and DRIP exclusion; drawer and TimelineEvents tests retain interactive instrument/timeline behavior. Marker legend wiring itself is now an acknowledged gap, not claimed covered by helper tests. |
| `components/__tests__/MetricCard.test.tsx` | 3 → 0 | Delete passed-through literal props and heading/button mounting. Real metric display/method/null assertions remain in PortfolioReturnCard, PerformancePanel, HoldingsTable, AttributionSummaryCard and ChartTooltip. |
| `components/__tests__/OrderHistorySection.test.tsx` | 4 → 3 | Drop intermediate next-page matrix duplicate. Keep delayed final-next (including disabled Next), previous-page focus restoration and unavailable financial totals. Orders retains first-page request/URL paging and scope isolation. |
| `components/__tests__/PerformancePanel.test.tsx` | 14 → 12 | Drop CSS class-placement test and standalone pending render already exercised during account/period transition. Keep production metric-before-chart order, compact controls/caveats, backend-invalid reasons, adjusted-vs-raw nulls, annualisation distinction, contribution drawdown regression, raw-overlay interaction, empty and retry. |
| `components/__tests__/SyncEvidence.test.tsx` | 10 → 7 | Reduce identical generic outcome rendering matrix to complete/failed; partial is in serialized fixture, no-op in DataConfidencePanel. Keep freshness precedence, timestamps, absent verification and legacy-success-not-verification. Disabled-outcome spelling no longer separately pinned. |
| `components/__tests__/WorkspaceTabs.test.tsx` | 3 → 2 | Drop generic URL-click duplicate. Keep invalid-tab fallback, keyboard roving focus and investigative parameter preservation; useAnalysisScope exercises real click plus Back/Forward. |
| `components/__tests__/orderFilters.test.ts` | 2 → 0 | Legacy helper has no production caller in this base. Actual Orders route/server filter behavior and orderPageApi request contracts remain. |
| `layout/__tests__/Sidebar.test.tsx` | 1 → 0 | Drop copied labels/absent admin labels. MobileNav uses Sidebar's actual shared PRIMARY_NAV and now asserts all destination paths and preserved account/period/inst without leaking tab. Desktop-only DOM/visual styling is not asserted. |
| `layout/__tests__/Topbar.test.tsx` | 2 → 1 | Remove single-consumer status retry duplicate; refreshStatusIntegration retains real Topbar plus confidence shared-query initial failure, GET retry, cached failure and account transitions. Retain header controls and security navigation. |
| `lib/__tests__/allocationAnalysis.test.ts` | 2 → 0 | Tests exercised `__tests__/allocationOracle`, not production allocation code. Keep authoritative allocation API/UI and classifications. |
| `lib/__tests__/allocationGolden.test.ts` | 9 → 0 | Same test-only oracle over nine legacy dimension/account combinations. Backend fixture untouched; this was not parity coverage of the current security-grouped production endpoint. |
| `lib/__tests__/dripAnalysis.test.ts` | 2 → 0 | Legacy trailing-twelve-month calculator has no production caller; current Income uses backend calendar-matched totals. IncomeAnalysisPanel retains actual financial display and matching-purchase links without client aggregates. |
| `routes/__tests__/Groups.test.tsx` | 3 → 2 | Drop mocked editor-ready/search-toolbar absence check. Keep pending/error retry; GroupsSection uses real editor and preserves late membership, pending edits and unchanged-blur-no-write regressions. |
| `routes/__tests__/Help.test.tsx` | 3 → 1 | Remove large static-copy matrix/headings. Keep real scoped workspace link replacing stale Help tab and preserving investigation ID. Financial caveats tested with real values in the financial panels, not their Help prose. |
| `routes/__tests__/Holdings.test.tsx` | 12 → 9 | Drop split-grid CSS check and two lexical-ID route repeats; full canonical-ID matrix remains in holdingsView. Keep ambiguous-ID and absent-scoped-ID request refusal, unresolved account guard, focus/Escape/back/drawer trap, independent errors and scoped order links. |
| `routes/__tests__/Overview.test.tsx` | 8 → 7 | Drop repeated successful-zero fixture render. Remaining compact and error-recovery cases still show real dated zero. Keep API account totals despite absent instruments, pending/error/empty distinctions, production DOM order and no obsolete analytics requests. |
| `routes/__tests__/WorkspacePages.test.tsx` | 6 → 4 | Drop literal navigation label arrays. Keep all three workspaces' invalid-tab/panel/URL contracts and hidden source inspection route. |

Only additional changed test is `frontend/src/layout/__tests__/MobileNav.test.tsx`: replaced copied labels/CSS assertions with actual destination and scope contracts. Together with the twelve environment-only paths and 23 rows above, these are all 36 changed frontend test paths. The only new tracked deliverable is this document.

## High-value suite intentionally left intact

- AuthGate: all 17 tests, including fail-closed initial session, no pre-auth portfolio mount, deadline expiry, cancellation/retry, duplicate clicks, logout request failure, query/mutation purge, late enrollment and recovery-token memory clearing. Private API suite: all 5 tests, including every 401 path and late response rejection. Real entrypoint gate and security route remain.
- ClassificationQueue: all 5 editor tests (bulk validation, sorting/editing, restore nonstandard values, failed-row retry); no mocked label substitute.
- ImportPanel: all 5 tests, including dedicated `/api/sync/trading212/request` without web broker credentials, polling, disabled legacy controls, manual Barclays upload and cash-flow refresh. No provider or live database access.
- allocationIntegration, refreshStatusIntegration and investigationIntegration: unchanged shared consumers, preference propagation, baseline-version cache isolation and scope/navigation regressions.
- DrawdownEpisodes, IncomeAnalysisPanel, PortfolioReturnCard, instrumentBuyMarkers, formatters and performanceChart retain actual numeric/method/null/date semantics. HoldingDetailPanel keeps populated-timeline drawer focus order; TimelineEvents retains filters/source links and keyboard markers.
- App, AppShellRecovery, useRouteFocus, useAnalysisScope, Orders, Diff, TimelineSourceView and history-workspace contracts remain; no removal of lazy-chunk failure containment or late route/scope guards.

## Bounded losses / future work

This is not a zero-risk deletion and not a claim of browser coverage. Exact Help wording, CSS class spelling/grid alignment, chart legend prop echoing, the disabled sync outcome's literal spelling and desktop-only navigation markup are less pinned. The removed buy/sell legend integration could regress independently of the retained date helpers. Actual SVG chart geometry was not proven by those removed label checks; browser chart/layout checks remain separate and were not run here.

If dormant orderFilters/dripAnalysis or test-only allocationOracle is deliberately revived in production, add tests at the new caller/endpoint boundary before relying on it; do not restore a large oracle matrix merely because it is financial-sounding. The source modules/helpers were left untouched under this test-only scope.

No exclusions, changed worker limit, shared QueryClient, weakened auth mock, production component change, dependency change, snapshot update, or deployment shortcut was introduced. Further cuts would mostly remove distinct scope/null/failure/editor branches for small assertion-time savings, so they were not made merely to reach a count target.
