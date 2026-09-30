# Archived redesigned UI acceptance — superseded

The chart-first/ledger-first redesign below is **not** the current candidate. The user requires the production UI from `31590ff`. Current scope, exact verification, exceptions and continuation commands are in [`../docs/ui-preservation-review.md`](../docs/ui-preservation-review.md). Former fold, compact-control, collapsed-attribution and 44px-global-CSS gates are replaced by production-baseline contracts; former performance budgets remain measured but are not certified. Static `/demo/` alternatives are retained only as historical artifacts and are no longer advertised by the preview banner.

## Historical redesigned candidate (not release acceptance)

All UI changes are review-only. This integrated checkout also contains the backend sync worker and analytical service changes; no broker, real database, permissions or production assets were changed by this frontend integration. Human design approval and release remain pending.

## Run the isolated review UI

From `/home/geoff/code/stocks`:

```sh
npm --prefix frontend ci --ignore-scripts # only if dependencies are absent
npm --prefix frontend run build -- --outDir /home/geoff/.hermes/cache/scratch/stocks-integrated-preview-dist --emptyOutDir
.venv/bin/python frontend/scripts/preview_demo.py \
  --dist /home/geoff/.hermes/cache/scratch/stocks-integrated-preview-dist --port 8794
```

Open `http://127.0.0.1:8794/`. Layout alternatives:
- `/demo/chart-first.html` — recommended, not human-approved.
- `/demo/ledger-first.html` — ledger-led alternative.

The preview binds loopback only. It has deterministic labelled synthetic fixtures, no upstream proxy, and rejects every mutation. Unknown API reads fail visibly rather than hitting a live backend. If using a remote machine, forward loopback port 8794 over your existing SSH connection; do not expose it publicly. Stop the server with Ctrl-C. Scratch build directories may be pruned; rebuild if absent.

For the combined backend + built frontend rehearsal, use an isolated checkout/worktree with **no `.env` or `backend/.env`** and the shared venv (run from that worktree root):

```sh
/home/geoff/code/stocks/.venv/bin/python scripts/synthetic_preview.py \
  --dist /home/geoff/.hermes/cache/scratch/stocks-integrated-preview-dist \
  --output /home/geoff/.hermes/cache/scratch/stocks-integrated-backend-review \
  --port 8127
```

The output directory must be new; choose another name if it exists. This is the real analytical GET-router rehearsal on an exclusively created synthetic DB, **not** the panel fixtures below. It deliberately has zero orders and synthetic disabled sync. Never launch the normal production app or supply a real DB/broker/auth store for review. These frontend browser results were obtained on the GET-only fixture server, not this backend rehearsal.

Recommendation: chart-first makes observation-based performance and its limitations immediately legible, while latest-snapshot attribution remains separately dated. Ledger-first is better for routine position inspection but places the investment story below the ledger. Both are static design artifacts, not proposed real financial data.

## Acceptance ledger

| Gate | Implementation and evidence |
| --- | --- |
| B1 | Holdings and Groups distinguish loading, failed with retry, true empty, and filtered-empty. Membership editing is withheld until both prerequisite queries succeed. Missing/nonfinite account valuation gives unavailable weights rather than fabricated zero percentages. Holdings, Groups and HoldingsTable tests. |
| B2 | URL filter chips, shown vs account/all-account scope counts; filter clear is separate from columns/sort reset. Account and period survive. HoldingsTable and Groups tests; real Chrome scoped clear interaction. |
| B3 | Shared tabs have roving tabindex, IDs/controls and associated panels, arrow/Home/End selection, and unknown/duplicate-tab canonicalization. All workspace defaults agree with rendering. WorkspaceTabs and WorkspacePages tests; Chrome arrow navigation. |
| B4 | Classification CTA uses scoped navigation, preserving account and performance period. AllocationAnalysisPanel test. |
| C1 | Two static labelled DEMO variants with recommendation rationale in public/demo/README.md. Both rendered at 320, 390, 1440 pixels. Human selection pending. |
| C2 | Observation chart precedes expanded metrics. Concise coverage/sparse-observation/carry-forward/proxy-flow caveats stay visible; methodology expands separately. Unavailable metrics retain each reason; invalid chain cannot draw a seemingly valid performance curve, including raw overlay. PerformancePanel tests. |
| C3 | Latest snapshot value-change summary stays distinct from performance; explicit comparison dates and initially collapsed attribution evidence. AttributionSummaryCard tests. |
| C4 | Unselected Holdings occupies full width; deliberate URL inst selection has closable detail panel, existing mobile modal/focus behavior preserved. Holdings tests plus Chrome select/Escape/focus return at all three widths. |
| C5 | Shared spacing/typography, tabular/right-aligned numerical columns, 44px visible control targets, concise unbroken mobile nav including Help; explicit Holding returns. Existing passkey/logout Topbar preserved with regression tests. Chrome route geometry and screenshot review. |
| E1 | Raw snapshot history has independent state and survives reconstruction/order failures. History queries only run when their view is selected. HistoryViews and PerformanceWorkspace tests; Chrome induced reconstruction failure then successful snapshot history. |
| E2 | Accessible exact observation table and date inspection use recorded date union, never manufactured daily samples. Missing drawdown remains unavailable. PerformancePanel tests; five sparse fixture observations and dated inspection in Chrome. |
| E4 | Lazy route imports retain auth, legacy redirects and shell; stable 560px loading region. App and workspace route tests, real isolated Vite build. Bundle measurement below. |
| D4 integrated | Actual backend v2 `no_op` outcome and `freshness[provider][section]` contract; sanitized `steps[].sections` fallback, with freshness taking precedence and no duplicate rows. Checked (`verified_at`), attempt (`last_attempt_at`), valuation (`valuation_at`), retained coverage, current status, reason and action are separate. Real `public_report` serialization feeds component, Data confidence and Import browser checks; legacy `ok` cannot infer green success. Live broker semantics remain unverified. |

## Authoritative structured refresh contract (schema version 2)

Source of truth: `docs/sync-reliability-operator-notes.md` and backend `sync_control.public_report`. `/api/sync/status.last_run` and completed service requests carry this report:

```ts
schema_version?: number;
outcome?: 'complete' | 'partial' | 'failed' | 'no_op' | 'disabled';
freshness?: Record<string, Record<string, {
  verified_at?: string | null;
  valuation_at?: string | null;
  last_attempt_at?: string | null;
  coverage?: 'complete' | 'partial' | 'unknown';
  status?: string;
  reason_code?: string;
  action_code?: 'none' | 'retry' | 'configure' | 'operator_review';
}>>;
// steps[].sections is a section-keyed map of the same sanitized metadata.
// status also provides next_run_at: UTC timestamp | null, and schedule: string.
```

Providers include Barclays, Hargreaves Lansdown and Trading 212; section keys are holdings, orders, cash and transactions. Optional fields support readable legacy reports; absence never manufactures evidence. Checked means committed verified broker observation, not a local duplicate or attempt. A failed newer attempt preserves prior verification, valuation and coverage, so current status/reason/action remain displayed alongside retained evidence. Coverage is an enum, **not a date range**, and is never inferred from valuation. No outcome is inferred from legacy `ok`; `no_op` is the literal wire value, not `no-op`.

`frontend/scripts/serialize_sync_fixture.py` feeds explicit synthetic input through the real backend public serializer without reading worker state, databases or credentials. The committed JSON fixture is consumed by React tests and the GET-only preview. Python tests regenerate it and compare both uses with the actual serializer, making backend contract drift fail rather than silently changing the fixture.

## Historical integrated candidate (superseded by acceptance fixes below)

- TypeScript `npm run typecheck`: pass.
- Vitest: **249 tests / 67 files passed**. Node's existing experimental localStorage warning remains; actual storage-backed AuthGate secret-leak checks pass.
- Python preview/real-serializer contract: **5 tests passed**.
- Vite build: pass into `/home/geoff/.hermes/cache/scratch/stocks-integrated-preview-dist`; no production output directory used.
- Chrome/Playwright: **60 route/viewport rows** (20 routes at 320/390/1440), **3 interaction sequences**, and eight legacy redirects at each width. Every Portfolio/Activity/Data tab plus Overview, Tax, Help and both static design variants is explicitly checked. Tax includes an expanded synthetic sale; Holding returns and Orders are populated. Data confidence and Import display real serialized v2 evidence.
- No document horizontal overflow, uncontained content overflow, undersized inspected controls, wrapped mobile-nav labels, unexpected HTTP/console errors or uncaught page errors in that matrix. Deliberate bounded table scrolling and clipped empty decorative background shapes are not content failures. The reconstruction failure interaction is intentional.
- Mobile Tax, Orders, Holding returns and confidence final content clears fixed navigation; top/bottom viewport captures distinguish actual layout from stitched full-page sticky-navigation artifacts. Horizontal scrolling of the returns table is exercised separately. Screenshot inspection covered these added mobile routes; human design approval remains pending.
- `git diff --check`: pass.
- Runtime evidence: `/home/geoff/.hermes/cache/scratch/stocks-integrated-ui-browser/geometry.json` and screenshots in the same directory. Scratch evidence is not committed. Owned ephemeral preview servers were stopped; no server is promised to remain running.

Re-run from the repo root with the fixture preview running:

```sh
.venv/bin/python frontend/scripts/verify_preview.py \
  --out /home/geoff/.hermes/cache/scratch/stocks-integrated-ui-browser
.venv/bin/python -m unittest discover -s frontend/scripts -p 'test_preview_demo.py' -v
```

Chrome executable is `/usr/bin/google-chrome`. The browser blocks non-GET and non-preview-origin requests. The matrix is a synthetic panel-layout/contract exercise, not a claim that fixture financial panels reconcile as a ledger.

**Resolved local-mode route regression:** scope default materialisation in the parent shell raced the child `/security` redirect. Security is not an analysis route and no longer rewrites its query. A failing-then-passing nested-router regression test and mandatory Chrome redirect checks at every matrix viewport now verify the Overview heading as well as the URL. The old `--check-local-security-redirect` flag is retained for compatibility but the check is no longer opt-in. Real passkey login/logout remains pending.

### Measured bundle evidence

Current integrated entry: `index-BQBhs0-l.js`, **440,147 bytes** (Vite: 440.15 kB / 140.76 kB gzip). The following is historical measurement from the prior frontend candidate, not a fresh integrated all-resource measurement:

Saved baseline artifact: `/home/geoff/.hermes/cache/scratch/stocks-improvement-baseline/dist/assets/index-UNc25X-i.js`, **1,090,200 bytes**. Final entry: **439,727 bytes** (Vite reports 439.73 kB / 140.58 kB gzip). Do not equate entry reduction with whole Overview load: Chrome observed **9 JavaScript chunks / 860,599 bytes** on initial Overview navigation. Python gzip measurement gives baseline 319,988, entry 139,991 and loaded Overview sum 269,250 bytes; compressor settings differ from Vite's gzip report. Other route chunks are deferred, not deleted. `scripts/measure_bundle.py` reproduces these file/browser-resource measurements.

## Verified acceptance fixes

- Typecheck and isolated Vite build pass; **250 Vitest tests / 67 files** and **58 Python harness/preview regression tests** pass. Existing Node experimental localStorage warnings remain, with no test failures.
- `verify_preview.py` now requires **320×844, 390×844, 720×900, 1440×900**, plus a **720×450 CSS-pixel / DPR 2 approximation of 200% desktop browser zoom**. This is not native Chrome UI zoom or pinch zoom. All 20 routes pass at all five configurations: **100 geometry rows, 5 interaction sequences, 5 sets of 9 mandatory redirects**. Tax expanded sale, populated Activity and holding returns, healthy Matching, independent history failure/recovery, exact-date table and real drawdown hover are exercised. No unwanted HTTP/console/page errors, overflow, undersized controls or wrapped mobile-nav labels.
- Normal-fixture Overview chart starts at **737.75, 604, 443.5 and 603 CSS px**, respectively, inside each normal initial viewport. This establishes chart *start* visibility, not whole-chart visibility: the 390×844 initial screenshot shows the lower chart behind the fixed mobile navigation until scrolling. Warning disclosures remain rendered, and a separate real-Chrome unavailable-chain test requires its critical reason and refuses a raw/fabricated chart. No warning is collapsed to force an above-fold pass.
- Real Chrome `PerformanceObserver` is installed **before navigation**, rejects unsupported/missing observers, excludes recent-input shifts and computes the maximum CLS session window. A deliberately moving synthetic element verifies the observer actually records shifts. Budgets were fixed before final runs: **CLS ≤0.10, API requests ≤15, resource requests ≤40, resource p95 ≤1500ms** per fixture route. Initial sync/date/account toolbar geometry and performance/diff loading space were stabilised; no financial calculations changed.
- Same fixture server, cold browser context per route, real clock and 1.5s post-load observation: saved monolithic baseline **max CLS 0.838784 / API requests 10 / resource requests 14 / p95 89.5ms**; final **0.005054 / 9 / 26 / 68.6ms**. More resource requests reflect split JavaScript chunks, not a reduction in all requests. Full 100-row route matrix max CLS **0.018257**, also below budget. Loopback fixture timings are not WAN performance promises.
- Current bundle: baseline entry **1,090,200 bytes / 319,988 gzip**; final entry **440,312 / 140,218 gzip**; initial Overview actually loads **9 JS chunks / 861,728 bytes / 269,607 summed gzip**. Entry reduction is not whole-page byte reduction.
- Direct `create_app` refuses either repository `.env` or `backend/.env` (including symlinks) **before application/settings imports**, then pins in-memory/local process defaults. Synthetic sentinel import guards verify both refusals. No private dotenv values were read.
- The analytical-router harness's `--zero-events` first proves **global database order count is zero**, not just an empty filtered page. Performance timeline opens real synthetic import sources and proves no trade/order source exists instead of unconditionally requesting an order. Holding→orders→Back, disabled pagination, both income periods and snapshot-source Performance alternatives are explicitly labelled alternatives, not populated-order success. Returns/groups accept only their asserted intentional empty states. **130 route/width/scenario checks and 10 alternative journeys pass**, and the read-only copied DB remains unchanged. The long-name matrix also caught/fixed classification-row intrinsic grid overflow.
- Evidence: `/home/geoff/.hermes/cache/scratch/stocks-acceptance-fixes/{summary.json,baseline-metrics.json,final-metrics.json,preview/geometry.json,zero-matrix/report.json}` and screenshots. Mobile and desktop Overview screenshots were inspected separately from DOM measurements. All owned ephemeral servers were shut down; the parent-owned preview was not touched.

Reproduce with an isolated worktree containing no dotenv files and a fresh scratch output directory:

```sh
# Build once, outside any live served directory.
npm --prefix frontend run build -- --outDir "$EVIDENCE/dist" --emptyOutDir
/home/geoff/code/stocks/.venv/bin/python frontend/scripts/rehearse_preview.py --dist "$EVIDENCE/dist" --out "$EVIDENCE/preview"
/home/geoff/code/stocks/.venv/bin/python frontend/scripts/measure_browser.py --dist "$EVIDENCE/dist" --out "$EVIDENCE/final-metrics.json" --enforce
/home/geoff/code/stocks/.venv/bin/python scripts/synthetic_preview.py --dist "$EVIDENCE/dist" --output "$EVIDENCE/zero" --prepare-only
/home/geoff/code/stocks/.venv/bin/python scripts/verify_analysis_ui.py --database "$EVIDENCE/zero/synthetic.db" --dist "$EVIDENCE/dist" --output "$EVIDENCE/zero-matrix" --zero-events
PYTHONPATH=backend PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: STOCKS_TEST_DIST="$EVIDENCE/dist" /home/geoff/code/stocks/.venv/bin/python -m pytest tests frontend/scripts/test_preview_demo.py frontend/scripts/test_drawdown_browser.py frontend/scripts/test_browser_metrics.py -q
```

`EVIDENCE` must be an absolute scratch path outside the repository. Baseline comparison uses the saved artifact with the **same current synthetic fixture server**, not a broker connection. Synthetic checks do not waive any outstanding real-broker, passkey, privileged isolation or human approval requirement.

## Remaining real acceptance boundaries

Synthetic browser coverage is not live-account or production-auth acceptance. Do not release without isolated clone/staging rehearsal and human review. Pending: real broker completeness/worker semantics and privileged service isolation; authenticated passkey/logout browser exercise; advanced Matching editing geometry (GET-only fixture checks its healthy summary, not mutations); all error/empty states at real data volumes; keyboard/screen-reader manual usability and human design selection. The analytical-router zero-order matrix covers populated Allocation categories from real synthetic snapshot rows; the panel-fixture matrix still uses intentionally empty Allocation. Dated drawdown hover is now exercised in real Chrome. Tax, Activity and Holding-returns fixture geometry is now covered, not real-volume semantics. Stitched full-page screenshots can put sticky header/fixed bottom navigation over content; real top/bottom viewport captures and final-content clearance checks pass for the added mobile routes. Table date buttons provide accessible drawdown inspection independent of chart hover.
