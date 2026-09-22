#!/usr/bin/env bash
# First installation only. Review before running. Run as Geoff, NOT with sudo.
# --check: read-only. --prepare-only: isolated build, no passwords/services/sudo.
# --install: build, snapshot DB, prompt for website password, then sudo activation.
# Never changes router/firewall/power settings or existing Grafana/Hermes services.
set -Eeuo pipefail
umask 077
SELF=$(realpath "${BASH_SOURCE[0]}")
REPO=$(dirname "$(dirname "$SELF")")
ORIGIN='https://solarpi.hopto.org:5000'
CADDY_VERSION='2.11.4'
# Official release's SHA-512, checked against its published checksum manifest.
CADDY_SHA512='8220d1f013b6f27510247b2360c9e0ca9f018feebd82515f07635318b34ff9777ccc8fd0b6e6f2486ce3a33fe389fbb7db12d05baa474f4587509fb4f5ebf1c9'
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
help_text() {
    printf '%s\n' \
        'Usage: bash deploy/install-surface.sh [--check|--prepare-only|--install] [--database PATH]' \
        'Default: --check. Run as your normal Surface user; sudo is requested only for activation.' \
        'Uses solarpi.hopto.org:5000, HTTP-01 on port 80; never changes router/firewall rules.' \
        'Creates fresh /opt/stocks, /etc/stocks, /var/lib/stocks and a private /var/backups/stocks snapshot.' \
        'Creates stocks.service and stocks-proxy.service. Refuses an existing installation.' \
        'Original database is not migrated. Existing broker credentials are NOT copied.' \
        'Requires installed uv, Node/npm, rsync, curl, tar, sha512sum, system Python and systemd.'
}
assert_fresh() {
    local target unit_paths unit_dir name load_state listeners
    # Include vendor/runtime/generated units and orphaned drop-ins that would be
    # inherited after installation. Never shadow or later stop an existing unit.
    unit_paths=$(systemd-analyze unit-paths) || fail 'Cannot inspect systemd unit paths.'
    [[ -n "$unit_paths" ]] || fail 'Empty systemd unit search path.'
    for name in stocks.service stocks-proxy.service; do
        load_state=$(systemctl show --property=LoadState --value "$name") || fail 'Cannot inspect existing unit state.'
        [[ $load_state == not-found ]] || fail "Existing systemd unit: $name ($load_state)."
    done
    while IFS= read -r unit_dir; do
        [[ $unit_dir == /* ]] || fail 'Unexpected systemd unit search path.'
        for name in stocks.service stocks-proxy.service stocks.service.d stocks-proxy.service.d stocks-.service.d service.d; do
            target="$unit_dir/$name"
            [[ ! -e "$target" && ! -L "$target" ]] || fail "Existing systemd unit or applicable drop-in: $target"
        done
    done <<< "$unit_paths"
    for target in /opt/stocks /etc/stocks /var/lib/stocks /var/lib/stocks-proxy /var/backups/stocks \
        /etc/systemd/system/stocks.service /etc/systemd/system/stocks-proxy.service; do
        [[ ! -e "$target" && ! -L "$target" ]] || fail "Existing deployment target: $target; refusing overwrite."
    done
    if getent passwd stocks >/dev/null || getent group stocks >/dev/null; then
        fail 'The stocks account/group already exists. Review the existing installation first.'
    fi
    if systemctl is-enabled --quiet caddy.service 2>/dev/null; then
        fail 'An enabled Caddy service already exists; do not install a conflicting proxy.'
    fi
    listeners=$(ss -H -ltn '( sport = :80 or sport = :5000 or sport = :8000 )') || fail 'Cannot inspect listening ports.'
    [[ -z $listeners ]] || \
        fail 'Port 80, 5000 or 8000 is occupied; no existing listener will be stopped.'
}

# Internal privileged phase. Only reached after the user-reviewed preparation.
if [[ ${1:-} == --activate ]]; then
    [[ $EUID == 0 ]] || fail 'Activation requires root via sudo from --install.'
    [[ -n ${SUDO_UID:-} && ${SUDO_USER:-} == geoff && $# == 2 ]] || fail 'Activation requires sudo from Geoff.'
    STAGE=$(realpath -e "$2")
    case "$STAGE" in /home/geoff/.cache/stocks-install.*) ;; *) fail 'Unexpected staging directory.' ;; esac
    [[ $(stat -c %u "$STAGE") == "$SUDO_UID" && $(stat -c %a "$STAGE") == 700 ]] || fail 'Staging ownership/permissions are not private.'
    [[ $(hostname) == geoff-Surface-Pro-4 ]] || fail 'This installer is for the Surface Pro 4 only.'
    for cmd in runuser useradd install rsync chown chmod ln systemd-analyze ss stat curl getent systemctl; do
        command -v "$cmd" >/dev/null || fail "Missing activation prerequisite: $cmd"
    done
    assert_fresh
    for file in production.env database.db release/frontend/dist/index.html release/bin/caddy; do
        [[ -f "$STAGE/$file" && ! -L "$STAGE/$file" ]] || fail "Missing staged file: $file"
    done
    ID=$(basename "$STAGE")
    RELEASE="/opt/stocks/releases/$ID"
    OWN_SERVICES=0
    SUCCESS=0
    # shellcheck disable=SC2329 # Called by the EXIT trap below.
    cleanup_activation() {
        local code=$?
        if [[ $SUCCESS == 0 && $OWN_SERVICES == 1 ]]; then
            systemctl disable --now stocks-proxy.service stocks.service >/dev/null 2>&1 || true
            printf '%s\n' 'Activation failed: only the new stocks services were disabled/stopped.' \
                'Deployment files and snapshots remain for diagnosis. Original DB and other services were not changed.' >&2
        fi
        return "$code"
    }
    trap cleanup_activation EXIT
    printf '%s\n' 'Installing fresh root-owned release and private database copy...'
    useradd --system --user-group --home-dir /var/lib/stocks --no-create-home --shell /usr/sbin/nologin stocks
    install -d -m 0755 /opt/stocks /opt/stocks/releases
    rsync -a --exclude=node_modules "$STAGE/release/" "$RELEASE/"
    chown -R root:root "$RELEASE"
    chmod -R u=rwX,go=rX "$RELEASE"
    install -d -o stocks -g stocks -m 0700 /var/lib/stocks
    install -d -o root -g root -m 0700 /etc/stocks /var/backups/stocks
    install -o root -g root -m 0600 "$STAGE/database.db" "/var/backups/stocks/$ID.db"
    install -o stocks -g stocks -m 0600 "$STAGE/database.db" /var/lib/stocks/portfolio.db
    install -o root -g root -m 0600 "$STAGE/production.env" /etc/stocks/production.env
    printf 'STOCKS_ORIGIN=%s\n' "$ORIGIN" > /etc/stocks/caddy.env
    chmod 0600 /etc/stocks/caddy.env
    ln -s "$RELEASE" /opt/stocks/current
    # Runtime interpreter comes from /usr, not Geoff's home. Confirm relocated venv.
    runuser -u stocks -- env PYTHONPATH="$RELEASE/backend" \
        PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:////var/lib/stocks/portfolio.db \
        "$RELEASE/.venv/bin/python" -c 'from app.main import app; import sys; assert sys.base_prefix.startswith("/usr"); print("Relocated runtime imports passed; migrations not started.")'
    install -m 0644 "$RELEASE/deploy/stocks.service" /etc/systemd/system/stocks.service
    install -m 0644 "$RELEASE/deploy/stocks-proxy.service" /etc/systemd/system/stocks-proxy.service
    systemd-analyze verify /etc/systemd/system/stocks.service /etc/systemd/system/stocks-proxy.service
    systemctl daemon-reload
    OWN_SERVICES=1
    systemctl enable --now stocks.service
    # Test the loopback boundary without a password. Forwarded headers are trusted
    # from loopback only; the expected result is an authentication challenge.
    READY=0
    for ((i=0; i<30; i++)); do
        CODE=$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' --max-time 2 \
            -H 'Host: solarpi.hopto.org:5000' -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/api/health) || CODE=000
        if [[ $CODE == 401 ]]; then READY=1; break; fi
        sleep 1
    done
    [[ $READY == 1 ]] || fail 'Backend did not produce the expected authentication challenge.'
    systemctl enable --now stocks-proxy.service
    printf '%s\n' 'Waiting up to three minutes for the public certificate (router TCP 80 must reach this Surface)...'
    READY=0
    for ((i=0; i<60; i++)); do
        CODE=$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' --max-time 2 \
            --resolve solarpi.hopto.org:5000:127.0.0.1 "$ORIGIN/api/health") || CODE=000
        if [[ $CODE == 401 ]]; then READY=1; break; fi
        sleep 1
    done
    [[ $READY == 1 ]] || fail 'Verified HTTPS did not become ready. Check DNS, firewall and port 80 forwarding; no insecure fallback.'
    systemctl is-active --quiet stocks.service
    systemctl is-active --quiet stocks-proxy.service
    SUCCESS=1
    printf '\nHTTPS certificate verified and unauthenticated requests rejected.\nURL: %s\n' "$ORIGIN"
    printf '%s\n' 'Now test login and an update on your phone with Wi-Fi OFF.' \
        'Broker credentials were NOT copied: add them privately with sudoedit /etc/stocks/production.env if needed, then restart stocks.' \
        'No firewall or power settings were changed. Keep the Surface awake and check existing Grafana dashboards.' \
        'Emergency stop: sudo systemctl disable --now stocks-proxy stocks' \
        'Logs: sudo journalctl -u stocks -u stocks-proxy -n 80 --no-pager'
    exit 0
fi

MODE=--check
DATABASE="$REPO/portfolio.db"
while (($#)); do
    case "$1" in
        --help|-h) help_text; exit 0 ;;
        --check|--prepare-only|--install) MODE=$1; shift ;;
        --database) (($# >= 2)) || fail '--database requires a path'; DATABASE=$2; shift 2 ;;
        *) fail "Unknown option: $1" ;;
    esac
done
[[ $EUID != 0 ]] || fail 'Run as Geoff, not root; the script requests sudo only when needed.'
[[ $(hostname) == geoff-Surface-Pro-4 ]] || fail 'This script targets geoff-Surface-Pro-4 only.'
[[ -f "$DATABASE" ]] || fail "Source database is missing: $DATABASE"
DATABASE=$(realpath "$DATABASE")
# Hermes's private tool directory is absent from ordinary terminal PATHs.
# Resolve uv explicitly; do not add private directories to PATH for other tools.
UV_BIN=$(command -v uv || true)
if [[ -z "$UV_BIN" ]]; then
    for candidate in "$HOME/.local/bin/uv" "$HOME/.hermes/bin/uv"; do
        if [[ -x "$candidate" && -f "$candidate" ]]; then UV_BIN=$candidate; break; fi
    done
fi
[[ -n "$UV_BIN" ]] || fail 'Missing prerequisite: uv (checked PATH, ~/.local/bin and ~/.hermes/bin).'
for cmd in npm node rsync curl tar sha512sum /usr/bin/python3 systemctl systemd-analyze ss realpath stat getent; do
    command -v "$cmd" >/dev/null || fail "Missing prerequisite: $cmd"
done
[[ $(uname -m) == x86_64 ]] || fail 'The pinned Caddy binary requires x86_64.'
assert_fresh
/usr/bin/python3 - "$DATABASE" <<'PY'
from pathlib import Path
from contextlib import closing
import sqlite3, sys
with closing(sqlite3.connect(Path(sys.argv[1]).as_uri() + '?mode=ro', uri=True)) as db:
    if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
        raise SystemExit('Source database integrity check failed')
print('Source SQLite quick_check passed (read-only).')
PY
if [[ $MODE == --check ]]; then
    printf '%s\n' 'Preflight passed. No files changed, downloads, password prompts or services started.'
    exit 0
fi
[[ $MODE == --prepare-only || -t 0 ]] || fail '--install needs an interactive terminal for masked password entry.'
mkdir -p "$HOME/.cache"
STAGE=$(mktemp -d "$HOME/.cache/stocks-install.XXXXXXXX")
printf 'Preparing isolated release in %s\n' "$STAGE"
trap 'printf "Preparation stopped. Private staging files retained at %s; inspect before removing.\n" "$STAGE" >&2' ERR
mkdir "$STAGE/release" "$STAGE/download"
rsync -a --exclude=.git --exclude=.venv --exclude=.env --exclude='.env.*' --exclude='*.env' \
    --exclude='*.db' --exclude='*.db-*' --exclude=node_modules --exclude=dist --exclude=__pycache__ \
    --exclude=.pytest_cache --exclude=.mypy_cache \
    "$REPO/backend" "$REPO/frontend" "$REPO/scripts" "$REPO/deploy" \
    "$REPO/alembic.ini" "$REPO/requirements-production.txt" "$STAGE/release/"
"$UV_BIN" venv --no-managed-python --no-python-downloads --python /usr/bin/python3 --relocatable "$STAGE/release/.venv"
"$UV_BIN" pip install --python "$STAGE/release/.venv/bin/python" --require-hashes --only-binary=:all: --link-mode copy \
    -r "$STAGE/release/requirements-production.txt"
npm --prefix "$STAGE/release/frontend" ci --ignore-scripts
npm --prefix "$STAGE/release/frontend" run typecheck
npm --prefix "$STAGE/release/frontend" run build
ARCHIVE="caddy_${CADDY_VERSION}_linux_amd64.tar.gz"
curl --fail --location --proto '=https' --tlsv1.2 --max-time 120 \
    "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/${ARCHIVE}" -o "$STAGE/download/$ARCHIVE"
(cd "$STAGE/download"; printf '%s  %s\n' "$CADDY_SHA512" "$ARCHIVE" | sha512sum --check --status)
mkdir "$STAGE/release/bin"
tar -xzf "$STAGE/download/$ARCHIVE" -C "$STAGE/release/bin" caddy
# Restrict this installation to HTTP-01; do not require public port 443 or expose
# Caddy's management API. Only the staged copy is modified.
/usr/bin/python3 - "$STAGE/release/deploy/Caddyfile" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); text=p.read_text()
assert '{\n    servers' in text and '{$STOCKS_ORIGIN} {' in text
text=text.replace('{\n    servers', '{\n    admin off\n    servers', 1)
text=text.replace('{$STOCKS_ORIGIN} {', '{$STOCKS_ORIGIN} {\n    tls {\n        issuer acme {\n            disable_tlsalpn_challenge\n        }\n    }', 1)
p.write_text(text)
PY
STOCKS_ORIGIN="$ORIGIN" XDG_DATA_HOME="$STAGE/caddy-data" XDG_CONFIG_HOME="$STAGE/caddy-config" \
    "$STAGE/release/bin/caddy" validate --config "$STAGE/release/deploy/Caddyfile" --adapter caddyfile
PYTHONPATH="$STAGE/release/backend" PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: \
    "$STAGE/release/.venv/bin/python" -c 'from app.main import app; import sys; assert sys.base_prefix.startswith("/usr"); print("System-Python runtime imports passed; no migrations run.")'
if [[ $MODE == --prepare-only ]]; then
    printf '\nPreparation passed; no backup/password/sudo/service actions.\nPrepared release: %s/release\n' "$STAGE"
    exit 0
fi
printf '\nSource database: %s\nDestination: /var/lib/stocks/portfolio.db (a COPY; original unchanged)\n' "$DATABASE"
printf 'Type INSTALL to install and expose the authenticated stocks website: '
read -r CONFIRM
[[ $CONFIRM == INSTALL ]] || fail 'Cancelled before database backup or activation.'
"$STAGE/release/.venv/bin/python" "$STAGE/release/scripts/deployment.py" backup --source "$DATABASE" --output "$STAGE/database.db"
printf 'Website username [geoff]: '
read -r LOGIN_NAME
LOGIN_NAME=${LOGIN_NAME:-geoff}
"$STAGE/release/.venv/bin/python" "$STAGE/release/scripts/deployment.py" configure \
    --output "$STAGE/production.env" --origin "$ORIGIN" --username "$LOGIN_NAME" \
    --database /var/lib/stocks/portfolio.db --dist /opt/stocks/current/frontend/dist
# Activate only after all unprivileged work and password entry have succeeded.
sudo /bin/bash "$SELF" --activate "$STAGE"
printf '\nPrivate staging directory retained: %s\n' "$STAGE"
printf '%s\n' 'It contains a private database snapshot and password hash. Keep private or remove after reviewing the installed backup.'
