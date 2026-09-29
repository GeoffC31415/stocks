# Improvement implementation ledger — candidate only

## Release boundary

Geoff approved continuing nonprivileged source work while unavailable, requires a testable preview before production, and has not approved production activation. No live broker requests, privileged policy changes, production database reads/migrations or public proxy changes are part of this work.

The current production pointer remains `/opt/stocks/releases/stocks-passkeys-31590ff` at last read-back. Implementation branch is `feat/ui-service-improvements-20260929`. Preserve unrelated dirty Barclays docs.

## Integrated candidate history

- `2855e01`: plan, baseline and preproduction review gate.
- `729ed2d`: incomplete observation rejection, strict HL parser, atomic HL pair helper, Trading212 budgets.
- `7e3fbb9`: workspaces, chart-first hierarchy, labelled variants, lazy routes and synthetic preview.
- `4001f01`: service result/provenance, staged HL runner integration, isolated harness and deployment artifacts.
- `98c95e6`: authoritative backend v2 evidence mapped to frontend, populated preview geometry.

Combined backend and root harness suite at `4001f01`: **1257 passed,1 warning**, actually rerun by parent. Full frontend suite reported by UI worker at `98c95e6`: **249 passed across67 files**, typecheck/build passed; parent rerun remains required. Worker browser report:60 route/viewport rows,3 interaction sequences,24 legacy redirect checks. These counts do not establish every original acceptance requirement.

## Independent spec review: FAIL; fixes in progress

Passing tests did not establish financial correctness. The independent reviewer reproduced:

- Trading212 cancellation leaves staged financial writes in the owning transaction.
- Historical hash dedupe prevents Trading212 and HL A→B→A restoration.
- Aggregation accepts unknown/partial required section coverage or duplicate-only local work as complete.
- Valuation dates can be synthesized from check time rather than retained valuation evidence.
- Missing cash on first observation is unqualified.
- Order pagination permits missing explicit terminal metadata.
- Genuine-closure review allowlist lacks an operational approved resolution mechanism.
- HL pair hardcoded labels do not prove actual export identity.
- Zero-order harness still unconditionally visits a source order; direct harness imports can read dotenv.
- UI acceptance omitted drawdown tooltip, requested chart placement sizes,720px/200% zoom and measured CLS/request budgets.
- Local-mode security route remains blank instead of redirecting.
- Two new mypy errors exclude FetchedHLPair from Fetcher typing.

Two isolated workers are repairing backend findings and harness/UI acceptance findings with regression tests. No quality approval has been issued; independent spec re-review must pass before code-quality review.

## Original task accounting

- **A1 partial/gated:** auth/isolation baseline and preexisting test/quality debt recorded; approved representative read-only production snapshot/calculation comparison remain pending. Synthetic evidence is not current-account evidence.
- **A2 partial:** omission rejection and private positive closure tests implemented; operational reviewed-closure path under repair.
- **A3 partial:** prior-cash rejection implemented; first-observation missing cash under repair.
- **A4 implemented/targeted tests passed:** strict finite/row/header/totals parser gates. Additional identity/date review findings under repair alongside A5.
- **A5 partial:** in-memory staging, atomic helper and runner integrated; actual pair identity evidence under repair.
- **B1 implemented:** distinct loading/error/empty/filter-empty and qualified weights; full integrated rerun pending.
- **B2 implemented:** visible filter counts/chips, independent clear/reset, scope retained; full integrated rerun pending.
- **B3 implemented:** keyboard/ARIA and unknown-tab handling; local auth redirect integration gap under repair.
- **B4 implemented:** scoped classification navigation; full integrated rerun pending.
- **C1 partial/human gate:** two labelled variants exist, chart-first recommendation provisional; Geoff has not selected/reviewed it.
- **C2 partial:** chart-first disclosure and invalid states implemented; requested chart-start geometry under repair/test.
- **C3 implemented:** separate dated attribution/evidence disclosure; full integrated rerun pending.
- **C4 implemented:** full-width unselected holdings, deliberate URL selection/mobile focus return; full integrated rerun pending.
- **C5 partial:** density/nav/labels implemented;720px/zoom/manual accessibility acceptance remains incomplete.
- **D1 partial:** versioned outcomes/CLI implemented; required-section aggregation and duplicate-only truthfulness under repair.
- **D2 partial:** durable status schema implemented; latest-observation dedupe and actual valuation provenance under repair.
- **D3 partial:** inbox isolation, archive attention and bounded clients implemented; cancellation/terminal financial integrity under repair.
- **D4 implemented contract mapping, pending service corrections:** frontend reads canonical no_op/freshness/steps sections without generic legacy success. Backend verification semantics are not yet signed off.
- **D5 partial/privileged gate:** uninstalled narrow operator rule and synthetic negative tests exist; installed rule content, authorized real run and correlation remain pending. Do not install/run while Geoff unavailable.
- **E1 implemented:** independent lazy snapshot history; full integrated rerun pending.
- **E2 partial:** exact sparse observation table exists; dated drawdown tooltip under repair.
- **E3 partial:** direct/lazy router assembly improved; complete zero-event navigation and dotenv refusal under repair.
- **E4 partial:** isolated builds/lazy bundles measured; actual request/CLS/geometry budgets under repair.
- **E5 implemented source/synthetic scope:** isolated identities and effective daily18:30 Europe/London plus2min random delay aligned; no live configuration activated.

## Preview state and access

Parent launched a provisional loopback-only GET-only fixture UI from the integrated build at `http://127.0.0.1:8794/`. It uses explicitly synthetic JSON and has no upstream proxy or production DB/broker/auth connection. Layout variants: `/demo/chart-first.html` and `/demo/ledger-first.html`. Child-owned preview servers were terminated with their agents and are not claimed available.

A parent follow-up command to read preview responses was approval-blocked and did not execute. Do not present provisional launch as verified parent reachability or release acceptance. The preview is an early design review artifact, not financial/service correctness sign-off. No public access/firewall change is authorized. If remote access is needed, document an existing approved SSH tunnel rather than exposing a new public port.

## Remaining sign-off layers

1. Finish regression fixes; integrate exact tested commits.
2. Independent original-spec re-review; fix important gaps.
3. Independent security/code-quality review after spec passes.
4. Parent full backend/frontend typecheck/test/build and baseline-aware lint/mypy gates.
5. Isolated browser geometry/request/CLS, authenticated synthetic boundary, actual screenshots and visual inspection. Do not equate screenshot capture with inspection.
6. Verified local preview access and concise user review checklist.
7. Geoff tests/selects direction; real-data/privileged/broker/deployment approvals separately.

This ledger is deliberately not a declaration that the plan is complete. It must be updated with exact observed results, not compressed into a smaller green session todo list.
