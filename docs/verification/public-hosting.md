# Public-hosting verification on Surface Pro 4

Scope: repository preparation only. No production service, router/firewall rule,
public DNS record, public certificate, user login or real-portfolio migration was
created. Existing Grafana and Hermes services were left unchanged.

## Executed checks

- `scripts/verify_public_hosting.py` ran the actual Caddy 2.11.4 proxy, Uvicorn,
  migrated disposable SQLite database and built React UI on loopback-only ports.
  Caddy's archive was checked against the release's SHA-512 checksums before use.
- Unauthenticated UI/API reads and writes returned 401. Authenticated health/deep
  links worked, absent/wrong Origin rejected writes, unknown API/assets remained 404.
- API requests validated the temporary TLS certificate against the private test CA.
  The browser used a local-test-only certificate exception; no CA was installed in
  the system trust store. This does **not** verify a public certificate.
- A real authenticated Chromium page used same-origin fetch to create a synthetic
  group, read it back from SQLite, delete it and confirm its absence. No broker API
  or actual portfolio data was involved. Desktop Groups and mobile Holdings rendered
  without console/page errors. Their screenshots were visually inspected: desktop
  layout coherent, mobile table intentionally horizontally scrollable with navigation
  and empty state visible. This was not a full interactive UX audit of every page.
- All rehearsal subprocesses were stopped and waited for; listeners matched the
  initial host state afterward. No public web server is left running.

Final rehearsal evidence at preparation time:
`/tmp/stocks-https-rehearsal-reviewed/report.json`, `desktop.png`, `mobile.png`.
Temporary evidence is not durable backup storage.

## Regression and dependency gates

Commands used the repo virtualenv, with
`PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory:` for backend tests.
The clean baseline was run from a detached worktree of `53ba329` using the same
interpreter/dependencies as the final code.

- Backend baseline: **446 passed, 7 failed**.
- Backend final: **623 passed, 7 failed**. JUnit failure identifiers match exactly;
  **177 additional tests pass**, with no additional failing tests.
- Existing backend failures: two missing private HL CSV fixtures; three tests that
  introspect the old flat FastAPI route representation; two UI tests hardcoding
  `/usr/bin/google-chrome`, absent on this Surface. The new rehearsal successfully
  uses the available Chromium executable instead.
- Final full backend run also emitted five asynchronous SQLite thread-cleanup
  warnings. The focused security tests and HTTPS rehearsal passed; this report does
  not describe the entire suite as warning-free.
- Frontend: **183 passed, 2 failed** before and after dependency updates. Both are
  existing compact-currency formatting expectations (`£250k` vs `£250.0k`, etc.).
- Frontend TypeScript check and isolated production build passed. Vite still warns
  about a large bundle; this is not a clean performance-budget result.
- Ruff: **30 baseline → 28 final**, no new findings by file/code/message comparison.
  All new security/deployment source and test files passed their focused Ruff gate.
- Mypy: **23 baseline → 23 final**, existing errors remain outside the new security
  implementation. Do not describe whole-repo type checking as clean.
- Independent review found one database-factory isolation defect; it was fixed and
  re-reviewed successfully. The reviewer ran 155 targeted tests, and its source hashes
  matched the final files when checked by the parent agent. This is code-review
  evidence, not a penetration-test or public deployment certification.
- `git diff --check` passed.
- A transient user-systemd service round-tripped the generated EnvironmentFile with
  quoted punctuation in its synthetic username, spaces in paths and literal scrypt
  dollar signs intact. No persistent service was installed.
- A final factory guard rejects conflicting per-app database settings before app
  construction; six sentinel-database tests prove neither database is connected or
  changed. Set the database environment before importing the app.
- `npm audit` (all dependencies) and `pip-audit --require-hashes -r
  requirements-production.txt` reported **no known vulnerabilities**. This is a
  point-in-time database check, not proof of absence of vulnerabilities.
- Caddy validated the bundled template and ran its loopback rehearsal variant.
  The uninstalled systemd unit could not validate its final executable path because
  `/opt/stocks/current/.venv/bin/python` does not exist yet. Its installation,
  sandboxed execution and reboot behavior still need the operator's deployment gate.

## Reproduce the HTTPS rehearsal

Build to an isolated directory, then supply an existing Caddy binary and a **new**
output directory (the script refuses an existing one):

```sh
npm --prefix frontend run build -- --outDir /tmp/stocks-rehearsal-dist
.venv/bin/python scripts/verify_public_hosting.py \
  --caddy /path/to/caddy \
  --dist /tmp/stocks-rehearsal-dist \
  --output /private/temp/new-stocks-rehearsal
```

Requires Python Playwright, an installed Chromium/Google Chrome executable, and
runtime dependencies. It does not install packages, start persistent services,
read the working portfolio or contact a broker.

See [public hosting](../public-hosting.md) for real-data backup, deployment, final
hostname/login selection, network access checks and rollback. Public readiness
must not be inferred from the local rehearsal alone.
