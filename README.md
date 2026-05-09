# Portfolio Tracker (Barclays XLS)

Track and visualize your stock portfolio over time by importing the two `.xls` exports Barclays Stockbrokers makes available:

- `LoadDocstore.xls` / `Portfolio.xls` — point-in-time **portfolio snapshot** (holdings, qty, price, value, book cost, % change).
- `OrderHistory.xls` — your full **order history** (buys, sells, DRIP).

Each snapshot is hashed, deduplicated and persisted, so over time you accumulate a series of snapshots you can diff, chart and use to attribute performance back to actual cash flows.

The goal: clearly see how your portfolio has changed between imports and surface enough context (P&L, CAGR, DRIP vs. discretionary, best/worst movers) to inform what to buy or sell next.

---

## Stack

- **Backend** — FastAPI, Pydantic v2, SQLAlchemy 2 (async), SQLite (`portfolio.db` in repo root)
- **XLS parsing** — `python-calamine` (handles the legacy Barclays `.xls`)
- **Frontend** — React 19 + TypeScript + Vite, Tailwind, TanStack Query, Recharts, Framer Motion, lucide-react
- **Routing** — React Router 7

In production the FastAPI app also serves the built frontend from `frontend/dist`.

---

## Quick start

1. Backend virtualenv + deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Frontend deps:

```bash
cd frontend && npm install && cd ..
```

3. Run both dev servers (in separate shells):

```bash
./start_backend.sh     # uvicorn on :8000
./start_frontend.sh    # vite on :5173 (proxies /api → :8000)
```

Open http://localhost:5173.

To serve everything from a single port, build the frontend (`npm run build`) and run only the backend — `app.main` mounts `frontend/dist` at `/`.

---

## Importing data

### Web UI (`/import`)

Two tabs:

- **Portfolio snapshot** — pick a `LoadDocstore.xls`. The snapshot date defaults to the file's last-modified date, but you can override it. `force` lets you re-import a file with the same hash.
- **Order history** — pick an `OrderHistory.xls`. Set the **DRIP threshold** in the topbar; buys below it are flagged as dividend reinvestments.

### CLI

```bash
cd backend
../.venv/bin/python -m app.import_cli ../data/LoadDocstore.xls
```

Optional flags: `--as-of-date YYYY-MM-DD`, `--force`.

---

## What you get

### `/` Overview
- Hero KPI: latest **portfolio value** with 12-month sparkline + Δ vs. a year ago.
- **P&L**, **effective return** (value + sales − cash deployed), **annualised CAGR**, **cash deployed**, **DRIP reinvested**, **sale proceeds**.
- Three charts (tabs): historical estimate (order-derived qty × current prices), capital deployment, and snapshot history.
- Performance leaders: best/worst % movers in the latest snapshot.

### `/holdings`
- Searchable, sortable table of every instrument in the latest snapshot.
- Click a row to open instrument detail: full historical value/book-cost line chart and the matched orders.

### `/positions`
- Per-security cost basis, DRIP, sells, net cost, current value, estimated P&L and **CAGR**, all derived from order history.
- Open vs. closed tabs; closed tab totals realised P&L.

### `/orders`
- Full order log with DRIP classification and stat cards.

### `/groups`
- Tag instruments with user-defined groups (e.g. "ETFs", "UK income"). Groups feed back into the Overview's `by_group` allocation.
- Set **target weights** per group to track allocation drift on the Overview.

### `/matching`
- Admin panel for the instrument matcher: review unmatched orders, resolve aliases, backfill links, and run reconciliation.
- **Matched Orders tab** — shows every order alongside its matched instrument (name + identifier). Inline dropdown to reassign a different instrument, apply the change, or unmatch entirely. Full audit trail persisted.

### `/import`
- Upload + recent imports list with new / closed counts per batch.
- Click any batch to see a **diff summary** (new, changed, closed instruments vs. the previous import).

### `/diff`
- Pick two import batches and see a per-instrument delta view: additions, removals, quantity/value changes.

---

## Project structure

```
backend/app/
  main.py                      # FastAPI app, lifespan, static mount
  config.py                    # pydantic-settings
  database.py                  # async engine + tiny inline migration
  models.py                    # SQLAlchemy 2 ORM
  schemas.py                   # Pydantic v2 IO models
  import_cli.py                # CLI snapshot importer
  routers/                     # imports, orders, portfolio, instruments, groups
  services/
    barclays_parser.py         # snapshot XLS → ParsedHoldingRow[]
    barclays_order_parser.py   # order-history XLS → ParsedOrderRow[]
    import_service.py          # snapshot ingest + diff vs. previous batch
    order_service.py           # analytics, cashflow, positions, Modified Dietz CAGR
    instrument_matcher.py      # links Order.security_name → Instrument
    order_fingerprint.py       # stable hash → de-dupe orders across imports
    portfolio_service.py       # summary + timeseries, drawdown
    market_data_service.py     # Stooq price refresh
    matching/
      scoring.py               # character / token similarity
      normalisation.py         # name canonicalisation
      candidates.py            # candidate generation
      resolver.py              # alias-based resolution
      audit.py                 # audit trail for matches
backend/tests/
  test_order_service.py      # Modified Dietz, positions
  test_portfolio_service.py  # snapshot metrics, drawdown
  test_import_service.py     # ingest + diff
  test_instrument_matcher.py # matching logic
  test_matching_engine.py    # scoring, normalisation
  test_order_fingerprint.py  # fingerprint stability
  test_hl_parser.py          # HL-format parsing
frontend/src/
  layout/                      # AppShell, Sidebar, Topbar (DRIP threshold)
  routes/                      # Overview, Holdings, Positions, Orders, Groups, Import, Diff, MatchingAdmin
  components/                  # KPIs, charts, tables, panels
  lib/api.ts                   # typed fetch client
  state/usePreferences.ts      # localStorage-backed prefs
data/                          # sample Portfolio.xls / OrderHistory.xls
portfolio.db                   # SQLite (gitignored)
```

---

## Data model (high level)

- `import_batches` — one row per portfolio snapshot import, with `file_sha256` (dedupe), `as_of_date`, and a JSON `diff_summary` of new / changed / closed instruments vs. the previous batch.
- `instruments` — unique by `(account_name, identifier)`. `closed_at` is set automatically when an instrument disappears from a newer snapshot.
- `holding_snapshots` — per-instrument values for a batch (qty, last price, value GBP, book cost GBP, % change).
- `order_import_batches` + `orders` — order history, deduped at row level via `order_fingerprint` (stable SHA over the row's economic identity).
- `instrument_groups` + `instrument_group_members` — user-defined grouping with optional target weights.
- `account_aliases` + `instrument_aliases` — user-defined name mappings to help the matcher resolve orders.

---

## API surface (selected)

```
POST   /api/imports                         # snapshot upload
GET    /api/imports                         # snapshot batches (newest first)
GET    /api/imports/{batch_id}              # single batch details
GET    /api/imports/{batch_id}/diff         # diff summary for a batch
GET    /api/imports/diff                    # compare two batches (SnapshotDiffResponse)
POST   /api/orders/import                   # order-history upload
GET    /api/orders                          # order log
GET    /api/orders/analytics                # totals, DRIP split, annual DRIP
GET    /api/orders/cashflow-timeseries      # monthly/cumulative net deployed
GET    /api/orders/positions                # cost basis + Modified Dietz per security
GET    /api/orders/estimated-timeseries     # qty × current price by month
POST   /api/orders/backfill-instruments     # re-match unlinked orders
GET    /api/orders/unlinked                 # unlinked order summary
GET    /api/portfolio/summary               # totals, by_account, by_group, best/worst
GET    /api/portfolio/timeseries            # value/book-cost per snapshot
GET    /api/portfolio/benchmarks            # SPX / VWRL benchmark data
GET    /api/instruments                     # latest-snapshot instruments
GET    /api/instruments/{id}/history        # all snapshots for one instrument
GET    /api/instruments/{id}/orders         # matched orders
POST   /api/instruments/{id}/quote          # refresh price via Stooq
GET    /api/groups                          # CRUD + PUT /{id}/members
GET    /api/matching/summary                # matcher admin summary
GET    /api/matching/unmatched-groups       # unmatched order groups
GET    /api/matching/candidates             # candidates for an unmatched order
GET    /api/matching/reconciliation         # reconciliation rows
POST   /api/matching/resolve-group          # resolve a group of unmatched orders
POST   /api/matching/orders/{order_id}/resolve   # resolve an individual order
POST   /api/matching/orders/{order_id}/unmatch   # unmatch an individual order
POST   /api/matching/backfill               # bulk backfill
GET    /api/matching/account-aliases        # CRUD account aliases
GET    /api/matching/instrument-aliases     # CRUD instrument aliases
GET    /api/health
```

---

## Persistence & determinism

- Snapshot files are content-hashed, so re-uploading the same file is rejected (use `force` to override).
- Orders are de-duped by `order_fingerprint`, which makes re-importing a longer order history safe and idempotent.
- `init_db()` runs `Base.metadata.create_all` plus a small inline migration that backfills `order_fingerprint` and drops dupes.
- **Tests**: 7 pytest modules cover parsers, order service (Modified Dietz), portfolio service (drawdown), import service, instrument matcher, matching engine, and order fingerprint stability.

---

## Roadmap / known gaps

### ✅ Completed

1. Snapshot diff surfaced in import history ✅
2. Snapshot-vs-snapshot comparison view (`/diff`) ✅
3. Concentration & allocation risk on the Overview (weight, drift vs. group targets) ✅
4. Live price refresh via Stooq (`POST /api/instruments/{id}/quote`) ✅
5. Modified Dietz per-position time-weighted return ✅
6. Benchmark overlay (SPX / VWRL) on the historical-estimate chart ✅
7. Drawdown per holding (peak-to-current) with near-peak filter ✅
8. Matched Orders tab shows instrument name + identifier with inline reassign/unmatch ✅

### 🔲 Remaining

8. **UK CGT view** — realised gains by tax year, with section 104 / same-day / 30-day matching.
9. **Push aggregations into SQL** — `portfolio_value_timeseries` still does N round-trips.
10. **Alembic migrations** — still using `Base.metadata.create_all` with inline migration.
