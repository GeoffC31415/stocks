#!/usr/bin/env python3
"""Fail-closed broker isolation migration. Stdlib only; never source env files.

Production commands require root, an exact expected release, and explicit
confirmation. Filesystem helpers are separately exercised on disposable trees.
See docs/broker-isolation.md before activation or recovery.
"""
from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import pwd
import re
import shutil
import socket
import sqlite3
import stat
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path


class MigrationError(Exception):
    """A fixed diagnostic that contains no config values."""


WEB_KEYS = {
    "DEPLOYMENT_MODE", "PUBLIC_ORIGIN", "AUTH_USERNAME", "AUTH_PASSWORD_HASH",
    "AUTH_MODE", "AUTH_DATABASE_PATH", "FRONTEND_DIST", "MAX_REQUEST_BODY_BYTES", "SYNC_SERVICE_TRIGGER_ENABLED",
    "SYNC_CONTROL_DIR", "SYNC_STALE_DAYS",
}
BROKER_KEYS = {
    "TRADING212_API_KEY", "TRADING212_API_SECRET", "TRADING212_ACCOUNT_NAME",
    "HL_USERNAME", "HL_DATE_OF_BIRTH", "HL_PASSWORD", "HL_SECURE_NUMBER",
    "BARCLAYS_SURNAME", "BARCLAYS_MEMBERSHIP_NUMBER", "BARCLAYS_PIN",
    "BARCLAYS_PASSCODE", "BARCLAYS_MEMORABLE_WORD", "BARCLAYS_AUTOMATION_ENABLED",
    "BARCLAYS_EXPECTED_ACCOUNT", "SYNC_INBOX", "BROWSER_PROFILE",
}
COMMON_KEYS = {"DATABASE_URL", "SYNC_STATUS_DIR"}
PREFIX = "PORTFOLIO_"


def parse_env(text: str) -> dict[str, str]:
    """Conservative systemd-compatible literal subset; no shell expansion.

    Preserve accepted RHS byte-for-byte. Reject ambiguous escaping, multiline,
    duplicate keys and unknown names. Errors report line numbers, never content.
    """
    result = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"PORTFOLIO_([A-Z0-9_]+)=(.*)", line)
        if not match or match[1] not in WEB_KEYS | BROKER_KEYS | COMMON_KEYS:
            raise MigrationError(f"Unrecognized configuration syntax/key at line {number}.")
        key, value = match.groups()
        if key in result:
            raise MigrationError(f"Duplicate configuration key at line {number}.")
        if any(ord(c) < 32 or c in "\\`" for c in value) or "$(" in value or "${" in value:
            raise MigrationError(f"Unsafe configuration syntax at line {number}.")
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0] or value[0] in value[1:-1]:
                raise MigrationError(f"Unsafe quoted configuration at line {number}.")
        elif any(c.isspace() or c in "'\"#;" for c in value):
            raise MigrationError(f"Unsafe unquoted configuration at line {number}.")
        result[key] = value
    return result


def split_env(production: str, brokers: str) -> tuple[str, str]:
    left, right = parse_env(production), parse_env(brokers)
    if left.keys() & right.keys():
        raise MigrationError("Duplicate configuration across environment files; reconcile privately.")
    values = left | right
    web = {k: v for k, v in values.items() if k in WEB_KEYS}
    worker = {k: v for k, v in values.items() if k in BROKER_KEYS}
    common = {
        "DATABASE_URL": "sqlite+aiosqlite:////var/lib/stocks-data/portfolio.db",
        "SYNC_STATUS_DIR": "/var/lib/stocks-status",
    }
    web.update(common)
    web.update(DEPLOYMENT_MODE="public", AUTH_MODE="basic", AUTH_DATABASE_PATH="/var/lib/stocks/auth.sqlite3",
               SYNC_SERVICE_TRIGGER_ENABLED="false", SYNC_CONTROL_DIR="/var/lib/stocks/control")
    worker.update(common)
    worker.update(DEPLOYMENT_MODE="local", SYNC_INBOX="/var/lib/stocks-sync/inbox",
                  BROWSER_PROFILE="/var/lib/stocks-sync/browser")
    def render(config):
        return "".join(f"{PREFIX}{key}={config[key]}\n" for key in sorted(config))
    return render(web), render(worker)


def safe_path(path: Path, *, tree: bool = False) -> None:
    """Reject symlinks in every ancestor and special/multiply-linked files."""
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise MigrationError("Symlink path refused.")
    if not path.exists():
        return
    paths = [path, *path.rglob("*")] if tree and path.is_dir() else [path]
    for item in paths:
        info = item.lstat()
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise MigrationError("Symlink or special file in state refused; review offline.")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise MigrationError("Multiply-linked file refused.")


def exclusive_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    safe_path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())


def backup_sqlite(source: Path, target: Path) -> None:
    safe_path(source)
    if not source.is_file():
        raise MigrationError("Required SQLite database missing.")
    exclusive_write(target, b"")
    with (
        closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src,
        closing(sqlite3.connect(target)) as dst,
    ):
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise MigrationError("SQLite backup integrity check failed.")


def state_preflight(root: Path, bundle: Path | None = None) -> None:
    old = root / "var/lib/stocks"
    safe_path(old, tree=True)
    if not old.is_dir() or not (old / "portfolio.db").is_file():
        raise MigrationError("Expected original state/database missing.")
    for name in ("stocks-data", "stocks-sync", "stocks-status"):
        path = root / "var/lib" / name
        safe_path(path)
        if path.exists():
            raise MigrationError("Isolation target already exists; do not rerun, use recovery guide.")
    if bundle is not None:
        safe_path(bundle, tree=True)
        if not bundle.is_dir() or stat.S_IMODE(bundle.stat().st_mode) != 0o700:
            raise MigrationError("Backup bundle must be an existing private directory.")
        if (bundle / "state-started").exists() or (bundle / "original-state").exists():
            raise MigrationError("Incomplete/prior migration found; use recovery guide.")
        if old.stat().st_dev != bundle.stat().st_dev:
            raise MigrationError("State and backup must share a filesystem for atomic quarantine.")


def migrate_state(root: Path, bundle: Path) -> None:
    """Services must already be stopped. Never destroy the original state tree."""
    state_preflight(root, bundle)
    old = root / "var/lib/stocks"
    backup_sqlite(old / "portfolio.db", bundle / "portfolio.db")
    exclusive_write(bundle / "state-started", b"1\n")
    # Quarantine ALL prior files (including unknown old backups/sessions), not
    # merely browser/inbox. Root-only bundle ancestors remove web access.
    old.rename(bundle / "original-state")
    old.mkdir(mode=0o700)
    worker = root / "var/lib/stocks-sync"
    worker.mkdir(mode=0o700)
    data = root / "var/lib/stocks-data"
    data.mkdir(mode=0o770)
    (root / "var/lib/stocks-status").mkdir(mode=0o750)
    exclusive_write(data / "portfolio.db", (bundle / "portfolio.db").read_bytes(), 0o660)
    for name in ("inbox", "browser"):
        source = bundle / "original-state" / name
        if source.exists():
            shutil.copytree(source, worker / name)
        else:
            (worker / name).mkdir(mode=0o700)
    (worker / "downloads").mkdir(mode=0o700)
    # Only this explicitly named web-private auth store returns to the web UID.
    auth = bundle / "original-state/auth.sqlite3"
    if auth.exists():
        backup_sqlite(auth, old / "auth.sqlite3")
    exclusive_write(bundle / "state-complete", b"1\n")


def rollback_state(root: Path, bundle: Path) -> None:
    safe_path(bundle, tree=True)
    original = bundle / "original-state"
    if not original.is_dir() or (bundle / "state-rolled-back").exists():
        raise MigrationError("No quarantined original state; manual recovery required.")
    evidence = bundle / "evidence"
    if evidence.exists():
        raise MigrationError("Partial rollback evidence exists; review manually, never overwrite.")
    for name in ("stocks", "stocks-data", "stocks-sync", "stocks-status"):
        safe_path(root / "var/lib" / name, tree=True)
    evidence.mkdir(mode=0o700)
    for name in ("stocks", "stocks-data", "stocks-sync", "stocks-status"):
        current = root / "var/lib" / name
        if current.exists():
            current.rename(evidence / name)
    original.rename(root / "var/lib/stocks")
    exclusive_write(bundle / "state-rolled-back", b"1\n")


UNITS = ("stocks.service", "stocks-sync.service", "stocks-sync.timer")
CONFIG_FILES = ("etc/stocks/production.env", "etc/stocks/brokers.env") + tuple(
    "etc/systemd/system/" + name for name in UNITS
)


def plain(value: str) -> str:
    return value[1:-1] if value.startswith(('"', "'")) else value


def layout_preflight(root: Path, release: Path, previous: Path) -> tuple[str, str]:
    state_preflight(root)
    for path in (release, previous, root / "etc/stocks", root / "etc/systemd/system"):
        safe_path(path)
    current = root / "opt/stocks/current"
    if not current.is_symlink() or current.resolve(strict=True) != previous or release == previous:
        raise MigrationError("Current release differs from explicit expected release.")
    marker = root / "etc/stocks/isolation.json"
    safe_path(marker)
    if marker.exists():
        raise MigrationError("Migration marker exists; use recovery guide, never rerun.")
    for relative in CONFIG_FILES:
        path = root / relative
        safe_path(path)
        if not path.is_file():
            raise MigrationError("Required installed environment/unit missing.")
    for name in UNITS:
        path = release / "deploy" / name
        safe_path(path)
        if not path.is_file():
            raise MigrationError("Required new unit template missing.")
    production = (root / CONFIG_FILES[0]).read_text()
    brokers = (root / CONFIG_FILES[1]).read_text()
    values = parse_env(production) | parse_env(brokers)
    expected = {
        "DATABASE_URL": "sqlite+aiosqlite:////var/lib/stocks/portfolio.db",
        "PUBLIC_ORIGIN": "https://solarpi.hopto.org:5000",
    }
    for key, value in expected.items():
        if plain(values.get(key, "")) != value:
            raise MigrationError("Original database/origin does not match approved layout.")
    for key, value in {"SYNC_INBOX": "/var/lib/stocks/inbox", "BROWSER_PROFILE": "/var/lib/stocks/browser", "AUTH_MODE": "basic"}.items():
        if key in values and plain(values[key]) != value:
            raise MigrationError("Unexpected old state path/auth mode; review before migration.")
    if not all(plain(values.get(k, "")) for k in ("AUTH_USERNAME", "AUTH_PASSWORD_HASH")):
        raise MigrationError("Existing Basic authentication configuration required.")
    return split_env(production, brokers)


def replace_bytes(path: Path, content: bytes, mode: int = 0o600) -> None:
    safe_path(path)
    fd, temporary = tempfile.mkstemp(prefix=".isolation-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            os.fchmod(out.fileno(), mode)
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        if path.read_bytes() != content:
            raise MigrationError("Written file verification failed.")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def switch_release(root: Path, target: Path) -> None:
    current = root / "opt/stocks/current"
    if not current.is_symlink():
        raise MigrationError("Current release pointer must remain a symlink.")
    temporary = current.with_name(".isolation-current")
    if temporary.exists() or temporary.is_symlink():
        raise MigrationError("Ambiguous temporary release pointer; inspect manually.")
    temporary.symlink_to(target)
    os.replace(temporary, current)
    if current.resolve(strict=True) != target:
        raise MigrationError("Release pointer verification failed.")


def activate_layout(root: Path, bundle: Path, release: Path, previous: Path, system) -> None:
    web, worker = layout_preflight(root, release, previous)
    state_preflight(root, bundle)
    originals = bundle / "config"
    originals.mkdir(mode=0o700)
    hashes = {}
    for relative in CONFIG_FILES:
        saved = originals / Path(relative).name
        content = (root / relative).read_bytes()
        exclusive_write(saved, content)
        hashes[relative] = hashlib.sha256(content).hexdigest()
    manifest = {"version": 1, "previous": str(previous), "release": str(release),
                "services": system.snapshot(), "config_sha256": hashes}
    exclusive_write(bundle / "manifest.json", json.dumps(manifest).encode())
    exclusive_write(root / "etc/stocks/isolation.json", json.dumps({"bundle": str(bundle)}).encode())
    try:
        system.stop()
        migrate_state(root, bundle)
        system.permissions(root, bundle)
        replace_bytes(root / CONFIG_FILES[0], web.encode())
        replace_bytes(root / CONFIG_FILES[1], worker.encode())
        for name in UNITS:
            replace_bytes(root / "etc/systemd/system" / name, (release / "deploy" / name).read_bytes(), 0o644)
        system.verify(root)
        switch_release(root, release)
        system.reload()
        system.start_web()
        system.health()
        exclusive_write(bundle / "activation-complete", b"1\n")
    except BaseException:
        # Never auto-roll back across changed schema/state. Preserve all evidence.
        system.stop()
        raise


def rollback_layout(root: Path, bundle: Path, system) -> None:
    safe_path(bundle, tree=True)
    if (bundle / "rollback-started").exists():
        raise MigrationError("Rollback already attempted; inspect preserved evidence manually.")
    manifest = json.loads((bundle / "manifest.json").read_text())
    previous = Path(manifest["previous"])
    safe_path(previous)
    if not previous.is_dir():
        raise MigrationError("Saved prior release missing; do not change release pointer alone.")
    # Validate ALL originals before stopping or changing any target.
    for relative in CONFIG_FILES:
        content = (bundle / "config" / Path(relative).name).read_bytes()
        if hashlib.sha256(content).hexdigest() != manifest["config_sha256"][relative]:
            raise MigrationError("Saved original configuration integrity failed.")
        safe_path(root / relative)
    system.stop()
    exclusive_write(bundle / "rollback-started", b"1\n")
    evidence = bundle / "rollback-config"
    evidence.mkdir(mode=0o700)
    for relative in CONFIG_FILES:
        path = root / relative
        exclusive_write(evidence / path.name, path.read_bytes())
    if (bundle / "original-state").exists():
        rollback_state(root, bundle)
    elif (bundle / "state-started").exists():
        raise MigrationError("Partial state transition; inspect original location manually.")
    for relative in CONFIG_FILES:
        replace_bytes(root / relative, (bundle / "config" / Path(relative).name).read_bytes(),
                      0o644 if relative.endswith((".service", ".timer")) else 0o600)
    switch_release(root, previous)
    system.reload()
    if manifest["services"]["web_active"]:
        system.start_web()
        system.health()
    exclusive_write(bundle / "rollback-complete", b"1\n")
    # Leave the marker and all evidence; subsequent deployment requires review.
    # Timers are NEVER automatically restarted (Persistent=true may log in now).


def apply_permissions(root: Path, *, web_uid: int, web_gid: int, worker_uid: int,
                      worker_gid: int, data_gid: int) -> None:
    for name, uid, gid in (("stocks", web_uid, web_gid), ("stocks-sync", worker_uid, worker_gid)):
        directory = root / "var/lib" / name
        safe_path(directory, tree=True)
        for item in (directory, *directory.rglob("*")):
            os.chown(item, uid, gid)
            item.chmod(0o700 if item.is_dir() else 0o600)
    data = root / "var/lib/stocks-data"
    os.chown(data, 0, data_gid)
    data.chmod(0o2770)
    os.chown(data / "portfolio.db", web_uid, data_gid)
    (data / "portfolio.db").chmod(0o660)
    status = root / "var/lib/stocks-status"
    os.chown(status, worker_uid, web_gid)
    status.chmod(0o2750)


def validate_host_identity(uid: int, hostname: str, release: Path, previous: Path) -> None:
    if uid != 0:
        raise MigrationError("Production preflight requires root via an approved interactive terminal.")
    if hostname != "geoff-Surface-Pro-4":
        raise MigrationError("Wrong host; this migration targets the Surface only.")
    for path in (release, previous):
        if path.parent != Path("/opt/stocks/releases") or not re.fullmatch(r"[A-Za-z0-9._-]+", path.name):
            raise MigrationError("Release must be a direct child of the approved releases directory.")


def host_preflight(release: Path, previous: Path) -> None:
    validate_host_identity(os.geteuid(), socket.gethostname(), release, previous)


def assert_quiescent(proc_root: Path, service_uids: set[int], state: Path) -> None:
    """Fail closed on surviving service processes or open state descriptors."""
    for process in proc_root.iterdir():
        if not process.name.isdigit():
            continue
        try:
            status = (process / "status").read_text()
            uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
            if service_uids.intersection(int(x) for x in uid_line.split()[1:]):
                raise MigrationError("Service identity process remains; stop all workers first.")
            for fd in (process / "fd").iterdir():
                try:
                    target = os.readlink(fd)
                except FileNotFoundError:
                    continue
                if target == str(state) or target.startswith(str(state) + "/"):
                    raise MigrationError("State remains open in another process; stop it first.")
        except FileNotFoundError:
            continue  # A process exiting during inspection is safe.


class System:
    def permissions(self, root, bundle):
        web = pwd.getpwnam("stocks")
        try:
            worker = pwd.getpwnam("stocks-sync")
        except KeyError:
            self.command("/usr/sbin/useradd", "--system", "--user-group", "--home-dir", "/var/lib/stocks-sync",
                         "--no-create-home", "--shell", "/usr/sbin/nologin", "stocks-sync")
            worker = pwd.getpwnam("stocks-sync")
        if web.pw_uid == 0 or worker.pw_uid == 0 or web.pw_uid == worker.pw_uid or web.pw_gid == worker.pw_gid:
            raise MigrationError("Service identities must be distinct and unprivileged.")
        if worker.pw_dir != "/var/lib/stocks-sync" or worker.pw_shell not in {"/usr/sbin/nologin", "/sbin/nologin"}:
            raise MigrationError("Existing worker identity has unexpected home/shell.")
        try:
            data = grp.getgrnam("stocks-data")
        except KeyError:
            self.command("/usr/sbin/groupadd", "--system", "stocks-data")
            data = grp.getgrnam("stocks-data")
        if data.gr_gid in {0, web.pw_gid, worker.pw_gid}:
            raise MigrationError("Shared data group must be separate from private groups.")
        apply_permissions(root, web_uid=web.pw_uid, web_gid=web.pw_gid,
                          worker_uid=worker.pw_uid, worker_gid=worker.pw_gid, data_gid=data.gr_gid)
        os.chown(bundle, 0, 0)
        bundle.chmod(0o700)

    def verify(self, root):
        # Probe DAC with exactly the groups configured in the units, not the
        # operator's supplemental groups. Namespace verification remains an
        # explicit post-activation gate documented in the deployment guide.
        data_gid = grp.getgrnam("stocks-data").gr_gid
        for name, private, forbidden in (("stocks", "stocks", "stocks-sync"),
                                          ("stocks-sync", "stocks-sync", "stocks")):
            user = pwd.getpwnam(name)
            script = (
                "import os,sys; from pathlib import Path; "
                "r=Path(sys.argv[1]); p=sys.argv[2]; f=sys.argv[3]; "
                "assert os.access(r/'var/lib'/p, os.R_OK|os.W_OK|os.X_OK); "
                "assert not os.access(r/'var/lib'/f, os.R_OK|os.X_OK); "
                "assert os.access(r/'var/lib/stocks-data', os.R_OK|os.W_OK|os.X_OK); "
                "assert os.access(r/'var/lib/stocks-data/portfolio.db', os.R_OK|os.W_OK); "
                "assert os.access(r/'var/lib/stocks-status', os.R_OK|os.X_OK); "
                "assert os.access(r/'var/lib/stocks-status', os.W_OK)==(p=='stocks-sync'); "
                "assert not os.access(r/'etc/stocks/production.env', os.R_OK); "
                "assert not os.access(r/'etc/stocks/brokers.env', os.R_OK)"
            )
            self.command("/usr/bin/setpriv", f"--reuid={user.pw_uid}", f"--regid={user.pw_gid}",
                         f"--groups={data_gid}", "/usr/bin/python3", "-c", script, str(root), private, forbidden)
        self.command("/usr/bin/systemd-analyze", "verify", *(str(root / "etc/systemd/system" / name) for name in UNITS))

    def snapshot(self):
        result = {}
        for label, name in (("web", "stocks.service"), ("worker", "stocks-sync.service"), ("timer", "stocks-sync.timer")):
            state = self.command("/usr/bin/systemctl", "is-active", name, allowed=(0, 3))
            if state not in {"active", "inactive", "failed"}:
                raise MigrationError("Service is transitioning or unknown; retry only after review.")
            result[label + "_active"] = state == "active"
        enabled = self.command("/usr/bin/systemctl", "is-enabled", "stocks-sync.timer", allowed=(0, 1))
        if enabled not in {"enabled", "disabled"}:
            raise MigrationError("Unsupported timer enablement; review before migration.")
        result["timer_enabled"] = enabled
        return result

    def reload(self):
        self.command("/usr/bin/systemctl", "daemon-reload")

    def start_web(self):
        self.command("/usr/bin/systemctl", "start", "stocks.service")

    def health(self):
        # This verifies ONLY the unauthenticated boundary, not authenticated app
        # health, database queries, passkeys, dashboards or broker operation.
        for _ in range(30):
            code = self.command("/usr/bin/curl", "--noproxy", "*", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "2",
                                "-H", "Host: solarpi.hopto.org:5000", "-H", "X-Forwarded-Proto: https", "http://127.0.0.1:8000/api/health", allowed=(0, 7, 28))
            if code == "401":
                break
            time.sleep(1)
        else:
            raise MigrationError("Backend unauthenticated boundary did not return 401.")
        for _ in range(2):
            if self.command("/usr/bin/systemctl", "is-active", "stocks.service", allowed=(0, 3)) != "active":
                raise MigrationError("Web service is not active.")
            if self.command("/usr/bin/systemctl", "show", "stocks.service", "--property=NRestarts", "--value") != "0":
                raise MigrationError("Web service restarted unexpectedly.")
            time.sleep(2)
        code = self.command("/usr/bin/curl", "--noproxy", "*", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5",
                            "--resolve", "solarpi.hopto.org:5000:127.0.0.1", "https://solarpi.hopto.org:5000/api/health")
        if code != "401":
            raise MigrationError("HTTPS unauthenticated boundary did not return 401.")

    def quiescence(self):
        uids = {pwd.getpwnam("stocks").pw_uid}
        try:
            uids.add(pwd.getpwnam("stocks-sync").pw_uid)
        except KeyError:
            pass
        for name in ("stocks", "stocks-sync", "stocks-data"):
            assert_quiescent(Path("/proc"), uids, Path("/var/lib") / name)

    def stop(self):
        self.command("/usr/bin/systemctl", "disable", "--now", "stocks-sync.timer")
        self.command("/usr/bin/systemctl", "stop", "stocks.service", "stocks-sync.service")
        self.quiescence()

    def command(self, *args, timeout=120, allowed=(0,)):
        import subprocess
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False,
                                    env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
        except (OSError, subprocess.SubprocessError):
            raise MigrationError("System command failed; services/evidence require operator review.") from None
        if result.returncode not in allowed:
            raise MigrationError("System command refused/failed; inspect privately, no output copied.")
        return result.stdout.strip()

    def resume_timer(self, bundle):
        if not any((bundle / name).exists() for name in ("activation-complete", "rollback-complete")):
            raise MigrationError("Cannot resume schedule after incomplete transition.")
        saved = json.loads((bundle / "manifest.json").read_text())["services"]
        if saved["timer_enabled"] == "enabled":
            self.command("/usr/bin/systemctl", "enable", "stocks-sync.timer")
        if saved["timer_active"]:
            self.command("/usr/bin/systemctl", "start", "stocks-sync.timer")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("preflight", "activate"):
        command = sub.add_parser(action)
        command.add_argument("--release", type=Path, required=True)
        command.add_argument("--expect-current", type=Path, required=True)
        if action == "activate":
            command.add_argument("--confirm", choices=["ISOLATE"], required=True)
    for action, confirmation in (("rollback", "RESTORE-PRE-MIGRATION"), ("resume-timer", "RESUME-SCHEDULE")):
        command = sub.add_parser(action)
        command.add_argument("--bundle", type=Path, required=True)
        command.add_argument("--confirm", choices=[confirmation], required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    system = System()
    try:
        if args.action in {"preflight", "activate"}:
            host_preflight(args.release, args.expect_current)
            layout_preflight(Path("/"), args.release, args.expect_current)
            if args.action == "preflight":
                print("Preflight passed; no services or state changed. Config values were not printed.")
                return 0
            bundle = Path(tempfile.mkdtemp(prefix="isolation-", dir="/var/backups/stocks"))
            print(f"Private recovery bundle: {bundle}", flush=True)
            activate_layout(Path("/"), bundle, args.release, args.expect_current, system)
            print("Isolation activated; unauthenticated HTTP/HTTPS boundary returned 401. Authenticated app health is NOT verified. Schedule remains disabled pending explicit resume.")
        else:
            if os.geteuid() != 0 or socket.gethostname() != "geoff-Surface-Pro-4":
                raise MigrationError("Recovery requires root on the approved host.")
            bundle = args.bundle
            if bundle.parent != Path("/var/backups/stocks") or not re.fullmatch(r"isolation-[A-Za-z0-9_-]+", bundle.name):
                raise MigrationError("Unexpected recovery bundle path.")
            safe_path(bundle, tree=True)
            if bundle.stat().st_uid != 0 or stat.S_IMODE(bundle.stat().st_mode) != 0o700:
                raise MigrationError("Recovery bundle must be root-only.")
            marker = Path("/etc/stocks/isolation.json")
            safe_path(marker)
            if json.loads(marker.read_text()).get("bundle") != str(bundle):
                raise MigrationError("Recovery bundle does not match installed marker.")
            if args.action == "rollback":
                rollback_layout(Path("/"), bundle, system)
                print("Prior units/env/data/release restored. New state preserved privately. Schedule remains disabled; review before resuming.")
            else:
                system.resume_timer(bundle)
                print("Saved timer enabled/active state restored; a persistent catch-up broker run may start.")
        return 0
    except MigrationError as exc:
        print(f"STOP: {exc} See docs/broker-isolation.md; do not rerun blindly.", file=sys.stderr)
    except (OSError, ValueError, KeyError, sqlite3.Error):
        # No exception repr/traceback: errors may include credentials or filenames.
        print("STOP: Migration/recovery failed. Preserve all evidence and inspect privately using docs/broker-isolation.md.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
