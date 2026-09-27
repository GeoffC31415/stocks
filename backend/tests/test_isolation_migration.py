"""Migration operates only on synthetic temporary trees in these tests."""
import importlib.util
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

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
        return {"timer_active": True, "timer_enabled": "enabled", "web_active": True, "worker_active": False}
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


@pytest.mark.parametrize("failure", ["health", "marker", "interrupt"])
def test_rollback_failure_after_restart_stops_services(tmp_path, monkeypatch, failure):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    system = FakeSystem()
    m.activate_layout(root, bundle, release, previous, system)
    system.events.clear()
    error = KeyboardInterrupt() if failure == "interrupt" else OSError("injected")
    if failure == "marker":
        write = m.exclusive_write
        def fail_marker(path, *args, **kwargs):
            if path.name == "rollback-complete":
                raise error
            return write(path, *args, **kwargs)
        monkeypatch.setattr(m, "exclusive_write", fail_marker)
    else:
        def fail_health():
            system.events.append("health-failed")
            raise error
        system.health = fail_health
    with pytest.raises(type(error)) as caught:
        m.rollback_layout(root, bundle, system)
    assert caught.value is error
    assert system.events == [
        "stop-timer-worker-web", "reload", "start-web",
        "unauthenticated-401-boundary-only" if failure == "marker" else "health-failed",
        "stop-timer-worker-web",
    ]
    assert (bundle / "rollback-started").exists()
    assert not (bundle / "rollback-complete").exists()
    assert (bundle / "rollback-config/production.env").exists()
    assert (bundle / "evidence").is_dir()


@pytest.mark.parametrize("failure_point", ["fsync", "flush", "close"])
@pytest.mark.parametrize("phase", ["rollback", "activation"])
@pytest.mark.parametrize("invalidation", ["ok", "error", "interrupt", "no-op"])
@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_completion_write_failure_refuses_resume(tmp_path, monkeypatch, error_type, invalidation, phase, failure_point):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    system = FakeSystem()
    if phase == "rollback":
        m.activate_layout(root, bundle, release, previous, system)
        system.events.clear()
    completion = bundle / (phase + "-complete")
    error = error_type("SENTINEL_WRITE")
    write = m.exclusive_write
    fdopen = m.os.fdopen
    observed = []

    def fail_after_creation(fd):
        observed.append(completion.read_bytes())
        raise error

    @contextmanager
    def failing_file(fd, *args, **kwargs):
        with fdopen(fd, *args, **kwargs) as out:
            proxy = Mock(wraps=out)
            if failure_point == "flush":
                def flush():
                    out.flush()
                    fail_after_creation(fd)
                proxy.flush.side_effect = flush
            yield proxy
        # Exercise a context-manager close failure after the real stream closed.
        if failure_point == "close":
            fail_after_creation(fd)

    def write_marker(path, *args, **kwargs):
        if path == completion:
            with monkeypatch.context() as patch:
                if failure_point == "fsync":
                    patch.setattr(m.os, "fsync", fail_after_creation)
                else:
                    patch.setattr(m.os, "fdopen", failing_file)
                return write(path, *args, **kwargs)
        return write(path, *args, **kwargs)

    monkeypatch.setattr(m, "exclusive_write", write_marker)
    unlink = Path.unlink
    cleanup_error = KeyboardInterrupt("SENTINEL_UNLINK") if invalidation == "interrupt" else OSError("SENTINEL_UNLINK")

    def fail_unlink(path, *args, **kwargs):
        if path == completion and invalidation != "ok":
            if invalidation == "no-op":
                return
            raise cleanup_error
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    expected_error = error_type if invalidation == "ok" else m.MigrationError
    with pytest.raises(expected_error) as caught:
        if phase == "rollback":
            m.rollback_layout(root, bundle, system)
        else:
            m.activate_layout(root, bundle, release, previous, system)
    if invalidation == "ok":
        assert caught.value is error
    else:
        assert "completion invalidation could not be confirmed" in str(caught.value)
        assert "SENTINEL" not in str(caught.value)
        if invalidation != "no-op":
            assert caught.value.__cause__ is cleanup_error
            assert cleanup_error.__context__ is error
    assert observed == [b"1\n"]  # Real creation/write/flush happened before failure.
    middle = [] if phase == "rollback" else ["permissions", "permission-probes"]
    assert system.events == ["stop-timer-worker-web", *middle, "reload", "start-web",
                             "unauthenticated-401-boundary-only", "stop-timer-worker-web"]
    if phase == "rollback":
        assert (bundle / "rollback-started").exists()
        assert (bundle / "rollback-config/production.env").exists()
        assert (bundle / "evidence/stocks-sync/browser/secret").read_text() == "SENTINEL_SESSION"
    else:
        assert (bundle / "original-state/browser/secret").read_text() == "SENTINEL_SESSION"
    calls = []
    host = m.System()
    monkeypatch.setattr(host, "command", lambda *a, **kw: calls.append(a) or (
        "enabled" if a[1] == "is-enabled" else "active" if a[1] == "is-active" else ""
    ))
    with pytest.raises(m.MigrationError, match="incomplete transition"):
        host.resume_timer(bundle, root=root)
    assert calls == []
    assert completion.exists() == (invalidation != "ok")
    assert (bundle / (phase + "-complete-pending")).exists()
    if phase == "activation":
        # A later successful rollback supersedes failed activation, not its evidence.
        m.rollback_layout(root, bundle, FakeSystem())
        host.resume_timer(bundle, root=root)
        assert calls[:2] == [("/usr/bin/systemctl", "enable", "stocks-sync.timer"),
                             ("/usr/bin/systemctl", "start", "stocks-sync.timer")]
        assert (bundle / "activation-complete-pending").exists()
        assert not (bundle / "rollback-complete-pending").exists()


@pytest.mark.parametrize("failure_point", ["pending-fsync", "pending-unlink"])
def test_rollback_completion_guard_failure_stays_incomplete(tmp_path, monkeypatch, failure_point):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    system = FakeSystem()
    m.activate_layout(root, bundle, release, previous, system)
    pending = bundle / "rollback-complete-pending"
    error = OSError("SENTINEL_GUARD")
    write, unlink = m.exclusive_write, Path.unlink

    def fail(*args, **kwargs):
        assert pending.exists()
        raise error

    def write_marker(path, *args, **kwargs):
        if path == pending and failure_point == "pending-fsync":
            with monkeypatch.context() as patch:
                patch.setattr(m.os, "fsync", fail)
                return write(path, *args, **kwargs)
        return write(path, *args, **kwargs)

    def unlink_marker(path, *args, **kwargs):
        if path == pending and failure_point == "pending-unlink":
            fail()
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(m, "exclusive_write", write_marker)
    monkeypatch.setattr(Path, "unlink", unlink_marker)
    with pytest.raises(OSError) as caught:
        m.rollback_layout(root, bundle, system)
    assert caught.value is error
    assert system.events[-1] == "stop-timer-worker-web"
    assert pending.exists()
    assert not (bundle / "rollback-complete").exists()
    host = m.System()
    command = Mock(side_effect=AssertionError("host commands forbidden"))
    monkeypatch.setattr(host, "command", command)
    with pytest.raises(m.MigrationError, match="incomplete transition"):
        host.resume_timer(bundle, root=root)
    command.assert_not_called()


def test_rollback_cleanup_failure_reports_unconfirmed_stop(tmp_path, capsys):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    system = FakeSystem()
    m.activate_layout(root, bundle, release, previous, system)
    system.events.clear()
    original = OSError("SENTINEL_HEALTH")
    cleanup = OSError("SENTINEL_CLEANUP")
    def fail_health():
        system.events.append("health-failed")
        raise original
    def fail_second_stop():
        system.events.append("stop-timer-worker-web")
        if "health-failed" in system.events:
            raise cleanup
    system.health = fail_health
    system.stop = fail_second_stop
    with pytest.raises(m.MigrationError, match="stop could not be confirmed") as caught:
        m.rollback_layout(root, bundle, system)
    assert caught.value.__cause__ is cleanup
    assert cleanup.__context__ is original
    assert "SENTINEL" not in str(caught.value)
    assert system.events == ["stop-timer-worker-web", "reload", "start-web",
                             "health-failed", "stop-timer-worker-web"]
    assert (bundle / "rollback-started").exists()
    assert not (bundle / "rollback-complete").exists()
    assert capsys.readouterr() == ("", "")


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


def test_resume_timer_rejects_failed_rollback_before_host_commands(tmp_path, monkeypatch):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    m.activate_layout(root, bundle, release, previous, FakeSystem())
    monkeypatch.setattr(m, "rollback_state", lambda *a: (_ for _ in ()).throw(OSError("injected")))
    with pytest.raises(OSError):
        m.rollback_layout(root, bundle, FakeSystem())
    assert (bundle / "activation-complete").exists()
    assert (bundle / "rollback-started").exists()
    assert not (bundle / "rollback-complete").exists()
    calls = []
    system = m.System()
    monkeypatch.setattr(system, "command", lambda *a, **kw: calls.append(a))
    with pytest.raises(m.MigrationError, match="incomplete transition"):
        system.resume_timer(bundle)
    assert calls == []


@pytest.mark.parametrize("phase", ["activation", "rollback"])
@pytest.mark.parametrize("hazard", ["marker", "release", "config", "manifest", "incomplete", "orphan-rollback"])
def test_resume_timer_rejects_incoherent_terminal_state(tmp_path, monkeypatch, phase, hazard):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    m.activate_layout(root, bundle, release, previous, FakeSystem())
    if phase == "rollback":
        m.rollback_layout(root, bundle, FakeSystem())
    if hazard == "marker":
        (root / "etc/stocks/isolation.json").write_text('{"bundle":"wrong"}')
    elif hazard == "release":
        m.switch_release(root, release if phase == "rollback" else previous)
    elif hazard == "config":
        (root / "etc/stocks/brokers.env").write_text("drift")
    elif hazard == "manifest":
        manifest = json.loads((bundle / "manifest.json").read_text())
        manifest["services"]["timer_active"] = "false"
        (bundle / "manifest.json").write_text(json.dumps(manifest))
    elif hazard == "incomplete":
        (bundle / (phase + "-complete")).unlink()
    else:
        (bundle / "rollback-complete").write_text("1")
        (bundle / "rollback-started").unlink(missing_ok=True)
    calls = []
    system = m.System()
    monkeypatch.setattr(system, "command", lambda *a, **kw: calls.append(a) or "")
    with pytest.raises(m.MigrationError):
        system.resume_timer(bundle, root=root)
    assert calls == []


@pytest.mark.parametrize("phase", ["activation", "rollback"])
@pytest.mark.parametrize("enabled", ["enabled", "disabled"])
@pytest.mark.parametrize("active", [True, False])
def test_resume_timer_reconciles_drift_and_reads_back(tmp_path, monkeypatch, enabled, active, phase):
    m = helper()
    calls = []
    state = {"enabled": "disabled" if enabled == "enabled" else "enabled", "active": not active}
    def command(*args, **kwargs):
        calls.append(args)
        action = args[1]
        if action in {"enable", "disable"}:
            state["enabled"] = "enabled" if action == "enable" else "disabled"
        elif action in {"start", "stop"}:
            state["active"] = action == "start"
        elif action == "is-enabled":
            return state["enabled"]
        elif action == "is-active":
            return "active" if state["active"] else "inactive"
        else:
            raise AssertionError(args)
        return ""
    system = m.System()
    monkeypatch.setattr(system, "command", command)
    root, bundle, release, previous = deployment_fixture(tmp_path)
    m.activate_layout(root, bundle, release, previous, FakeSystem())
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["services"].update(timer_active=active, timer_enabled=enabled)
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    if phase == "rollback":
        m.rollback_layout(root, bundle, FakeSystem())
    system.resume_timer(bundle, root=root)
    assert state == {"enabled": enabled, "active": active}
    assert calls[-2:] == [("/usr/bin/systemctl", "is-enabled", "stocks-sync.timer"), ("/usr/bin/systemctl", "is-active", "stocks-sync.timer")]


@pytest.mark.parametrize("enabled,active", [("disabled", "active"), ("enabled", "inactive"), ("enabled", "activating")])
def test_resume_timer_refuses_readback_mismatch(tmp_path, monkeypatch, enabled, active):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    m.activate_layout(root, bundle, release, previous, FakeSystem())
    system = m.System()
    monkeypatch.setattr(system, "command", lambda *a, **kw: enabled if a[1] == "is-enabled" else active if a[1] == "is-active" else "")
    with pytest.raises(m.MigrationError, match="readback"):
        system.resume_timer(bundle, root=root)


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
