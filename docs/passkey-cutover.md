# Final passkey-only cutover (operator gate)

Do not execute until independent security/specification review and explicit physical
Surface root approval. The helper is stdlib-only; tests use disposable databases,
mocked HTTP/service adapters, and no production credentials or portfolio database.

## Owner gate

1. Complete isolated deployment, leaving Basic migration mode enabled.
2. On the gaming PC, enroll the intended Dashlane passkey, then perform an actual
   passkey **authentication** within ten minutes of cutover. Registration alone is
   insufficient: `credentials.last_used_at` must be set by verified authentication.
3. Separately confirm Dashlane selection with the owner. The database proves a
   verified WebAuthn ceremony, **not** the password-manager vendor or physical device.
4. Confirm an accepted local-admin recovery route / independent backup credential.
   Do not disclose grants, database contents, environment values, or passwords.

## Explicit command (not executed during development)

From an approved root shell on **geoff-Surface-Pro-4**, replace `RELEASE_NAME` with
the exact reviewed installed release name (do not substitute a dynamically resolved
`current` value or run from a user-writable checkout):

```sh
/usr/bin/python3 /opt/stocks/releases/RELEASE_NAME/deploy/passkey_cutover.py \
  --expect-current /opt/stocks/releases/RELEASE_NAME --confirm PASSKEY-ONLY
```

The release must already contain this reviewed helper. It checks the isolation
marker's private bundle, manifest release, state-complete and activation-complete
markers, and rejects rollback evidence. Exact public origin and auth database path
are required. Config/auth/evidence paths must be private, owned, non-symlink and
single-linked; ancestor directories must not be group/world writable. The auth
store belongs to `stocks`, config and backups to root. Existing `/var/backups/stocks`
must be root-owned mode 0700; the helper will not silently repair unsafe permissions.

The conservative existing env parser rejects duplicate/unknown keys and ambiguous
syntax. Session lifetime overrides not recognized by that parser currently refuse
cutover; review allowlist support separately rather than weakening parsing. No
broker file or portfolio database is read. No timer, broker service, or proxy is
changed.

Before replacing config it creates a unique private `passkey-*` bundle containing
0600 original config, SQLite-backup-API auth snapshot (integrity checked), and a
secret-free manifest. Treat **all** these files as sensitive; the config snapshot
contains the old password hash and is operator evidence only, never a fallback.
The config replacement preserves other lines, selects `AUTH_MODE=passkey`, and
removes `AUTH_USERNAME` and `AUTH_PASSWORD_HASH`. Only `stocks.service` is stopped
and started. Installed config and exact release are read back.

Public probes use HTTPS with normal certificate validation, the public hostname,
and curl `--resolve` to loopback, no cookies/auth/proxy/curlrc, no redirects:

- `/api/auth/session`: 200, `mode=passkey`, `authenticated=false`.
- Anonymous `/api/health`: 401.
- `/` with `Accept: text/html`: 200 sign-in shell.

This verifies the local public-origin boundary, not external DNS/router reachability
or an authenticated health request. Existing auth sessions remain in the store.
Afterward the owner must log in from the intended external client and verify the
portfolio UI, authorized health, logout, and refusal of old Basic credentials.
Do not report those steps complete from the helper's anonymous checks.

## Failure / recovery

Preflight refusal leaves config/services untouched. A failure after replacement
attempts to stop the web service and never restores Basic automatically. If systemctl
itself fails, independently confirm the service is stopped; do not assume it is.
Keep the complete private evidence bundle; inspect it only in an approved local
admin session. Repair passkey configuration/release or use the existing local
`backend/app/auth_cli.py` recovery procedure. Do not copy backups into web-readable
paths, blindly restore old sessions/DB state, or expose a public password fallback.
A rerun against already-passkey config intentionally refuses; recovery is explicit.
