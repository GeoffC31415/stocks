# Production UI preservation candidate — durable review and pickup

## Pinned state

- Worktree: `/home/geoff/code/stocks-preserve-ui`.
- Branch: `fix/preserve-production-ui-20260930`.
- Tested implementation commit: **`5471368fd72f3173848f73b9c82ddb85a73163df`** (`fix(ui): preserve production layout and retain data safeguards`). This report is a following documentation-only commit; use `git rev-parse HEAD` to identify the branch's report commit. The implementation SHA above is the exact functional candidate.
- Parent integration base: `4aa9598`; production UI reference: `31590ff`.
- Evidence root: `/home/geoff/.hermes/cache/scratch/stocks-preserve-ui-20260930` (scratch can be pruned; commands below regenerate it).
- **No deployment, merge, push, sudo, production file/DB/credential/service changes, or edits to the dirty main checkout or other worktrees were made by this task.** All test data was explicitly synthetic and all rehearsal servers were ephemeral, loopback-only and cleaned up. Final process check found no owned rehearsal server.
- Parent's supplied observation at 21:47 BST: live still `stocks-passkeys-31590ff`, web/proxy active, TLS `/api/health` returned 401. This task did not independently inspect or change live state.
- User authorized going live, but is unavailable overnight. **Parent owns independent spec/quality review, integration and safe release.** This report is implementation/verification evidence, not independent review or release approval. Do not deploy automatically from these instructions.
- Canonical parent handoff is `/home/geoff/code/stocks/docs/ui-preservation-handoff.md`; it was not edited here. Parent must add the returned final branch SHA and decision there.

## Inventory and preservation decision

### Restored production presentation

`Overview.tsx`, `AttributionSummaryCard.tsx`, `MobileNav.tsx`, `GroupsSection.tsx` and `index.css` are byte-identical to `31590ff`. Restored the Overview `space-y-5` spacing, original three headline KPI columns/stacked mobile cards, original typography/card sizes and flow disclosure placement; Performance left, expanded attribution right on desktop. Removed the extra value-change headline and collapsed attribution disclosure.

Holdings again uses the original 3/5 table + 2/5 detail split, including the original “Select a holding” empty detail card. Search, classification toggle and **Reset view** retain original labels/placement; removed added chips/count/clear-filter toolbar. Removed the added Groups search/count toolbar. Existing URL holdings filters and sorting still work; clear search by editing the existing search box.

Performance retains original `p-5` card, period controls in compact and full panels, full-panel metric tiles **before** the chart, natural DOM order, original 200px pending placeholder, and original methodology placement. Removed chart-first CSS ordering, compressed compact description, hidden compact period controls, giant loading placeholders and the new exact-observation ledger/date buttons. Exact dated drawdown hover remains as a data disclosure, not a new layout.

Restored mobile **Dashboard**, original navigation typography and Portfolio **Returns**. Activity retains exactly Orders / Snapshot changes / Import history; source-record drilldowns still render without introducing a Source record navigation tab. Removed blanket 44px global control/summary/nav resizing and snapshot-selector width redesign. Passkey and logout controls remain inline beside Refresh data in their original placement/style.

### Structural and core improvements retained

- **All backend application/services/import/parser/sync/financial safeguards, deployment artifacts and backend tests from `4aa9598` remain untouched.** Only the analytical browser verifier's superseded layout expectations changed under `scripts/`.
- Lazy route imports and persistent shell; legacy scoped redirects; existing auth/security routing; local `/security` scope-race fix; per-view independent/lazy history queries and failure recovery.
- API schema-v2 compatibility and serialized public-sync fixture. Literal `complete`, `partial`, `failed`, `no_op`, `disabled`; no inferred green success from legacy `ok`.
- Truthful import/service completion outcomes, freshness verification versus latest attempt versus valuation, coverage/reason/action disclosure; cached status explicitly qualified after failed reads; retry performs a status GET, not a refresh mutation.
- Holdings pending/error/empty distinctions, finite account-weight denominator, authoritative account-scoped detail and target drift, independent detail history/orders errors; Groups editor withheld until both membership prerequisites succeed.
- Unavailable financial metrics/reasons, invalid return-chain protection including disabled raw overlay, no raw-for-adjusted substitution; period/account query keys and existing financial calculations.
- Scope-preserving classification CTA; tab canonicalization/roving focus/linked panels without changing visible workspace labels. Source navigation is a valid hidden state with a focusable first visible Activity tab and a correctly named source region.
- Classification repair form intrinsic-width/long-identifier containment remains: minimal necessary access to data repair controls, not a dashboard redesign.

## Every visible exception to the original UI

1. **Refresh evidence**, in existing toolbar valuation/status area, Data confidence and Import: authoritative outcome plus retained checked/valuation/attempt/coverage/status/reason/action. Initial loading, unavailable reads and qualified cached evidence are explicit. It uses the existing small muted/amber text styles; it can increase height/wrapping. The actual refresh/passkey/logout buttons are not relocated or resized.
2. **Import outcomes**: completed service requests show their report instead of unconditional green “Sync complete”; Trading 212 and successful individual step text is neutral rather than proof of comprehensive freshness. This is required for the new import/sync contract.
3. **Performance truthfulness**: sparse covered dates, carried-forward/proxy-flow caveat and each unavailable reason remain visible in the original disclosure block. Empty curves retain invalidity/scope warnings; invalid adjusted chains cannot display a raw fallback chart. Additional text increases height, not card density/order. Added drawdown tooltip reveals only recorded dates and exact finite values on hover; no manufactured daily observations or observation ledger.
4. **Read/error states**: pending/failed Holdings, Groups prerequisite failures, unavailable/nonfinite weights and true empty/filtered-empty/invalid holdings states get truthful text/retry in their original panels; Diff gains truthful loading text. Normal loaded layout is unchanged.
5. **History isolation**: original chart card and selectors remain; independently selected history queries now show their own pending/error/retry/no-recorded-orders text. On zero-order scopes the selectors remain reachable so failures in reconstruction cannot remove real snapshot history. No analytics chart is fabricated from missing orders.
6. **Lazy-route transition**: a reserved 560px loading status exists inside the persistent shell while a route chunk loads. Loaded page presentation follows the production baseline.
7. **Classification repair containment**: long names/identifiers and form controls may wrap/contain rather than overflow; this narrowly preserves access to the existing data repair surface.

The amber synthetic preview banner is harness-only, never a production frontend change. It now advertises preservation, not the archived layout alternatives. Static `/demo/` artifacts remain historical and are not app routes or advertised choices.

## Verified gates and exact outputs

Commands run from the worktree root unless stated otherwise. Interpreter is the documented shared `/home/geoff/code/stocks/.venv/bin/python`; this isolated worktree contains neither repository nor backend dotenv files. Built files are outside all live served directories.

| Gate | Actual result |
| --- | --- |
| `npm --prefix frontend ci --ignore-scripts` | 270 packages added; 0 vulnerabilities. Lockfile unchanged. |
| Red layout regressions before restoration | 8 expected failures / 32 passes across Overview, Holdings, Performance, mobile/Portfolio navigation; expanded attribution separately 1 expected failure / 3 passes. |
| Red controls/source-navigation regressions | 5 expected failures / 18 passes before removing new toolbars/tab. |
| `npm --prefix frontend test -- --run` | **68 files, 257 tests passed**; 46.36s. Existing Node experimental localStorage warnings only. |
| `npm --prefix frontend run typecheck` | `tsc --noEmit`, exit 0. |
| `npm --prefix frontend run build -- --outDir "$E/dist" --emptyOutDir` | Vite build passed; 2,953 modules; entry 440.62 kB / 140.87 kB gzip; 6.06s. Route chunks retained. Entry size is not total Overview transfer size. |
| `PYTHONPATH=backend PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: "$PY" -m pytest backend/tests -q` | **1,284 passed**, one existing synthetic openpyxl long-sheet-name warning; 163.00s. |
| `env -u PORTFOLIO_DATABASE_URL -u PORTFOLIO_DEPLOYMENT_MODE PYTHONPATH=backend STOCKS_TEST_DIST="$E/dist" "$PY" -m pytest tests frontend/scripts/test_preview_demo.py frontend/scripts/test_drawdown_browser.py frontend/scripts/test_browser_metrics.py -q` | **62 passed**, 39.45s, no skip. Includes zero-order source journeys, long-name classifications, factory dotenv refusal, read-only harness, real public serializer and real drawdown hover/unavailable-chain checks. |
| `"$PY" frontend/scripts/rehearse_preview.py --dist "$E/dist" --out "$E/preview"` | **90 geometry rows** (18 app routes × 5 viewport configurations), **5 interaction sequences**, 5 sets of 9 legacy/local-security redirects; exit 0. No document/uncontained overflow or unexpected HTTP/console/page errors. |
| `"$PY" frontend/scripts/verify_ui_preservation.py --baseline "$E/baseline-dist" --candidate "$E/dist" --out "$E/comparison"` | **10 comparisons, 0 differences**, comparing actual baseline/candidate component widths, classes, fonts, colour, padding, gaps, labels and order on the same fixtures at 390/1440. Baseline independently built from `git archive 31590ff frontend`. Truthful extra text can increase height; this is not pixel-identical full-page certification. |
| Same comparison against former redesigned `$HOME/.hermes/cache/scratch/stocks-acceptance-fixes/dist` | Correctly rejected the redesign (original empty detail absent); nonzero exit, durable `red-comparison.log`. Existing React tests also proved semantic RED/GREEN. |
| `"$PY" frontend/scripts/test_refresh_status_browser.py --dist "$E/dist" --out "$E/refresh-status"` | 390/1440 initial 503, qualified cached 503, account changes and explicit GET retries recovered; 6 reads per sequence, no forbidden requests/page errors/overflow. |
| `"$PY" frontend/scripts/test_overview_hierarchy.py --dist "$E/dist" --out "$E/hierarchy"` | 390/1440 original hierarchy/DOM spacing/period controls, no overflow; no failures. |
| `"$PY" scripts/verify_analysis_ui.py --database "$E/zero/synthetic.db" --dist "$E/dist" --output "$E/zero-matrix" --zero-events` | **130 route/width/scenario checks, 0 failed; 10 navigation journeys, 0 failures; read-only DB copy hash unchanged.** Global order count proven zero, not merely an empty filter. |
| Screenshot visual inspection | Candidate mobile/desktop Overview viewport images inspected: original stacked mobile/three-column desktop cards, Dashboard label, performance-left/expanded-attribution-right; visible values £125,400, 6.20%, +£5,000. No observed clipping/overlap. This is synthetic fixture/UI inspection, not financial reconciliation. |
| `git diff --check` | Passed before implementation commit. |

### Honest non-passing and superseded gates

- Former chart-first fold/height, collapsed-attribution, hidden compact-control and global 44px-density expectations were **replaced**, not silently passed. Replacement contracts assert the production layout/navigation, and the direct baseline comparison rejects the redesigned artifact. Overflow, axis/observation correctness, contrast, focus reachability, errors and financial unavailable-state checks still fail closed.
- Measurements are retained in preview `geometry.json`: **max CLS 0.584919487070259; 75/90 rows exceed former performance budgets**. Overview hierarchy run showed chart tops 1413px at 390 and 783px at 1440; CLS 0.22710292263763165 and 0.1249814411262753. Chart-above-fold and CLS ≤0.10 are **not certified**. The user requested production presentation, so these old redesign gates did not justify shrinking/reordering the UI. Required truthfulness text also increases height. Do not present this as a low-CLS release.
- First combined backend+root pytest process: 1,344 passed / 2 failed because backend imports initialized an in-memory global engine, while root isolation tests deliberately unset those environment variables and expected defaults to match the global. No backend workaround or security equality weakening was made. Running the two documented test roots in separate subprocesses yielded the green results above.
- First preview interaction run hit a detached responsive Recharts dot during scroll. Harness now scrolls the stable region and lets locator hover retry; exact recorded-date/value assertions remain. Final complete matrix passed.
- A combined zero-matrix + pytest command exceeded its 400s wrapper after the matrix printed a clean result. Root suite was rerun independently and passed 62 tests in 39.45s. No owned rehearsal process remained.

## Pending gates / blockers

- Parent independent specification and quality reviews, scoped integration into parent branch, decision on candidacy and controlled deployment. **No independent review performed by this task.**
- Real broker completeness/worker behavior, privileged service isolation, authenticated passkey/logout browser use, advanced Matching mutation geometry, manual keyboard/screen-reader usability and real-data-volume/error acceptance remain outside these synthetic tests.
- Source-preserving UI is established for the compared components/routes, not all live user data or native browser zoom. 720×450/DPR 2 matrix entry is a CSS-pixel approximation, not native Chrome UI zoom.
- Parent reports legacy `upgrade-surface.sh` unsuitable/refused for isolated layout; `upgrade_isolated.py` requires controlled root release and coherent evidence. Do not bypass it, restart services, alter production auth or repeatedly prompt the sleeping user for sudo.
- Scratch evidence may expire. No preview is promised to remain running. No live DB/auth/broker material is available or needed here.

## Fresh-session next commands

```sh
cd /home/geoff/code/stocks-preserve-ui
git status --short
git branch --show-current
git rev-parse HEAD
git show --stat 5471368fd72f3173848f73b9c82ddb85a73163df
git diff 4aa9598..HEAD -- backend deploy  # must remain empty
# Inspect canonical handoff separately; do not overwrite dirty parent docs.

PY=/home/geoff/code/stocks/.venv/bin/python
E=/home/geoff/.hermes/cache/scratch/stocks-preserve-ui-20260930
npm --prefix frontend ci --ignore-scripts  # only if dependencies absent
npm --prefix frontend run typecheck
npm --prefix frontend test -- --run
npm --prefix frontend run build -- --outDir "$E/dist" --emptyOutDir
PYTHONPATH=backend PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: "$PY" -m pytest backend/tests -q
env -u PORTFOLIO_DATABASE_URL -u PORTFOLIO_DEPLOYMENT_MODE PYTHONPATH=backend STOCKS_TEST_DIST="$E/dist" "$PY" -m pytest tests frontend/scripts/test_preview_demo.py frontend/scripts/test_drawdown_browser.py frontend/scripts/test_browser_metrics.py -q
"$PY" frontend/scripts/rehearse_preview.py --dist "$E/dist" --out "$E/preview"
"$PY" frontend/scripts/test_refresh_status_browser.py --dist "$E/dist" --out "$E/refresh-status"
"$PY" frontend/scripts/test_overview_hierarchy.py --dist "$E/dist" --out "$E/hierarchy"
# If synthetic.db exists, use it read-only; otherwise prepare with a NEW output path:
"$PY" scripts/synthetic_preview.py --dist "$E/dist" --output "$E/zero-new" --prepare-only
"$PY" scripts/verify_analysis_ui.py --database "$E/zero-new/synthetic.db" --dist "$E/dist" --output "$E/zero-matrix" --zero-events
```

Regenerate the comparison baseline only in scratch; reuse installed dependencies without touching another checkout:

```sh
# Choose an unused scratch baseline directory if these already exist.
mkdir -p "$E/baseline-new"
git archive 31590ff frontend | tar -x -C "$E/baseline-new"
ln -s /home/geoff/code/stocks-preserve-ui/frontend/node_modules "$E/baseline-new/frontend/node_modules"
npm --prefix "$E/baseline-new/frontend" run build -- --outDir "$E/baseline-new-dist" --emptyOutDir
"$PY" frontend/scripts/verify_ui_preservation.py --baseline "$E/baseline-new-dist" --candidate "$E/dist" --out "$E/comparison"
```

### Parent-owned manual preview (not started by this task)

Fixture-only preview, loopback bind; Ctrl-C to stop:

```sh
cd /home/geoff/code/stocks-preserve-ui
/home/geoff/code/stocks/.venv/bin/python frontend/scripts/preview_demo.py \
  --dist /home/geoff/.hermes/cache/scratch/stocks-preserve-ui-20260930/dist --port 8794
```

Open `http://127.0.0.1:8794/` or forward that loopback port through existing SSH. This does **not** start a LAN listener at 192.168.7.205; parent owns any secure access setup. Never use the normal production app for review.

For real analytical GET routers on an exclusively created synthetic DB, use a **new** output directory and no dotenv:

```sh
/home/geoff/code/stocks/.venv/bin/python scripts/synthetic_preview.py \
  --dist /home/geoff/.hermes/cache/scratch/stocks-preserve-ui-20260930/dist \
  --output /home/geoff/.hermes/cache/scratch/stocks-preserve-ui-20260930/manual-preview-1 --port 8127
```

## Exact changed paths

Implementation commit `5471368fd72f3173848f73b9c82ddb85a73163df` contains these paths; this documentation-only continuation adds `docs/ui-preservation-review.md`:

- `frontend/PREVIEW_ACCEPTANCE.md`
- `frontend/scripts/preview_demo.py`
- `frontend/scripts/test_drawdown_browser.py`
- `frontend/scripts/test_overview_hierarchy.py`
- `frontend/scripts/verify_preview.py`
- `frontend/scripts/verify_ui_preservation.py`
- `frontend/src/components/AttributionSummaryCard.tsx`
- `frontend/src/components/GroupsSection.tsx`
- `frontend/src/components/HoldingsTable.tsx`
- `frontend/src/components/PerformancePanel.tsx`
- `frontend/src/components/WorkspaceTabs.tsx`
- `frontend/src/components/__tests__/AttributionSummaryCard.test.tsx`
- `frontend/src/components/__tests__/HoldingsTable.test.tsx`
- `frontend/src/components/__tests__/PerformancePanel.test.tsx`
- `frontend/src/index.css`
- `frontend/src/layout/MobileNav.tsx`
- `frontend/src/layout/Topbar.tsx`
- `frontend/src/layout/__tests__/MobileNav.test.tsx`
- `frontend/src/routes/ActivityWorkspace.tsx`
- `frontend/src/routes/Diff.tsx`
- `frontend/src/routes/Groups.tsx`
- `frontend/src/routes/Holdings.tsx`
- `frontend/src/routes/Overview.tsx`
- `frontend/src/routes/PortfolioWorkspace.tsx`
- `frontend/src/routes/__tests__/Groups.test.tsx`
- `frontend/src/routes/__tests__/Holdings.test.tsx`
- `frontend/src/routes/__tests__/Overview.test.tsx`
- `frontend/src/routes/__tests__/WorkspacePages.test.tsx`
- `scripts/verify_analysis_ui.py`
