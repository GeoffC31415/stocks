# Portfolio Tracker (Barclays XLS)

Track and visualize your stock portfolio over time by importing `LoadDocstore.xls` snapshots from Barclays Stockbrokers.

## Stack

- Backend: FastAPI, Pydantic v2, SQLAlchemy 2 (async), SQLite
- XLS parsing: `python-calamine` (works for this legacy Barclays `.xls`)
- Frontend: React + TypeScript + Tailwind + TanStack Query + Recharts

## Quick start

1. Create and activate a virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

3. Run backend API:

```bash
cd backend
../.venv/bin/uvicorn app.main:app --reload
```

4. Run frontend:

```bash
cd frontend
npm run dev
```

Frontend is available at `http://localhost:5173` and proxies API requests to `http://localhost:8000`.

## Importing Barclays snapshots

### Web UI

- Use the upload panel and select your latest `LoadDocstore.xls`.
- Optional: set `as_of_date` (YYYY-MM-DD) if you want a specific snapshot date.
- Use `force` if you intentionally need to import a duplicate file hash.

### CLI

```bash
cd backend
../.venv/bin/python -m app.import_cli ../data/LoadDocstore.xls
```

Optional flags:

- `--as-of-date 2026-04-04`
- `--force`

## Data persisted locally

- SQLite DB file: `portfolio.db` (repo root)
- Tracks:
  - Import batches and file hash dedupe
  - Instruments and holdings snapshots over time
  - New/sold/changed detection between imports
  - User-defined groups and group membership
