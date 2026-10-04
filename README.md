# Portfolio Tracker

Private portfolio analysis with manual HL/Barclays imports and read-only Trading
212 sync. Snapshot values are dated observations, not live market wealth.

## Start here

- [Development, release and cleanup workflow](docs/workflow.md)
- [Documentation index](docs/README.md)
- [Analysis semantics and limitations](docs/analysis.md)
- [Trading 212 service sync](docs/trading212-service-sync.md)

## Application

| Workspace | Purpose |
| --- | --- |
| Dashboard `/` | Portfolio state and investigation entry points |
| Portfolio `/portfolio` | Performance, holdings, returns, allocation, income, groups |
| Activity `/activity` | Orders, snapshot changes, import history |
| Data `/data` | Manual imports, Trading 212 sync, matching, classifications, confidence, settings |
| Tax `/tax` | Estimated UK capital gains, not tax advice |
| Help `/help` | Metric definitions and scoped investigation links |

Groups live under Portfolio, not Data. Performance uses its selected period;
Holdings/Allocation use latest snapshots; Returns uses lifetime transactions.
Unavailable coverage is not zero, and successful sync is not an independent audit
of broker history. See the analysis guide before interpreting results.

## Development and checks

There is one active source checkout per machine: `~/code/stocks`. Production runs
from root-owned releases on the Surface, never from this checkout.

Use an isolated development database made from a verified WAL-aware production
snapshot. Do not start development against the production database. Never upload
a development database to production or commit portfolio data, credentials,
browser sessions or screenshots.

```sh
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Vite and backend reload support interactive development. The proposed unified
`stocks dev`, `stocks refresh` and `stocks publish` commands are **not yet
implemented**; see the workflow document for requirements and existing tooling.

## Production

- Canonical portfolio database: `/var/lib/stocks-data/portfolio.db` on the Surface.
- Website: `stocks.service` behind `stocks-proxy.service`.
- Trading 212 button: `stocks-t212-sync.service`, isolated from the web process.
- Deployment: installed `stocks-release` controller with explicit authorization,
  rehearsal, compatibility checks, recovery record and post-deploy verification.
- Barclays is manually imported; there is no combined-sync control on the Data page.

Do not expose development ports to the public internet. Do not silently change
broker timers, credentials, migration policy or deployment permissions.

Historical plans, handoffs and retired agent work are archived outside the source
checkout under `~/archives/stocks-docs` and `~/archives/stocks-retired`. They are
recovery material, not current instructions. Source branches remain in Git until
explicitly reconciled; deployed code does not imply it has reached `master`.
