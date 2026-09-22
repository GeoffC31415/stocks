#!/usr/bin/env bash
# Upgrade an EXISTING Surface installation to a new release (install-surface.sh is first-install only).
# Run as Geoff from an unpacked source tree:  bash deploy/upgrade-surface.sh [--check|--prepare-only|--upgrade]
# Keeps: /etc/stocks/*.env, /var/lib/stocks (database), Caddy data. Snapshots the DB first.
# Rollback: sudo ln -sfn /opt/stocks/releases/<previous> /opt/stocks/current && sudo systemctl restart stocks
set -Eeuo pipefail
umask 077
SELF=$(realpath "${BASH_SOURCE[0]}")
REPO=$(dirname "$(dirname "$SELF")")
ORIGIN='https://solarpi.hopto.org:5000'
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

if [[ ${1:-} == --activate ]]; then
    [[ $EUID == 0 && ${SUDO_USER:-} == geoff && $# == 2 ]] || fail 'Activation requires sudo from Geoff.'
    STAGE=$(realpath -e "$2")
    case "$STAGE" in /home/geoff/.cache/stocks-upgrade.*) ;; *) fail 'Unexpected staging directory.' ;; esac
    [[ $(stat -c %u "$STAGE") == "$SUDO_UID" && $(stat -c %a "$STAGE") == 700 ]] || fail 'Staging is not private.'
    [[ -L /opt/stocks/current ]] || fail 'No existing installation; use install-surface.sh.'
    PREVIOUS=$(readlink -f /opt/stocks/current)
    ID=$(basename "$STAGE"); RELEASE="/opt/stocks/releases/$ID"
    [[ $RELEASE != "$PREVIOUS" ]] || fail "Release is already current: $RELEASE"
    TS=$(date +%Y%m%d-%H%M%S)
    # Consistent online snapshot via SQLite's backup API, taken as the service user.
    runuser -u stocks -- "$PREVIOUS/.venv/bin/python" -c "
import sqlite3,sys
s=sqlite3.connect('file:/var/lib/stocks/portfolio.db?mode=ro',uri=True); d=sqlite3.connect('/var/lib/stocks/.pre-upgrade.db')
s.backup(d); d.close()
assert sqlite3.connect('/var/lib/stocks/.pre-upgrade.db').execute('pragma integrity_check').fetchone()==('ok',)"
    install -o root -g root -m 0600 /var/lib/stocks/.pre-upgrade.db "/var/backups/stocks/pre-upgrade-$TS.db"
    rm -f /var/lib/stocks/.pre-upgrade.db
    printf 'Database snapshot: /var/backups/stocks/pre-upgrade-%s.db\n' "$TS"
    rsync -a --exclude=node_modules "$STAGE/release/" "$RELEASE/"
    chown -R root:root "$RELEASE"; chmod -R u=rwX,go=rX "$RELEASE"
    # Chromium for the scheduled HL download: root-owned, read-only to the service.
    install -d -m 0755 /opt/stocks/playwright
    # Playwright has no ubuntu26.04 build yet; the 24.04 headless shell runs with
    # the libraries already present (verified with ldd before first use).
    PLAYWRIGHT_BROWSERS_PATH=/opt/stocks/playwright PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 \
        "$RELEASE/.venv/bin/python" -m playwright install --only-shell chromium >/dev/null
    chown -R root:root /opt/stocks/playwright; chmod -R u=rwX,go=rX /opt/stocks/playwright
    install -d -o stocks -g stocks -m 0700 /var/lib/stocks/inbox /var/lib/stocks/browser
    [[ -f /etc/stocks/brokers.env ]] || install -o root -g root -m 0600 /dev/null /etc/stocks/brokers.env
    for unit in stocks.service stocks-proxy.service stocks-sync.service stocks-sync.timer; do
        install -m 0644 "$RELEASE/deploy/$unit" "/etc/systemd/system/$unit"
    done
    systemd-analyze verify /etc/systemd/system/stocks.service /etc/systemd/system/stocks-sync.service /etc/systemd/system/stocks-sync.timer
    ln -sfn "$RELEASE" /opt/stocks/current
    systemctl daemon-reload
    systemctl restart stocks.service
    READY=0
    for ((i=0; i<40; i++)); do
        CODE=$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --max-time 2 \
            -H 'Host: solarpi.hopto.org:5000' -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/api/health) || CODE=000
        [[ $CODE == 401 ]] && { READY=1; break; }
        systemctl is-failed --quiet stocks.service && break
        sleep 1
    done
    if [[ $READY != 1 ]]; then
        printf 'New release failed its health check; rolling back to %s\n' "$PREVIOUS" >&2
        ln -sfn "$PREVIOUS" /opt/stocks/current
        install -m 0644 "$PREVIOUS/deploy/stocks.service" /etc/systemd/system/stocks.service
        systemctl daemon-reload; systemctl restart stocks.service
        fail 'Rolled back. Database snapshot kept.'
    fi
    systemctl restart stocks-proxy.service
    for ((i=0; i<30; i++)); do
        CODE=$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --max-time 2 \
            --resolve solarpi.hopto.org:5000:127.0.0.1 "$ORIGIN/api/health") || CODE=000
        [[ $CODE == 401 ]] && break; sleep 1
    done
    [[ $CODE == 401 ]] || fail 'HTTPS proxy did not come back; check journalctl -u stocks-proxy.'
    systemctl enable --now stocks-sync.timer
    printf 'Upgraded: %s -> %s\nRollback: sudo ln -sfn %s /opt/stocks/current && sudo systemctl restart stocks\n' \
        "$(basename "$PREVIOUS")" "$ID" "$PREVIOUS"
    exit 0
fi

MODE=${1:---check}
[[ $EUID != 0 ]] || fail 'Run as Geoff, not root.'
[[ $(hostname) == geoff-Surface-Pro-4 ]] || fail 'This script targets geoff-Surface-Pro-4 only.'
[[ -L /opt/stocks/current && -x /opt/stocks/current/bin/caddy ]] || fail 'No existing installation to upgrade.'
UV_BIN=$(command -v uv || true)
for c in "$HOME/.local/bin/uv" "$HOME/.hermes/bin/uv"; do [[ -z $UV_BIN && -x $c ]] && UV_BIN=$c; done
[[ -n $UV_BIN ]] || fail 'Missing prerequisite: uv.'
for cmd in npm node rsync curl /usr/bin/python3 systemctl systemd-analyze; do
    command -v "$cmd" >/dev/null || fail "Missing prerequisite: $cmd"
done
[[ $MODE == --check ]] && { printf 'Upgrade preflight passed; current release %s.\n' "$(basename "$(readlink -f /opt/stocks/current)")"; exit 0; }
mkdir -p "$HOME/.cache"
STAGE=$(mktemp -d "$HOME/.cache/stocks-upgrade.XXXXXXXX")
printf 'Preparing release in %s\n' "$STAGE"
mkdir "$STAGE/release"
rsync -a --exclude=.git --exclude=.venv --exclude=.env --exclude='.env.*' --exclude='*.env' \
    --exclude='*.db' --exclude='*.db-*' --exclude=node_modules --exclude=dist --exclude=__pycache__ \
    "$REPO/backend" "$REPO/frontend" "$REPO/scripts" "$REPO/deploy" \
    "$REPO/alembic.ini" "$REPO/requirements-production.txt" "$STAGE/release/"
"$UV_BIN" venv -q --no-managed-python --no-python-downloads --python /usr/bin/python3 --relocatable "$STAGE/release/.venv"
"$UV_BIN" pip install -q --python "$STAGE/release/.venv/bin/python" --require-hashes --only-binary=:all: \
    --link-mode copy -r "$STAGE/release/requirements-production.txt"
npm --prefix "$STAGE/release/frontend" ci --ignore-scripts --silent
npm --prefix "$STAGE/release/frontend" run -s typecheck
npm --prefix "$STAGE/release/frontend" run -s build >/dev/null
# Reuse the already verified, pinned Caddy binary and hardened Caddyfile.
install -d "$STAGE/release/bin"
cp /opt/stocks/current/bin/caddy "$STAGE/release/bin/caddy"
cp /opt/stocks/current/deploy/Caddyfile "$STAGE/release/deploy/Caddyfile"
PYTHONPATH="$STAGE/release/backend" PORTFOLIO_DATABASE_URL=sqlite+aiosqlite:///:memory: \
    "$STAGE/release/.venv/bin/python" -c 'from app.main import app; import app.fetchers.hl, playwright; print("Release imports passed.")'
[[ $MODE == --prepare-only ]] && { printf 'Prepared: %s/release\n' "$STAGE"; exit 0; }
[[ $MODE == --upgrade ]] || fail "Unknown option: $MODE"
sudo -S -p '' /bin/bash "$SELF" --activate "$STAGE"
