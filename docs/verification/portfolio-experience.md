# Portfolio experience verification

## T00 — Safe baseline

Implementation branch: `feature/portfolio-experience`, starting at `fa34371`.
The starting working tree was clean (the plan's dirty-tree warning is historical).
No pre-existing modified/untracked files were present. Tracked-file SHA-256
manifest and complete diagnostics are in private evidence outside the repository.

### Safety

- `portfolio.db` and `portfolio.db.bak` both pass `git check-ignore`.
- SQLite online backup created outside the repository in a mode-0700 directory.
  Read-only source transaction, backup `integrity_check = ok`, complete logical
  dump equality, and unchanged source SHA-256 verified before implementation.
- Test fixtures inspected: module-local in-memory engines; HTTPX ASGI transports
  do not run lifespan. Baseline commands additionally set
  `PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory:`.
- `app.main` lifespan runs migrations. The rehearsal instead builds a separate
  app from audited GET routes, with its **own read-only dependency provider**;
  no copied original lifespan. Mutation methods are rejected server-side and
  browser requests are restricted by route-specific GET allowlists.
- Provider GETs/refreshes are not allowed. Offline font CSS uses system fonts;
  comparisons therefore do not claim identical typography to the historical review.
- Child failure detection, readiness deadline, terminate/kill cleanup and copied
  DB hash preservation are tested. No installation, live restart, migration,
  provider refresh, personal-data edit or deployment occurred.

### Fresh initial gates

| Command | Observed result |
|---|---|
| `.venv/bin/pytest -q` | 229 passed |
| `npm --prefix frontend test -- --run` | 59 passed, 23 files |
| `npm --prefix frontend run typecheck` | passed |
| `make lint` | inherited: 101 ruff diagnostics |
| `make typecheck` | inherited: 32 errors in 7 files |
| `npm --prefix frontend run build -- --outDir /tmp/stocks-experience-dist` | passed; existing large-chunk warning |

Full ruff JSON (path/code/message/location) and mypy diagnostics are retained
privately for identity comparisons, not merely count comparisons. `make check`
was not used because it runs mutating formatting. Live `frontend/dist` untouched.

### Reproduced defects (not passes)

`test_invalid_common_chain_cannot_publish_a_curve_or_drawdown` failed semantically:
a duplicate-date input gives an unavailable cumulative KPI but a nonempty partial
curve. Temporarily strict-xfailed for T01, not counted as a passing acceptance test.
The rendered synthetic SVG fixture detects repeated/overlapping date labels and
inverted losses. Six harness safety/geometry tests pass.

The isolated browser command ran all seven routes at 320/390/768/1440px. It
**exited nonzero: 11 of 28 route/width combinations failed**, retaining all
measurements/screenshots instead of stopping at the first defect. Required API
responses and content headings were observed on all routes; no API/page errors.

| Route | 320px document | 390px document | 768px document | 1440px document |
|---|---:|---:|---:|---:|
| Overview | 320 | 390 | 768 | 1440 |
| Holdings | 900 | 900 | 908 | 1440 |
| Income | 524 | 524 | 768 | 1440 |
| Orders | 620 | 620 | 768 | 1440 |
| Allocation | 320 | 390 | 768 | 1440 |
| Returns | 320 | 390 | 768 | 1440 |
| Classifications | 320 | 390 | 768 | 1440 |

Overview reproduces invalid performance with a published curve, duplicate and
overlapping ticks, and inverted drawdown at all widths; clipped controls at
320/390px. Default height: 3478px desktop, 5825px at 390px. Performance heading:
y=1110.5 desktop, y=1707.5 at 390px. These are a new offline-font baseline.
Screenshots captured; image/manual visual acceptance is **outstanding**.
Numerical correctness and successful geometry checks are separate claims.

### Reproduction

```sh
PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  .venv/bin/pytest backend/tests/test_experience_contracts.py backend/tests/test_ui_rehearsal.py -q
npm --prefix frontend run build -- --outDir /tmp/stocks-experience-dist
.venv/bin/python scripts/verify_analysis_ui.py \
  --database /path/to/verified-private-backup.db \
  --dist /tmp/stocks-experience-dist --output /tmp/stocks-experience-ui
```

Private evidence location for this session is recorded in
`/tmp/stocks-experience-evidence-path`; do not commit its contents or screenshots.
Remaining release tasks are tracked only in the implementation plan. This is
verification evidence, not a second progress ledger. R1–R3 are not released.
