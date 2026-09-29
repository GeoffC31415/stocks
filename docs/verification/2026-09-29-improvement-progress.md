# Improvement implementation ledger — preproduction candidate

## Release boundary

Geoff approved nonprivileged implementation/testing while unavailable and requires a testable preview before production. No production activation, policy installation, live broker run, real-data access/migration or public proxy/firewall change is approved. Last production read-back: `/opt/stocks/releases/stocks-passkeys-31590ff`. Branch: `feat/ui-service-improvements-20260929`. Unrelated dirty Barclays documentation remains untouched.

## Source and verification state

**Source-spec PASS at `cba5015`, independently reviewed. Security/code-quality review is in progress; no release approval.**

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

Parent restarted loopback GET-only fixture preview on port8794 using the parent-built `cba5015` candidate:
- URL: `http://127.0.0.1:8794/` on the Surface.
- Build: `/home/geoff/.hermes/cache/scratch/stocks-user-review-cba5015`.
- Process handle: `proc_ff8e78ff047b`.
- Variants: `/demo/chart-first.html`, `/demo/ledger-first.html`.
- Synthetic JSON only; no upstream proxy, production DB, broker credentials or auth store. Mutations denied. Unknown reads fail explicitly.

The build and same server implementation were exercised in independent parent Chrome hierarchy tests on an ephemeral loopback port. Original older-preview smoke command was approval-blocked and never retried. Do not misstate that command as successful, or equate local browser testing with off-LAN/public access. No public preview listener is authorized. SSH forwarding can be used through existing authorized access; see `docs/improvement-preview-review.md`.

## Remaining gates

1. Finish independent security/code-quality review; address important defects before release readiness.
2. Geoff tests preview and selects design; preserve human approval as real gate.
3. Approved consistent actual-data snapshot/reconciliation without permission widening.
4. Actual passkey/logout/remote-access and manual accessibility/true-device zoom checks.
5. Installed narrow policy inspection and any correlated real broker run need separate authorization.
6. Production release needs explicit approval, applicable backup/rollback and exact running-release read-back.

The overall plan is not complete: human/actual-data/live gates remain. Source-spec PASS is not code-quality approval, production readiness, or permission to deploy.
