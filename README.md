# Portfolio Tracker

A private portfolio analysis app combining imported holdings snapshots and order history. It supports Hargreaves Lansdown CSV exports, local Barclays XLS imports, and read-only Trading 212 API sync. Snapshot values describe their import valuation dates, not live market wealth. Orders and snapshots are deduplicated; neither source proves complete cash-flow or dividend coverage.

## Workspaces

| Destination | Purpose |
| --- | --- |
| `/` | Dashboard: current state, changes, and investigation entry points |
| `/portfolio?tab=performance` | Snapshot-based actual-portfolio performance, covered dates, attribution and confidence |
| `/portfolio?tab=holdings` | Latest account positions and instrument details |
| `/portfolio?tab=returns` | Lifetime order-derived position returns, not the shared performance period |
| `/portfolio?tab=allocation` | Exposure, concentration, eligible target drift and hypothetical contributions |
| `/portfolio?tab=income` | Recorded reinvestment purchase proxy, calendar comparisons and drivers |
| `/portfolio?tab=groups` | Group membership and targets (the currently implemented Groups destination) |
| `/activity?tab=orders` | Paginated order investigation with search, type, account and independent date filters |
| `/activity?tab=changes` | Compare selected snapshot pairs |
| `/activity?tab=imports` | Import history and source records |
| `/data?tab=import` | Preview/import files and explicitly requested quote refresh |
| `/data?tab=matching` | Match repair and exceptions |
| `/data?tab=classifications` | Instrument metadata repair |
| `/data?tab=confidence` | Coverage, warnings and source-specific repair workflow |
| `/data?tab=settings` | Analysis preferences and limitations |
| `/tax` | Estimated UK capital gains by tax year; not tax advice |
| `/help` | Metric explanations, scope exceptions and scoped investigation links |

**Route caveat:** `DataWorkspace` currently exposes `import`, `matching`, `classifications`, `confidence`, and `settings`, not `groups`. Do not use `/data?tab=groups` until the route is actually wired; Groups remains under Portfolio.

Legacy URLs remain redirects: `/holdings` → Portfolio Holdings, `/positions` → Returns, `/groups` → Portfolio Groups, `/orders` → Activity Orders, `/diff` → Changes, `/import` → Data Import, `/matching` → Data Matching, and `/cgt` → Tax. Query parameters survive redirects, including legacy `inst` instrument links such as `/holdings?inst=42`. Help uses `scopedNavigationUrl` to preserve the current account, period and investigation parameters while replacing the workspace tab. Explicit destination parameters take precedence.

## How to interpret the analysis

### Current state, performance and risk are different

- **Current holdings:** latest snapshots for the selected accounts. Check dates, missing account coverage and cash treatment before comparing totals.
- **Actual-portfolio performance:** a snapshot-boundary, flow-adjusted Modified Dietz estimate. Dietz is an estimated money-weighted method, not exact time-weighted return. Observe the disclosed covered dates and whether a figure is cumulative or annualised.
- **Position gain/cost:** unrealised gain against recorded book cost. Lifetime position MWR includes transaction timing; neither is interchangeable with selected-period portfolio performance.
- **Past holdings valued at today’s prices:** order-derived quantities valued at current prices. This renamed reconstruction is not historical portfolio wealth, benchmarked actual return, or a valid performance benchmark overlay.
- **Current-composition risk:** historical modelling of today's holdings, not a record of what the investor actually held. Missing history must remain unavailable, not replaced with fabricated analytics.
- **All-account history:** the Dashboard retains the longest available account history. When an account first appears, its first observed value is added as a scope baseline rather than being treated as investment return; subsequent changes participate normally. This makes the return representative over the full available period while clearly distinguishing account-scope additions from market performance.

For accounts with successfully synced Trading 212 cash history, external flows are actual API deposits less withdrawals; purchases and sales are internal and are not counted again. Other accounts retain observed non-DRIP buy contribution proxies and sale withdrawal proxies where retained cash cannot be distinguished from money leaving the account. The residual after observed flows and reinvestment is **not pure price effects**: FX, fees, missing transactions, timing and valuation differences can contribute. Holding contribution attribution is not a causal price decomposition.

The shared period applies to Performance. Holdings, allocation and groups use latest snapshots; Returns uses lifetime transactions. Income uses its own calendar comparison and trailing windows; Tax uses the chosen tax year; Changes uses the selected snapshot pair. Matching/classification repair queues may span all accounts. Orders has its own search and `from_date`/`to_date` filters. Full-filter totals cover all matching orders independently of pagination; changing the query must update totals, while changing only the page must not redefine their scope.

### Security identity, concentration and targets

Security aggregation is conservative. The reviewed registry currently approves only EQQQ with exact source identifier `EQQQ`, ISIN `IE0032077012` or SEDOL `B0GL4T3`, listing `EQQQ` on `XLON`, provider mapping `EQQQ.L`, and supported source value currency `GBP`/`GBX`/`GBp`. The unchanged source currency remains part of the key. Similar names or editable tickers cannot merge unsupported identifiers, listings, currencies or share classes. Broker records are not rewritten. See [reviewed identity evidence](docs/security-identity.md).

HHI measures displayed weight concentration, **not diversification or fund overlap**. Product-level classifications are not constituent look-through. Two apparently separate funds can own the same underlying companies.

Target comparison requires a complete, exclusive target set: every eligible holding belongs to exactly one group, targets sum to **100% within ±0.01 percentage points**, and the cash-excluded invested scope has positive value. Invalid/overlapping/incomplete sets are unavailable, not silently normalised. Drift is measured in percentage points; personal tolerance is a user preference, not investment advice.

Contribution scenarios use hypothetical user-entered amounts. They execute no trades, transfer no money, and do not change holdings or real cash. Cash is excluded from the model; a result is not a funded order or recommendation.

### Income is a purchase proxy

Income uses **backend-stored import classification**, not a retrospective application of today's threshold. Threshold changes do not rewrite historical purchases. Reinvestment purchases are not declared/cash dividends and are not a complete dividend ledger.

Matched YTD compares the current calendar period with the same prior-year calendar period, not a partial current year with a complete prior year. February 29 is clamped to February 28 when the prior year has no leap day. Check the comparison endpoint and latest recorded transaction date. Completeness remains unknown; months without recorded purchases are `null` (displayed as unavailable/dash), not confirmed zero income.

Drivers retain current, closed and unlinked records. Current/closed status uses latest snapshots independently of the comparison period. Matching-purchase links carry account, instrument, stored DRIP kind and applicable dates into Orders; unlinked rows lead to their source records. Orders uses `kind=drip`, not `type=drip`.

### Repair workflow

Start at Data confidence; identify affected accounts, dates and source records. Verify the broker file and import coverage, then resolve only evidenced matching/classification exceptions. Review the source account because repair queues can include all accounts. Keep a verified private backup before imports or bulk changes, refresh derived data afterward, and recheck confidence. Healthy matching alone does not prove complete cash-flow, market-history or income coverage.

## Trading 212 read-only sync

Use **Data → Import → Sync Trading 212** for a complete observation: positions,
verified account-summary cash, completed fills/order history, and deposits/withdrawals.
The key needs read-only portfolio, account-summary, historical-order and
historical-transaction (`history:transactions`) permissions, never order placement.
Missing account-summary permission **rejects the observation**; there is no
positions-only successful fallback. Trading 212 buys are ordinary buys, not inferred DRIPs.

In public/service mode the button requests the dedicated worker through
`/api/sync/trading212/request` and polls that same endpoint. Web credential status
is not worker credential availability. Credentials belong to the worker's private
configuration, not the public web environment. Local development retains direct
provider routes; use only deliberately provisioned test credentials and a disposable
DB. See [sync guidance](docs/sync-reliability-operator-notes.md) and
[ingest safeguards](backend/docs/sync-integrity-operator.md).

An unchanged observation is reported as unchanged; rechecks still consume rate
limits. Changed observations are retained even on the same day. Cash events deduplicate
by account/provider reference. The combined operation fetches all sections before
writes and commits snapshot, orders and cash atomically, rolling back on failure or
cancellation. A successful validated Trading 212 positions snapshot is authoritative
for current holdings: ordinary sales, including selling the last holding to leave
only verified cash, need no operator closure review or inferred SELL history.
Missing securities are marked closed in the new snapshot; historical snapshots,
orders and cash events are retained. Malformed or incomplete required data still
rejects the entire combined sync.

### Cash deposits and withdrawals

Full paginated transaction history imports deposits positively and withdrawals
negatively; fees and cash/lending interest are not external funding. Ambiguous
transfers, unsupported currencies (only GBP), malformed records and conflicting
references reject the sync. Missing transaction permission changes no ledger rows.
A separately requested local cash-history refresh writes the ledger/coverage marker,
not snapshots or trades; the combined button imports all sections together.

A successful empty history proves zero reported funding and suppresses buy/sell
proxies for that account. Unavailable history does not. Coverage means all pages
returned by the API, not an independent audit. Cash history must be fetched after
the closing snapshot cutoff, including its time for same-day API snapshots.
Opening-date flows are assumed already valued and excluded. Closing cutoff is the
API observation time or end of day for dated file snapshots; later movements are
excluded. Daily Dietz weighting and opening-day timing remain approximations.

## Development and operations

Backend: FastAPI, Pydantic, async SQLAlchemy and SQLite. Frontend: React,
TypeScript, Vite and TanStack Query. Dependencies: `requirements.txt` and
`frontend/package.json`; production runtime lock: `requirements-production.txt`.

Normal application startup can create/migrate the database. Never start it against
live data for verification, edit a running reload checkout, or overwrite the served
frontend build. Imports, repairs and provider refreshes are writes, not read-only checks.

- [Development checks and isolated previews](docs/sync-reliability-operator-notes.md#development-checks-and-isolated-previews)
- [Deployment and recovery boundary](docs/simple-release.md)
- [Public hosting and backups](docs/public-hosting.md)
- [Passkey usage and local recovery](docs/passkeys.md)
- [Market-data limitations](docs/market-data.md)
- [Documentation index](docs/README.md)

Portfolio databases, source exports, credentials, browser profiles, auth stores and
screenshots are private and stay outside Git. Snapshot hashes and order fingerprints
deduplicate source data; aliases and classifications do not establish security identity.
Tests establish source behaviour, not provider completeness or production readiness.
