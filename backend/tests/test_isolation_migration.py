"""Migration operates only on synthetic temporary trees in these tests."""
import importlib.util
import json
import os
import sqlite3
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def helper():
    path = ROOT / "deploy/broker_isolation.py"
    assert path.exists(), "migration helper must exist"
    spec = importlib.util.spec_from_file_location("isolation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_strict_env_split_never_discloses_synthetic_secrets(capsys):
    m = helper()
    web, worker = m.split_env(
        'PORTFOLIO_AUTH_USERNAME=owner\nPORTFOLIO_AUTH_PASSWORD_HASH="SENTINEL_AUTH"\nPORTFOLIO_TRADING212_API_KEY=SENTINEL_BROKER\nPORTFOLIO_DEPLOYMENT_MODE=public\n',
        'PORTFOLIO_HL_PASSWORD="SENTINEL_BANK"\n',
    )
    assert "SENTINEL_AUTH" in web and "SENTINEL_AUTH" not in worker
    assert "SENTINEL_BROKER" in worker and "SENTINEL_BROKER" not in web
    assert "SENTINEL_BANK" not in web
    assert "PORTFOLIO_AUTH_MODE=basic" in web
    assert "PORTFOLIO_AUTH_DATABASE_PATH=/var/lib/stocks/auth.sqlite3" in web
    assert "AUTH_DATABASE_PATH" not in worker
    assert "PORTFOLIO_SYNC_SERVICE_TRIGGER_ENABLED=false" in web
    assert "AUTH_" not in worker and "DEPLOYMENT_MODE=local" in worker
    for text in (web, worker):
        assert "sqlite+aiosqlite:////var/lib/stocks-data/portfolio.db" in text
        assert "PORTFOLIO_SYNC_STATUS_DIR=/var/lib/stocks-status" in text
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("text", [
    "export PORTFOLIO_HL_PASSWORD=SENTINEL", "PORTFOLIO_HL_PASSWORD=$(SENTINEL)",
    "PORTFOLIO_HL_PASSWORD='SENTINEL", "PORTFOLIO_HL_PASSWORD=SENTINEL # comment",
    "UNKNOWN=SENTINEL", "PORTFOLIO_HL_PASSWORD=SENTINEL\nPORTFOLIO_HL_PASSWORD=other",
    'PORTFOLIO_HL_PASSWORD="SENTINEL\\n"',
])
def test_unsafe_env_fails_without_value_in_error(text, capsys):
    m = helper()
    with pytest.raises(m.MigrationError) as exc:
        m.split_env(text, "")
    assert "SENTINEL" not in str(exc.value)
    assert capsys.readouterr() == ("", "")


def test_conflicting_files_fail_closed():
    m = helper()
    with pytest.raises(m.MigrationError):
        m.split_env("PORTFOLIO_HL_PASSWORD=one", "PORTFOLIO_HL_PASSWORD=two")


def fixture_tree(tmp_path):
    root = tmp_path / "root"
    old = root / "var/lib/stocks"
    old.mkdir(parents=True, mode=0o700)
    for name in ("browser", "inbox"):
        (old / name).mkdir()
        (old / name / "secret").write_text("SENTINEL_SESSION")
    (old / ".old-credential-backup").write_text("SENTINEL_ARCHIVE")
    with sqlite3.connect(old / "portfolio.db") as db:
        db.execute("create table sentinel (value text)")
        db.execute("insert into sentinel values ('before')")
    bundle = root / "var/backups/stocks/isolation-fixture"
    bundle.mkdir(parents=True, mode=0o700)
    return root, old, bundle


def test_migrate_and_rollback_keep_originals_and_new_evidence(tmp_path):
    m = helper()
    root, old, bundle = fixture_tree(tmp_path)
    m.migrate_state(root, bundle)
    assert not (old / "browser").exists()
    assert not (old / ".old-credential-backup").exists()
    assert (bundle / "original-state/.old-credential-backup").read_text() == "SENTINEL_ARCHIVE"
    assert stat.S_IMODE((bundle / "portfolio.db").stat().st_mode) == 0o600
    shared = root / "var/lib/stocks-data/portfolio.db"
    with sqlite3.connect(shared) as db:
        assert db.execute("pragma integrity_check").fetchone() == ("ok",)
        db.execute("insert into sentinel values ('after')")
    assert (root / "var/lib/stocks-sync/browser/secret").read_text() == "SENTINEL_SESSION"
    m.rollback_state(root, bundle)
    with sqlite3.connect(old / "portfolio.db") as db:
        assert db.execute("select value from sentinel").fetchall() == [("before",)]
    with sqlite3.connect(bundle / "evidence/stocks-data/portfolio.db") as db:
        assert db.execute("select value from sentinel").fetchall() == [("before",), ("after",)]
    assert (old / "browser/secret").exists()
    with pytest.raises(m.MigrationError):
        m.rollback_state(root, bundle)


@pytest.mark.parametrize("hazard", ["target", "symlink", "hardlink", "missing-db"])
def test_state_preflight_refuses_ambiguity_without_mutation(tmp_path, hazard):
    m = helper()
    root, old, bundle = fixture_tree(tmp_path)
    if hazard == "target":
        (root / "var/lib/stocks-sync").mkdir()
    elif hazard == "symlink":
        (old / "browser/link").symlink_to(old / "inbox")
    elif hazard == "hardlink":
        os.link(old / "browser/secret", old / "browser/alias")
    else:
        (old / "portfolio.db").unlink()
    with pytest.raises(m.MigrationError):
        m.migrate_state(root, bundle)
    assert (old / "browser/secret").read_text() == "SENTINEL_SESSION"
    assert not (bundle / "original-state").exists()


def test_partial_state_failure_is_recoverable_and_rerun_refused(tmp_path, monkeypatch):
    m = helper()
    root, old, bundle = fixture_tree(tmp_path)
    monkeypatch.setattr(m.shutil, "copytree", lambda *a, **kw: (_ for _ in ()).throw(OSError("injected")))
    with pytest.raises(OSError):
        m.migrate_state(root, bundle)
    with pytest.raises(m.MigrationError):
        m.migrate_state(root, bundle)
    m.rollback_state(root, bundle)
    assert (old / "browser/secret").read_text() == "SENTINEL_SESSION"


def test_sqlite_backup_captures_wal_exclusively(tmp_path):
    m = helper()
    source, target = tmp_path / "source.db", tmp_path / "snapshot.db"
    with sqlite3.connect(source) as writer:
        writer.execute("pragma journal_mode=wal")
        writer.execute("create table sentinel(value)")
        writer.execute("insert into sentinel values (42)")
        writer.commit()
        m.backup_sqlite(source, target)
        with sqlite3.connect(target) as reader:
            assert reader.execute("select value from sentinel").fetchone() == (42,)
        with pytest.raises((m.MigrationError, FileExistsError)):
            m.backup_sqlite(source, target)


def deployment_fixture(tmp_path):
    root, old, bundle = fixture_tree(tmp_path)
    env = root / "etc/stocks"
    env.mkdir(parents=True)
    (env / "production.env").write_text('PORTFOLIO_AUTH_USERNAME=owner\nPORTFOLIO_AUTH_PASSWORD_HASH=SENTINEL_AUTH\nPORTFOLIO_PUBLIC_ORIGIN=https://solarpi.hopto.org:5000\nPORTFOLIO_DATABASE_URL=sqlite+aiosqlite:////var/lib/stocks/portfolio.db\n')
    (env / "brokers.env").write_text('PORTFOLIO_HL_PASSWORD=SENTINEL_BANK\n')
    units = root / "etc/systemd/system"
    units.mkdir(parents=True)
    for name in ("stocks.service", "stocks-sync.service", "stocks-sync.timer"):
        (units / name).write_text("original unit " + name)
    previous = root / "opt/stocks/releases/previous"
    previous.mkdir(parents=True)
    release = root / "opt/stocks/releases/new"
    (release / "deploy").mkdir(parents=True)
    for name in ("stocks.service", "stocks-sync.service", "stocks-sync.timer"):
        (release / "deploy" / name).write_text((ROOT / "deploy" / name).read_text())
    (root / "opt/stocks/current").symlink_to(previous)
    return root, bundle, release, previous


class FakeSystem:
    def __init__(self):
        self.events = []
    def snapshot(self):
        return {"timer_active": True, "web_active": True, "worker_active": False}
    def stop(self):
        self.events.append("stop-timer-worker-web")
    def permissions(self, root, bundle):
        assert (bundle / "original-state").exists()
        self.events.append("permissions")
    def verify(self, root):
        self.events.append("permission-probes")
    def reload(self):
        self.events.append("reload")
    def start_web(self):
        self.events.append("start-web")
    def health(self):
        self.events.append("unauthenticated-401-boundary-only")


def test_layout_activation_and_rollback_restore_coherent_files(tmp_path):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    system = FakeSystem()
    m.activate_layout(root, bundle, release, previous, system)
    assert system.events == ["stop-timer-worker-web", "permissions", "permission-probes", "reload", "start-web", "unauthenticated-401-boundary-only"]
    assert (root / "opt/stocks/current").resolve() == release
    web = (root / "etc/stocks/production.env").read_text()
    worker = (root / "etc/stocks/brokers.env").read_text()
    assert "SENTINEL_BANK" not in web and "SENTINEL_AUTH" not in worker
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["services"]["timer_active"] is True
    assert "SENTINEL" not in json.dumps(manifest)
    m.rollback_layout(root, bundle, system)
    assert (root / "opt/stocks/current").resolve() == previous
    assert (root / "etc/systemd/system/stocks.service").read_text() == "original unit stocks.service"
    assert "SENTINEL_BANK" in (root / "etc/stocks/brokers.env").read_text()
    assert (bundle / "rollback-config/production.env").exists()
    assert system.events.count("stop-timer-worker-web") == 2
    assert not any("start-timer" in x or "start-worker" in x for x in system.events)


def test_activation_failure_keeps_services_stopped_and_recoverable(tmp_path):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    system = FakeSystem()
    def fail(_):
        raise m.MigrationError("injected permission failure")
    system.verify = fail
    with pytest.raises(m.MigrationError):
        m.activate_layout(root, bundle, release, previous, system)
    assert system.events[-1] == "stop-timer-worker-web"
    assert "start-web" not in system.events
    m.rollback_layout(root, bundle, FakeSystem())
    assert (root / "opt/stocks/current").resolve() == previous
    assert (root / "var/lib/stocks/browser/secret").exists()


@pytest.mark.parametrize("hazard", ["pending", "wrong-db", "wrong-origin", "wrong-current", "passkey-mode"])
def test_layout_preflight_no_stop_or_mutation_on_conflicts(tmp_path, hazard):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    env = root / "etc/stocks"
    if hazard == "pending":
        (env / "isolation.json").write_text("{}")
    elif hazard == "wrong-current":
        previous = release
    else:
        key, val = {"wrong-db": ("DATABASE_URL", "sqlite:////elsewhere"), "wrong-origin": ("PUBLIC_ORIGIN", "https://other.test"), "passkey-mode": ("AUTH_MODE", "passkey")}[hazard]
        text = (env / "production.env").read_text()
        text = "\n".join(line for line in text.splitlines() if not line.startswith("PORTFOLIO_" + key + "="))
        (env / "production.env").write_text(text + "\nPORTFOLIO_" + key + "=" + val + "\n")
    system = FakeSystem()
    with pytest.raises(m.MigrationError):
        m.activate_layout(root, bundle, release, previous, system)
    assert system.events == []
    assert not (bundle / "original-state").exists()


def test_host_preflight_requires_root_before_reading_any_config(monkeypatch):
    m = helper()
    monkeypatch.setattr(m.os, "geteuid", lambda: 1000)
    with pytest.raises(m.MigrationError, match="root"):
        m.host_preflight(Path("/not/a/release"), Path("/not/previous"))


def test_system_stops_timer_first_and_never_starts_worker(monkeypatch):
    m = helper()
    calls = []
    system = m.System()
    monkeypatch.setattr(system, "command", lambda *args, **kwargs: calls.append(args) or "")
    quiescence = []
    monkeypatch.setattr(system, "quiescence", lambda: quiescence.append(True))
    system.stop()
    assert quiescence == [True]
    assert calls[0] == ("/usr/bin/systemctl", "disable", "--now", "stocks-sync.timer")
    assert calls[1] == ("/usr/bin/systemctl", "stop", "stocks.service", "stocks-sync.service")
    assert not any("start" in call for call in calls)


def test_resume_timer_uses_saved_active_and_enabled_state_only(tmp_path, monkeypatch):
    m = helper()
    calls = []
    system = m.System()
    monkeypatch.setattr(system, "command", lambda *args, **kwargs: calls.append(args) or "")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "activation-complete").write_text("1")
    (bundle / "manifest.json").write_text(json.dumps({"services": {"timer_active": False, "timer_enabled": "disabled"}}))
    system.resume_timer(bundle)
    assert calls == []
    (bundle / "manifest.json").write_text(json.dumps({"services": {"timer_active": True, "timer_enabled": "enabled"}}))
    system.resume_timer(bundle)
    assert calls == [("/usr/bin/systemctl", "enable", "stocks-sync.timer"), ("/usr/bin/systemctl", "start", "stocks-sync.timer")]


def test_permission_plan_separates_status_private_state_and_shared_db(tmp_path, monkeypatch):
    m = helper()
    root, old, bundle = fixture_tree(tmp_path)
    m.migrate_state(root, bundle)
    calls = []
    monkeypatch.setattr(m.os, "chown", lambda path, uid, gid: calls.append((Path(path), uid, gid)))
    m.apply_permissions(root, web_uid=101, web_gid=102, worker_uid=201, worker_gid=202, data_gid=301)
    assert stat.S_IMODE((root / "var/lib/stocks-data").stat().st_mode) == 0o2770
    assert stat.S_IMODE((root / "var/lib/stocks-data/portfolio.db").stat().st_mode) == 0o660
    assert stat.S_IMODE((root / "var/lib/stocks-status").stat().st_mode) == 0o2750
    assert stat.S_IMODE((root / "var/lib/stocks-sync").stat().st_mode) == 0o700
    assert (root / "var/lib/stocks-status", 201, 102) in calls
    assert (root / "var/lib/stocks-data/portfolio.db", 101, 301) in calls


@pytest.mark.parametrize("uid,host,release,previous", [
    (1000, "geoff-Surface-Pro-4", "/opt/stocks/releases/new", "/opt/stocks/releases/old"),
    (0, "wrong-host", "/opt/stocks/releases/new", "/opt/stocks/releases/old"),
    (0, "geoff-Surface-Pro-4", "/tmp/new", "/opt/stocks/releases/old"),
    (0, "geoff-Surface-Pro-4", "/opt/stocks/releases/new", "/tmp/old"),
])
def test_host_identity_and_release_scope_fail_closed(uid, host, release, previous):
    m = helper()
    with pytest.raises(m.MigrationError):
        m.validate_host_identity(uid, host, Path(release), Path(previous))


def test_cli_default_is_help_and_activation_refuses_unprivileged():
    import subprocess
    import sys
    path = ROOT / "deploy/broker_isolation.py"
    result = subprocess.run([sys.executable, str(path), "--help"], capture_output=True, text=True)
    assert result.returncode == 0 and "preflight" in result.stdout
    result = subprocess.run([sys.executable, str(path), "activate", "--release", "/tmp/new", "--expect-current", "/tmp/old", "--confirm", "ISOLATE"], capture_output=True, text=True)
    assert result.returncode != 0 and "root" in result.stderr
    assert "Traceback" not in result.stderr


def test_snapshot_rejects_unknown_service_states(monkeypatch):
    m = helper()
    system = m.System()
    monkeypatch.setattr(system, "command", lambda *args, **kwargs: "mystery")
    with pytest.raises(m.MigrationError):
        system.snapshot()


def test_health_requires_stable_active_service_and_401(monkeypatch):
    m = helper()
    system = m.System()
    calls = []
    def command(*args, **kwargs):
        calls.append(args)
        if "is-active" in args:
            return "active"
        if "show" in args:
            return "0"
        if args[0] == "/usr/bin/curl":
            return "401"
        raise AssertionError(args)
    monkeypatch.setattr(system, "command", command)
    monkeypatch.setattr(m.time, "sleep", lambda _: None)
    system.health()
    assert len([c for c in calls if c[0] == "/usr/bin/curl"]) == 2
    monkeypatch.setattr(system, "command", lambda *args, **kw: "200" if args[0] == "/usr/bin/curl" else command(*args, **kw))
    with pytest.raises(m.MigrationError):
        system.health()
