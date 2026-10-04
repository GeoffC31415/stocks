# Hosting and private persistence

See [deployment](simple-release.md) for the sole release entrypoint and
[passkeys](passkeys.md) for authentication/recovery. This is a single-owner app,
not a multi-user financial service. Repository templates describe intended policy;
inspect effective installed units/drop-ins before changes, not just these files.

## Network and authentication

The intended public origin is exactly `https://solarpi.hopto.org:5000`.
Caddy on the Surface terminates TLS and proxies to loopback `127.0.0.1:8000`.
Keep existing Grafana forwards on 3000/4000 unchanged. Do not forward backend,
Vite, preview or proxy-admin ports publicly, weaken TLS validation or trust forwarded
headers from arbitrary peers. The source backend template uses one Uvicorn worker
and trusts proxy headers only from loopback.

A hostname certificate also works on port 5000, but forwarding 5000 alone does not
provide ACME HTTP-01 (80) or TLS-ALPN-01 (443). Verify actual issuance/renewal,
DNS/IPv6, router/firewall, DHCP reservation and Surface power/reboot behaviour.
Do not overwrite other services' port forwards or enable hostname-wide HSTS without
checking every service on that hostname. External reachability requires an external
client test, not local curl/hairpin NAT. No fixed LAN address or certificate status
is asserted here. A private VPN is an alternative requiring separate configuration.

Local deployment mode is loopback-only. Public mode validates HTTPS origin and the
configured auth mode; passkey mode protects financial APIs while permitting a bounded
login shell/assets/auth ceremonies. Basic is supported compatibility mode, not a
passkey fallback. Unsafe public requests require exact Origin. Body/concurrency limits,
no-store/security headers and sanitized errors reduce abuse; they are not DDoS protection.

## Web and broker boundaries

Source [web unit](../deploy/stocks.service) and
[worker unit](../deploy/stocks-sync.service) separate `stocks` and `stocks-sync`.
Both intentionally share the portfolio DB through `stocks-data`; this isolates broker
credentials/private state, not the worker's ability to alter portfolio data.

- `/var/lib/stocks`: web-private authentication store/control markers.
- `/var/lib/stocks-sync`: worker-private browser, inbox and HOME.
- `/var/lib/stocks-data`: shared portfolio DB and WAL/SHM files.
- `/var/lib/stocks-status`: sanitized worker-written, web-readable status.
- `/etc/stocks/production.env`: private web configuration; no broker credentials.
- `/etc/stocks/brokers.env`: private worker configuration; no web authentication settings.

These are layout contracts, not proof of installed permissions. Verify effective
identities, supplementary groups, sandbox paths and runtime readability as the real
service identities; root-readable code alone proves little. Never copy dotenv files,
credentials, broker exports/profiles or databases into a served code release.

## Backups and recovery

Before imports, repairs or schema-changing work, obtain an authorized consistent
SQLite snapshot using its backup API, not a raw copy of an active WAL database.
The current helper is [scripts/deployment.py](../scripts/deployment.py); because
it imports configuration at module load, use an isolated checkout with no dotenv
files and a cleared/private environment. Example on an **explicit disposable source**:

```sh
PYTHON_DOTENV_DISABLED=1 PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  /home/geoff/code/stocks/.venv/bin/python scripts/deployment.py backup \
  --source "${DISPOSABLE_DB:?Set the disposable source path}" \
  --output "${PRIVATE_BACKUP:?Set a new private backup path}"
```

For production, use only the separately authorized installed backup capability;
this example grants no live DB access. The helper refuses missing source/existing
output and checks SQLite integrity. Ensure a private parent directory and verify
content/counts plus disposable restore, not integrity alone. Keep encrypted off-machine
copies and deliberately reviewed retention; same-machine history is not disaster recovery.

Normal app startup runs schema initialization/migrations. Never start it on a live
DB for verification or run direct Alembic against the old INI default. Schema/runtime/
proxy changes are outside the code-only release contract. A data restore requires
quiesced writers, preservation of incident evidence and explicit acceptance of lost
post-backup writes; code rollback must not silently restore data or auth sessions.
