# Frontend review candidate — no production release

All changes are frontend-only. No broker, database, permissions or production assets were changed. Human design approval and release remain pending.

## Run the isolated review UI

From `/home/geoff/code/stocks-improve-ui/frontend`:

```sh
npm ci # only if dependencies are absent
npm run build -- --outDir "$TMPDIR/stocks-ui-preview" --emptyOutDir
python scripts/preview_demo.py --dist "$TMPDIR/stocks-ui-preview" --port 8794
```

Open `http://127.0.0.1:8794/`. Layout alternatives:
- `/demo/chart-first.html` — recommended, not human-approved.
- `/demo/ledger-first.html` — ledger-led alternative.

The preview binds loopback only. It has deterministic labelled synthetic fixtures, no upstream proxy, and rejects every mutation. Unknown API reads fail visibly rather than hitting a live backend. If using a remote machine, forward loopback port 8794 over your existing SSH connection; do not expose it publicly. Stop the server with Ctrl-C. Scratch build directories may be pruned; rebuild if absent.

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
| D4 frontend | Tolerant structured outcome/section contract; complete/partial/failed/no-op/disabled remain explicit; legacy missing outcome is unreported. DataConfidencePanel, ImportPanel and Topbar no longer infer generic green success. SyncEvidence and integration tests. Backend worker integration remains another owner's work. |

## Structured refresh contract for backend coordination

Existing `/api/sync/status` and run types remain compatible. Optional additions at status or last_run level:

```ts
outcome?: 'complete' | 'partial' | 'failed' | 'no-op' | 'disabled';
sections?: Array<{
  name?: string; status?: string;
  checked_at?: string | null;
  valuation_date?: string | null;
  attempted_at?: string | null;
  coverage_start?: string | null;
  coverage_end?: string | null;
  detail?: string | null;
}> | Record<string, /* same section fields */ object>;
```

Date meanings stay separate: a check timestamp does not imply newer valuation, an attempted refresh does not prove success, and coverage is not inferred from valuation. No outcome is inferred from legacy `ok`. The service worker must supply authoritative outcome/section evidence; frontend contract tests do not certify live backend semantics.

## Verified final candidate

- TypeScript `npm run typecheck`: pass.
- Vitest: **244 tests / 67 files passed**. Node's existing experimental localStorage warning remains; actual storage-backed AuthGate secret-leak checks pass.
- Python preview contract: **3 tests passed**.
- Vite isolated build: pass; no production output directory used.
- Chrome/Playwright: **24 route/viewport rows** (8 routes at 320/390/1440), **3 interaction sequences**. No document horizontal overflow, undersized inspected controls, wrapped mobile-nav labels or uncaught page errors. Horizontal holdings table scrolling is intentional.
- `git diff --check`: pass.
- Runtime evidence: `/home/geoff/.hermes/cache/scratch/stocks-ui-browser/geometry.json` and screenshots in the same directory. These are scratch evidence, not committed assets.

Re-run browser checks with the preview running:

```sh
uv run --with playwright python scripts/verify_preview.py --out "$TMPDIR/stocks-ui-browser"
```

Chrome executable is `/usr/bin/google-chrome`. The browser blocks non-GET and non-preview-origin requests. Screenshot inspection identified wrapped mobile labels; a failing browser regression was added, then labels were fixed and checks passed.

### Measured bundle evidence

Saved baseline artifact: `/home/geoff/.hermes/cache/scratch/stocks-improvement-baseline/dist/assets/index-UNc25X-i.js`, **1,090,200 bytes**. Final entry: **439,727 bytes** (Vite reports 439.73 kB / 140.58 kB gzip). Do not equate entry reduction with whole Overview load: Chrome observed **9 JavaScript chunks / 860,599 bytes** on initial Overview navigation. Python gzip measurement gives baseline 319,988, entry 139,991 and loaded Overview sum 269,250 bytes; compressor settings differ from Vite's gzip report. Other route chunks are deferred, not deleted. `scripts/measure_bundle.py` reproduces these file/browser-resource measurements.

## Remaining real acceptance boundaries

Synthetic browser coverage is not a live-account or production-auth acceptance test. Do not release without isolated clone/staging rehearsal and human review. Pending: real broker completeness/worker contract validation; authenticated passkey/logout browser exercise; full Tax, Activity and Holding-returns responsive geometry; all error/empty states at real data volumes; keyboard/screen-reader manual usability and chart hover interaction. Full-page screenshots of fixed bottom navigation can show content passing behind it; app bottom padding allows final content to scroll clear. Table date buttons provide accessible drawdown inspection independent of chart hover.
