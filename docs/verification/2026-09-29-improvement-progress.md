# Improvement implementation ledger — preproduction candidate

## Release boundary

Geoff approved nonprivileged implementation/testing while unavailable and requires a testable preview before production. No production activation, policy installation, live broker run, real-data access/migration or public proxy/firewall change is approved. Last production read-back: `/opt/stocks/releases/stocks-passkeys-31590ff`. Branch: `feat/ui-service-improvements-20260929`. Unrelated dirty Barclays documentation remains untouched.

## Source and verification state

**Source-spec PASS at `cba5015`. Frontend quality APPROVED at `c596634`; backend quality APPROVED after independent review of the reserved-owner API fix, integrated at `041bbeb`. Test-only fixture isolation follows at `f1a262e`. Source implementation/review is complete; human, actual-data and release gates remain. No release approval.**

The generic matching alias API now rejects reserved `hl-client-identity` creation/deletion with 403 and hides enrollment records from generic lists. Ordinary aliases and reviewed offline enrollment remain supported. Synthetic HTTP/import regressions and fresh-reader comparisons prove attempted repinning cannot accept a changed owner. Independent review passed 45 tests with SQLAlchemy warnings treated as errors. No real owner pin was accessed or changed.

Final parent rerun at `f1a262e`: **1336 backend/root tests passed, no skips**, including the opt-in real Chrome zero-order test with `STOCKS_TEST_DIST` set to the isolated preview build. Only the existing openpyxl sheet-title warning remains. The fixture now owns a fresh FastAPI app with the production matching router: unsupported methods reliably return 405 independently of the global app’s optional frontend fallback, which legitimately returns 404. Security assertions were not relaxed.

Parent rerun at `c596634`: **1326 backend/root tests passed,1 skipped,2 warnings**; **256 frontend tests passed across68 files**, typecheck/build passed; **9 exact preview-contract/metrics tests passed**. Full parent Chrome orchestration passed **100 geometry rows and5 interaction rows**. Initial/cached503, account changes, read-only retries and recovery passed390×844/1440×900 without forbidden requests or page errors. One transaction-deassociation SAWarning occurred in a cancellation regression alongside the existing openpyxl warning; report it rather than claiming warning-free output.

Owner-binding now introduces an explicit operator gate: **paired HL sync will intentionally reject until independently verified owner-pin enrollment**. No live pin enrolled, no migration or production change. Old closure manifests need both ingestion and valuation baseline fields; see `backend/OWNER_REVIEW.md`.

Quality findings repaired in isolated worktrees:
- Reviewed closures bound latest ingestion but mutated latest valuation baseline; bind both and reject backdated reviewed observations under the writer transaction.
- HL coherent raw pair identity not bound to canonical retained account owner; prevent a different client pair overwriting the legacy shared account without rewriting historical fingerprints.
- Actual public serializer now emits nullable coverage-range fields absent from frontend exact fixture; regenerate and retain exact equality regression.
- Initial/cached refresh-status fetch failures need explicit unavailable/cached qualification instead of endless loading or stale-looking current evidence.
- Harden malformed public report collection/value shapes as a scoped resilience improvement.

All reported important source-quality defects are repaired and independently reviewed. Historical source-spec PASS did not waive them. Real financial/service release readiness still requires the remaining human/operator gates.

Integrated history:
- `2855e01`: original plan, baseline and preview gate.
- `729ed2d`: incomplete-observation rejection, strict HL parsing, atomic pair helper, budgets.
- `7e3fbb9`: workspaces, labelled layout variants and lazy routes.
- `4001f01`: status provenance, paired runner and isolated harness.
- `98c95e6`: actual backend v2 serializer/GUI contract and populated geometry.
- `c2e4fda`: owning cancellation rollback, latest dedupe, required coverage, actual valuation, cash/pagination, reviewed-closure CLI and HL identity repairs.
- `1a21816`, `bfe4aa0`, `46e34c0`: tooltip, auth redirect, zero-order/dotenv safety, measured geometry/CLS/request budgets.
- `a598585`: in-process bootstrap test environment/sys.path isolation; production DB guard unchanged.
- `cba5015`: genuine value→secondary metrics→chart→latest changes mobile hierarchy.

Parent-observed results:
- Combined backend/root suite: **1299 passed,1 skipped,1 warning**.
- Frontend: **252 passed across67 files**, typecheck and isolated build passed.
- Actual Chrome hierarchy on parent-built candidate:390×844 chart top716px;1440×900 chart top511.75px; no failures. CLS0.011773725766981758 and0.0016919020329646778 respectively. Chart start, not entire mobile plot, is above the fold.
- Parent visually inspected synthetic mobile/desktop Overview and full-width Holdings screenshots. Critical caveats remain visible. A possible visual numerical mismatch was independently cleared by exact read-only API calculation: return17.39130434782608%, final index117.39130434782608.
- Ruff25 and mypy25 remaining findings are preexisting baseline debt; new Fetcher type failures resolved. Baseline full quality gates are not described as clean.

Independent final source-spec reviewer reran1299 backend/root tests,252 frontend tests,typecheck/build and179 focused rehearsal/database/auth tests. Worker acceptance evidence includes100 route/viewport checks,5 interaction checks,130 zero-order scenario checks and10 explicit alternative journeys. Counts are distinct suites, not added into an invented total. True-device zoom/manual screen-reader and real passkey/broker acceptance remain separate.

Evidence directories: `/home/geoff/.hermes/cache/scratch/stocks-parent-final-verification/`, `/home/geoff/.hermes/cache/scratch/stocks-parent-hierarchy-cba5015/`, `/home/geoff/.hermes/cache/scratch/stocks-final-source-spec-cba5015/`, `/home/geoff/.hermes/cache/scratch/stocks-acceptance-fixes/`. Scratch may expire; rerun before release. No private data/screenshots/DB copies committed.

## Original A1–E5 accounting

“Implemented/verified” below means source and synthetic-test scope, not real broker/production certification.

- **A1 partial/gated:** deployed-source/auth/isolation baseline recorded; approved representative read-only actual-data reconciliation still pending.
- **A2 implemented/verified:** omitted positions reject atomically; operational offline preview-default closure review binds exact account/latest observation/staged payload. Real closure approval/application not performed.
- **A3 implemented/verified:** prior and first-observation missing cash reject the entire incomplete account observation.
- **A4 implemented/verified:** strict finite/header/row/count/totals parsing; verified raw export identity and actual valuation metadata.
- **A5 implemented/verified:** coherent in-memory pair, single atomic importer/runner boundary, owning rollback including cancellation, raw identity/date coherence; legacy fingerprints preserved.
- **B1 implemented/verified:** loading/error/empty/filter-empty and unavailable weights separate with retry.
- **B2 implemented/verified:** active filters/counts, split clear vs reset, account/period preserved.
- **B3 implemented/verified:** roving keyboard/ARIA tabs, unknown/duplicate-tab canonicalization, local security redirect repaired.
- **B4 implemented/verified:** scope-preserving classification navigation.
- **C1 partial/human gate:** two labelled demo variants exist; chart-first recommendation provisional until Geoff tests/selects.
- **C2 implemented/verified synthetic scope:** primary value→secondary metrics→chart, invalid reasons/critical caveats remain visible, repetitive methodology disclosed, requested viewport chart-start targets pass.
- **C3 implemented/verified:** compact separately dated latest snapshot changes and expandable evidence.
- **C4 implemented/verified:** unselected full-width Holdings, deliberate closable deep-linked selection/mobile dialog/focus return.
- **C5 partial/manual gate:** typography/density/numeric alignment/Holding returns/mobile controls implemented;320/390/720/1440 and explicitly approximate200% zoom tested. Actual-device zoom and manual screen-reader usability pending.
- **D1 implemented/verified:** structured outcomes/CLI, required-section coverage, no-op local duplicates, failed/rejected attention semantics.
- **D2 implemented/verified:** durable versioned attempt/verified observation/actual valuation/coverage, latest A→B→A→A semantics; no DB migration required. Bounded HL and unknown Barclays history remain truthfully qualified, not universal-complete.
- **D3 implemented/verified:** independent inbox read/archive failures, committed-with-attention, durable terminal status and bounded provider budgets; owning cancellation rollback verified with fresh file-DB readers.
- **D4 implemented/verified source contract:** actual serialized public v2 maps canonical no_op/freshness/steps sections, check/attempt/valuation/coverage/reason/action distinct, no legacy generic green success.
- **D5 partial/privileged gate:** separate uninstalled start-only Geoff policy and synthetic negatives; installed rule contents and correlated authorized live run not verified. No installation/run while Geoff unavailable.
- **E1 implemented/verified:** independent raw snapshot history and lazy unused queries.
- **E2 implemented/verified:** exact sparse-observation table and dated drawdown tooltip; real synthetic Chrome hover tested, no daily points invented.
- **E3 implemented/verified:** lazy/direct router assembly, pre-import dotenv refusal, explicit global zero-order precondition and snapshot alternatives, no production lifespan/migrations/auth store; test bootstrap restores inherited environment.
- **E4 implemented/verified synthetic scope:** route splitting with stable loading geometry, measured baseline/final request/CLS/resource latency; pre-established budgets CLS0.10/API15/resources40/p95latency1500ms pass.
- **E5 implemented/verified source scope:** isolated identities and effective daily18:30 Europe/London plus2min random delay aligned; no live templates installed or sandbox weakened.

## Preview and user review

Parent restarted loopback GET-only fixture preview on port8794 using the parent-built `c596634` frontend candidate (later changes are backend guard/test-only):
- URL: `http://127.0.0.1:8794/` on the Surface.
- Build: `/home/geoff/.hermes/cache/scratch/stocks-review-c596634/dist`.
- Process handle: `proc_f6f46add8b44`.
- Variants: `/demo/chart-first.html`, `/demo/ledger-first.html`.
- Synthetic JSON only; no upstream proxy, production DB, broker credentials or auth store. Mutations denied. Unknown reads fail explicitly.

The current build passed parent Chrome hierarchy and refresh-error scenarios. Parent verified the running process and GET HTML containing `DEMO / SYNTHETIC DATA` after the final full-suite rerun; this is loopback reachability, not off-LAN/public access. Production pointer was read back unchanged at `/opt/stocks/releases/stocks-passkeys-31590ff`, with stocks service and sync timer active. No public preview listener is authorized. SSH forwarding can be used through existing authorized access; see `docs/improvement-preview-review.md`.

## Remaining gates

1. Independent security/code-quality review is complete for the reported source fixes; rerun acceptance before any separately approved release.
2. Geoff tests preview and selects design; preserve human approval as real gate.
3. Approved consistent actual-data snapshot/reconciliation without permission widening.
4. Actual passkey/logout/remote-access and manual accessibility/true-device zoom checks.
5. Installed narrow policy inspection and any correlated real broker run need separate authorization.
6. Production release needs explicit approval, applicable backup/rollback and exact running-release read-back.

Source implementation and independent quality review are complete. The overall plan is not fully accepted: human/actual-data/live gates remain. Neither source-spec nor quality approval grants permission to deploy.
