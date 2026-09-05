# Portfolio route timing rehearsal

Same read-only SQLite backup and Chromium/system-font fixture, three cold-context
samples per route at 390 and 1440px. The baseline is a `git archive` of
`669413693590210749315375c65ec12d0490b4e5`; after measurements use the T15–T23 source.
These local samples are regression evidence, not a general performance benchmark.
API durations are browser resource timing, not isolated server CPU times.

Budgets were recorded before the after run: baseline maximum request count + 4;
API duration max(750ms, 3 × baseline maximum); CLS max(0.1, baseline maximum + 0.03).
The first after run exceeded CLS budgets on Holdings/Returns. Stable table space
and explicit loading states fixed those regressions; the final run passes every
comparable route budget. Existing high CLS on some routes is not claimed WCAG or
Core Web Vitals approval. Groups/Help are newly measured without a before baseline.

| Route | Requests before → after | Max observed API ms before → after | CLS before → after |
|---|---:|---:|---:|
| allocation | 2 → 3 | 36.7 → 30.5 | 0.2248 → 0.2248 |
| classifications | 2 → 2 | 25.9 → 26.9 | 0.2248 → 0.2248 |
| comparison | 4 → 4 | 36.9 → 30 | 0.9889 → 0.9889 |
| confidence | 2 → 2 | 52.9 → 43.3 | 0.2248 → 0.2248 |
| holdings | 5 → 6 | 42.9 → 68 | 0.3151 → 0.2268 |
| income | 3 → 2 | 48.8 → 24.9 | 0.2248 → 0.2248 |
| orders | 4 → 3 | 41.6 → 24.6 | 0.3472 → 0.2248 |
| overview | 4 → 5 | 78.2 → 59.7 | 0.3042 → 0.3042 |
| performance | 7 → 7 | 121.9 → 136.9 | 0.3314 → 0.3314 |
| returns | 5 → 4 | 71.2 → 38.4 | 0.2729 → 0.2248 |

Reproduce (private verified backup, never live startup):

```sh
.venv/bin/python scripts/measure_routes.py --repo "$PWD"   --database /path/to/verified-private-backup.db   --dist /tmp/stocks-experience-dist --output /tmp/stocks-route-timing.json
```

Private raw samples and fixed budgets: `/tmp/stocks-r3-kfu_464p/`.
No fabricated latency improvement or new data-provider coverage is claimed.
