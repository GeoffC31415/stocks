# Sync and isolated development

## Worker boundary

Public mode never directly calls brokers from a web request. With service-trigger
support enabled, authenticated exact-Origin empty-body/parameter requests select
fixed worker services; arbitrary units/commands are not accepted:

- `/api/sync/request` POST/GET requests/polls the general worker.
- `/api/sync/trading212/request` POST/GET requests/polls only `stocks-t212-sync.service`.
- Direct `/api/sync/all` and Trading 212 provider writes are forbidden in public mode.

The dedicated `app.trading212_cli` runs Trading 212 only: no migrations, browser fetch
or inbox imports. Both workers share the stable `sync-run.lock` inode. Trading 212
has a separate invocation-correlated report namespace; the web selects parent-status-dir
plus `trading212`, while the installed dedicated worker receives that subdirectory
as its configured status directory. Do not append it twice. Inspect actual installed
unit/policy before changes; a dedicated unit template is not present in this repository.
Web credential availability does not certify the worker's credentials/permissions.

The [source timer](../deploy/stocks-sync.timer) is daily 18:30 Europe/London,
randomized up to two minutes and Persistent. This is not proof of the effective
installed schedule or broker scope. Inspect drop-ins and next trigger; enabling a
Persistent timer can immediately catch up and requires separate approval. Operator
start-only policy templates are review inputs, not proof that a grant is installed.

Barclays manual file upload remains available. Its source fetcher now supports a
guarded opt-in paired path, not the obsolete always-disabled collector description.
Credentials alone do not enable it: automation flag, independently pinned expected
account and supervised authentication verification are required. `barclays-login-blocked`
is a permanent operator pause; `barclays-login-attempt` survives uncertain attempts.
Only verified committed pair ingestion can acknowledge the latter. Never clear either
blindly to retry. A pause cannot undo an already in-flight bank call. See
[ingest safety](../backend/docs/sync-integrity-operator.md).

## Status and durability

`GET /api/sync/status` returns account snapshot ages, enable flags, running/last-run
state and next schedule information. `next_run_at` is UTC or null (unknown), not a
predicted success. Schema-version-2 reports use `complete`, `partial`, `failed`,
`no_op`, or `disabled`. Provider section evidence separates attempt, verification,
valuation, coverage, current reason and action:

- `last_attempt_at` is an attempt, not a verified check.
- `verified_at` advances only for a successful validated committed section;
  an unchanged provider check can advance verification without a new batch.
- `valuation_at` retains provider valuation evidence, not today's check time.
- `coverage` is complete/partial/unknown, not inferred from valuation or legacy `ok`.
  Failed checks preserve prior verification/coverage; inspect current status too.

A duplicate file or empty inbox is `no_op`, not fresh provider evidence. Disabled or
unconfigured brokers are not failures. Incomplete required coverage/failed sections
require attention; partial and failed both exit nonzero. Post-commit archive or
acknowledgment failure is committed-with-attention, not a rollback claim.
Private reports atomically publish/fsync under the worker lock; public reports allowlist
fields and omit filenames, source paths, raw exceptions, identities and credentials.
Publication failure means persisted terminal status cannot be guaranteed.

Trading 212 failure logs retain the stable `code`, `endpoint`, `phase`, HTTP status
and worker `invocation_id`, adding reviewed fixed-English `reason`, `stage` and
`resource` labels. They describe the observed rejection, not an inferred cause or
repair; unknown failures say that no classified reason is available. The snapshot
import stage validates positions and account-summary cash together, so its resource
label includes both. Exception text/classes, rejected values, identities, provider
bodies/URLs, credentials and tracebacks are not logged. Owner rollback remains before
diagnostics. These explanations are **journal-only**: public status still suppresses
step detail and diagnostic codes; the public scrubber and API error responses are
unchanged. Use the worker invocation ID to correlate a failure with its journal line.
No item index or provider-derived category metadata is added: only source-owned,
sink-allowlisted codes and fixed explanations cross the diagnostic boundary.

### Trading 212 cash and fill contract

The [official API schema](https://docs.trading212.com/api/) documents these cash types:

| Cash type | Handling |
| --- | --- |
| `DEPOSIT` | Positive finite nonzero external funding. |
| `WITHDRAW` | Either finite nonzero sign accepted; external outflow is `-abs(amount)`. |
| `FEE` | Validated internal event; no external funding row. |
| `INTEREST_ON_FREE_CASH` | Validated internal event; no external funding row. |
| `LENDING_INTEREST` | Validated internal event; no external funding row. |
| `TRANSFER` | Signed finite nonzero external cash movement for the observed account: negative outflow, positive inflow, preserving amount's sign. |
| Missing/unknown type | Reject with `unsupported_cash_transaction_type`; no speculative aliases. |

All classified events require a timezone-bearing date, nonblank unpadded reference,
finite amount and GBP currency, including internal events. Internal zero amounts are
allowed; funding zeroes and negative deposits are refused. Exact duplicate references
are deduplicated; conflicting reference evidence is refused. Field failures use
`invalid_cash_transaction_reference`, `_date`, `_amount` or `_currency`; malformed
items use `invalid_cash_transaction`; invalid transfer amounts have the distinct
`invalid_cash_transfer_amount` code. Cross-refresh consistency checks cover retained
external funding events; internal fee/interest events are validated on each fetch
but are not retained for historical comparison. Failure rolls back the complete
sync, not only the offending section.

The cash-ledger TRANSFER policy is grounded in an observed negative event confirmed
as Invest -> CFD: cash left the observed Invest account. CFD is outside this equity
API portfolio scope; never invent its holdings, orders or a corresponding incoming
cash leg. The observed account movement is funding, not investment loss. Positive
transfers are account inflows, not investment gains. Opposite legs cancel aggregate
funding only when both accounts and both actual legs are independently in scope.
This account-scoped policy is not a guarantee about every future provider subtype
or a classification of within-account Pie reallocations. Unknown types remain
fail-closed; no spelling aliases or broad provider-wide completeness claims are made.

| Fill type | Handling |
| --- | --- |
| `TRADE` | Import validated execution; BUY quantity must be positive, SELL accepts either nonzero sign and stores magnitude. |
| `STOCK_SPLIT`, `STOCK_DISTRIBUTION`, `FOP`, `FOP_CORRECTION`, `CUSTOM_STOCK_DISTRIBUTION`, `EQUITY_RIGHTS`, `SCRIP_STOCK_DIVIDENDS`, `STOCK_DIVIDENDS`, `STOCK_ACQUISITION`, `CASH_AND_STOCK_ACQUISITION`, `SPIN_OFF` | Recognised and skipped, preserving existing behaviour; never fabricated as trades. |
| Missing/unknown fill type | Reject with `invalid_order_fill_type`. |

Recognition of all 12 fill categories does not implement a corporate-action ledger or
validate skipped event economics. Fill trade side, quantity, date, instrument name,
identifier, net value and wallet currency remain required. Order origin, status,
strategy, order type, time validity and fill trading method do not determine whether
an actual validated trade fill is imported. Order pagination accepts only canonical
`cursor=123&limit=50` or `limit=50&cursor=123` parameter order, with existing path,
host, unique-key, numeric-bound and encoding checks retained.

### Journal troubleshooting (read-only)

Select the unit that actually ran; general and dedicated workers have separate reports:

```sh
journalctl -u stocks-t212-sync.service -n 80 --no-pager -o cat
journalctl -u stocks-sync.service -n 80 --no-pager -o cat
# Copy the exact invocation ID from the matching failure/report, never a credential:
journalctl _SYSTEMD_INVOCATION_ID=EXACT_INVOCATION_ID --no-pager -o cat
```

The failure line discloses only validated code/endpoint/phase, HTTP status when known,
invocation correlation and reviewed prose. It does not disclose the rejected type
value (even for unknown types), dates, amounts, references, holdings, account identity,
provider payloads, URLs, exceptions or traceback. The fixed invalid TRANSFER amount
reason names a source-owned category, not an arbitrary echoed provider string. Public status
continues to omit these diagnostic details. Journal access may require the operator's
normal approved permissions; do not read credential files or enable HTTP debug logs.

## Development checks and isolated previews

Use an isolated checkout without `.env` or `backend/.env`, existing dependencies and
private scratch output. Never launch normal app lifespan against live data or overwrite
served `frontend/dist`. From that worktree root:

```sh
/home/geoff/code/stocks/.venv/bin/python scripts/test_t212_synthetic.py \
  backend/tests/test_t212_service.py backend/tests/test_t212_release_contract.py -q
npm --prefix frontend test -- --run --maxWorkers=2
npm --prefix frontend run typecheck
```

The backend launcher clears inherited `PORTFOLIO_*`, disables dotenv before config
imports and selects an in-memory default. Tests use explicit disposable databases.
Select relevant tests for scoped work; use the full backend suite for integration:
`/home/geoff/code/stocks/.venv/bin/python scripts/test_t212_synthetic.py backend/tests -q`.

For a synthetic read-only preview, explicitly choose a **new absolute scratch directory**
outside the repository (the fixture output must not exist):

```sh
: "${EVIDENCE:?Set a new private absolute scratch directory outside the repository}"
npm --prefix frontend run build -- --outDir "$EVIDENCE/dist"
/home/geoff/code/stocks/.venv/bin/python scripts/synthetic_preview.py \
  --dist "$EVIDENCE/dist" --output "$EVIDENCE/fixture" --port 8127
```

Open loopback `http://127.0.0.1:8127`; stop with Ctrl+C. This creates labelled synthetic
holdings and zero orders, serving audited analytical GET routes read-only with writes
blocked and normal lifespan disabled. It is not real auth/broker/ledger acceptance.
For a real-data UI rehearsal, first obtain a verified private SQLite backup via an
authorized backup capability, then use explicit private paths:

```sh
/home/geoff/code/stocks/.venv/bin/python scripts/verify_analysis_ui.py \
  --database "${PRIVATE_VERIFIED_BACKUP:?Set the verified private backup path}" \
  --dist "${PRIVATE_DIST:?Set the isolated built frontend path}" \
  --output "${PRIVATE_UI_EVIDENCE:?Set a new private evidence path}"
```

The harness copies/integrity-checks the backup, restricts requests and records whether
its read-only copy changed. Screenshots/reports contain private financial information;
keep them outside Git. Browser/package prerequisites must already exist. Missing
prerequisites or failed checks remain blockers, not permission to install/launch live
services. DOM measurements do not replace human visual/accessibility review.
