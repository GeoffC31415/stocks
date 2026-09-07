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

Observed non-DRIP buys are contribution proxies; sales are treated as withdrawal proxies where retained cash cannot be distinguished from money leaving the account. The residual after observed flows and reinvestment is **not pure price effects**: FX, fees, missing transactions, timing and valuation differences can contribute. Holding contribution attribution is not a causal price decomposition.

The shared period applies to Performance. Holdings, allocation and groups use latest snapshots; Returns uses lifetime transactions. Income uses its own calendar comparison and trailing windows; Tax uses the chosen tax year; Changes uses the selected snapshot pair. Matching/classification repair queues may span all accounts. Orders has its own search and `from_date`/`to_date` filters. Full-filter totals cover all matching orders independently of pagination; changing the query must update totals, while changing only the page must not redefine their scope.

### Security identity, concentration and targets

Security aggregation is conservative. The reviewed registry currently approves only EQQQ with exact ISIN `IE0032077012` or SEDOL `B0GL4T3`, listing `EQQQ` on `XLON`, provider mapping `EQQQ.L`, and supported source value currency `GBP`/`GBX`/`GBp`. The unchanged source currency remains part of the key. Similar names or editable tickers cannot merge unsupported identifiers, listings, currencies or share classes. Broker records are not rewritten. See [reviewed identity evidence](docs/security-identity.md).

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

Create a Trading 212 API key with portfolio and historical-order read permissions only; do not grant order-placement permissions. Copy `.env.example` to `.env` and set:

```dotenv
PORTFOLIO_TRADING212_API_KEY=...
PORTFOLIO_TRADING212_API_SECRET=...
PORTFOLIO_TRADING212_ACCOUNT_NAME=Trading 212
```

Restart the backend after changing `.env`, then use **Data → Import** to sync the current snapshot or completed order history. The `.env` file is ignored by Git. A key without account-summary permission still imports positions, but deliberately omits cash because the API cannot verify it. Trading 212 purchases are imported as ordinary buys rather than inferred DRIPs.

## Development and safe verification

Backend: FastAPI, Pydantic, async SQLAlchemy and SQLite. Frontend: React, TypeScript, Vite, TanStack Query, Tailwind and React Router. Dependencies are declared in `requirements.txt` and `frontend/package.json`.

Normal backend startup can run schema creation and inline migrations. Production serves `frontend/dist`. **Do not start the normal application against a live database for verification, and do not overwrite the live frontend build.** Imports, match repairs and provider refreshes are writes requiring appropriate approval. This guide authorises no deployment, backfill or live refresh.

With existing dependencies, run from the repository root:

```bash
npm --prefix frontend test -- --run Help
npm --prefix frontend run typecheck
# Full frontend regression suite when integrating:
npm --prefix frontend test -- --run
# Isolated output only; never use the normal frontend/dist for rehearsal:
npm --prefix frontend run build -- --outDir /tmp/stocks-experience-dist
```

For browser integration, first obtain a **verified private SQLite backup**, outside the repository, made with SQLite's backup API (a raw copy of a WAL-mode file is not sufficient). Confirm its integrity and preservation evidence; never substitute an invented backup filename or skip that prerequisite. Set the following paths to the actual verified backup and a private, non-repository evidence directory:

```bash
# PRIVATE_VERIFIED_BACKUP and PRIVATE_UI_EVIDENCE must be explicitly set first.
.venv/bin/python scripts/verify_analysis_ui.py \
  --database "${PRIVATE_VERIFIED_BACKUP:?Set the verified private backup path}" \
  --dist /tmp/stocks-experience-dist \
  --output "${PRIVATE_UI_EVIDENCE:?Set a private evidence directory}"
```

The rehearsal script makes an integrity-checked copy, serves audited GET routes with read-only SQLite and lifespan disabled, blocks mutations, and records whether its copy changed. It uses existing Playwright/Chrome; do not install packages or launch production services as an implicit fallback. Screenshots/reports contain private portfolio information and must stay outside Git. Browser evidence is not automatic visual acceptance: contrast, chart clarity and screenshots still need review. Record failures and missing evidence honestly.

## Structure and persistence

- `backend/app/routers/`, `services/`, `schemas.py`, `models.py`: API, analytics, imports and persistence.
- `frontend/src/routes/`, `components/`, `lib/`, `state/`: workspaces, analysis UI, typed clients and shared scope.
- `backend/tests/`, frontend `__tests__/`: service and component regressions.
- `scripts/verify_analysis_ui.py`: isolated read-only UI rehearsal.
- `portfolio.db`: private working database, ignored by Git. Import files and browser evidence are private too.

Snapshot hashes deduplicate imports; order fingerprints deduplicate source rows. Instruments retain account-specific identity and dated holding snapshots. Group memberships, classifications and matching aliases are persisted metadata, not proof of security identity or complete histories.

## Gated extensions and release boundary

D01–D04 remain data- and approval-gated, not declared ready by this documentation:

- **D01:** validated market/FX history, instrument identities, coverage and comparable benchmarks; sample provider responses do not establish full-portfolio readiness or permission for persistent backfill.
- **D02:** current-composition risk and historical loss analysis depend on D01 and explicit horizon/coverage requirements.
- **D03:** reproducible scenario fans require D01–D02 plus separate acceptance of model assumptions.
- **D04:** fund look-through requires validated constituent data and coverage, not ticker matching or product classifications.

See the [implementation plan](docs/plans/2026-09-04-portfolio-experience.md), [verification evidence](docs/verification/portfolio-experience.md), and [market-data limitations](docs/market-data.md). Tests establish implementation behaviour, not provider readiness or release approval. Deployment is a separate, explicitly authorised operation with rollback planning.
