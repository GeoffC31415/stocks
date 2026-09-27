"""Host adapter contracts: commands mocked; never operate real services."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


EFFECTIVE = dict(ActiveState="active", SubState="running", NRestarts="0",
    NeedDaemonReload="no", InvocationID="1" * 32, ExecStart="/synthetic/web",
    User="stocks", Group="stocks", SupplementaryGroups="", Environment="",
    EnvironmentFiles="", WorkingDirectory="/", RootDirectory="",
    ProtectSystem="strict", ProtectHome="yes", ReadWritePaths="",
    ReadOnlyPaths="", InaccessiblePaths="", BindPaths="", BindReadOnlyPaths="",
    PrivateTmp="yes", NoNewPrivileges="yes", FragmentPath="/synthetic/stocks.service",
    DropInPaths="")


def helper():
    spec = importlib.util.spec_from_file_location("isolation", Path(__file__).resolve().parents[2] / "deploy/broker_isolation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_permissions_refuses_shared_identity_before_changes(tmp_path, monkeypatch):
    m = helper()
    monkeypatch.setattr(m.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=101, pw_gid=101, pw_dir="/var/lib/stocks-sync", pw_shell="/usr/sbin/nologin"))
    monkeypatch.setattr(m.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=301))
    system = m.System()
    calls = []
    monkeypatch.setattr(system, "command", lambda *a, **kw: calls.append(a) or "")
    with pytest.raises(m.MigrationError, match="identit"):
        system.permissions(tmp_path, tmp_path)
    assert calls == []


def test_quiescence_rejects_remaining_service_process(tmp_path):
    m = helper()
    proc = tmp_path / "123"
    proc.mkdir()
    (proc / "status").write_text("Name:\tworker\nUid:\t101\t101\t101\t101\n")
    with pytest.raises(m.MigrationError, match="process"):
        m.assert_quiescent(tmp_path, {101}, Path("/var/lib/stocks"))


def test_quiescence_rejects_foreign_open_database(tmp_path):
    m = helper()
    proc = tmp_path / "123"
    (proc / "fd").mkdir(parents=True)
    (proc / "status").write_text("Uid:\t200\t200\t200\t200\n")
    (proc / "fd/3").symlink_to("/var/lib/stocks/portfolio.db-wal")
    with pytest.raises(m.MigrationError, match="open"):
        m.assert_quiescent(tmp_path, {101}, Path("/var/lib/stocks"))


def test_verify_uses_explicit_identity_groups_and_no_broker_command(tmp_path, monkeypatch):
    m = helper()
    system = m.System()
    monkeypatch.setattr(m.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=101 if name == "stocks" else 201, pw_gid=102 if name == "stocks" else 202))
    monkeypatch.setattr(m.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=301))
    calls = []
    monkeypatch.setattr(system, "command", lambda *a, **kw: calls.append(a) or "")
    system.verify(tmp_path)
    probes = [a for a in calls if a[0] == "/usr/bin/setpriv"]
    assert len(probes) == 2
    assert all("--groups=301" in a for a in probes)
    assert all("sync_cli" not in str(a) for a in calls)
    assert any(a[0] == "/usr/bin/systemd-analyze" for a in calls)


@pytest.mark.parametrize("hazard", [None, "saved", "stopped", "invocation", "boot", "worker", "timer", "reload", "unknown"])
def test_readiness_is_bounded_read_only_and_stable(monkeypatch, hazard):
    m = helper()
    system = m.System()
    calls, sample = [], [0]
    system.health = lambda: None  # Network boundary separately tested; never network here.
    system.boot_identity = lambda: ("00000000-0000-0000-0000-000000000002" if hazard == "boot" and sample[0] > 1 else "00000000-0000-0000-0000-000000000001")
    monkeypatch.setattr(m.time, "sleep", lambda _: None)
    def command(*a, **kw):
        calls.append(a)
        assert kw.get("timeout") == 10
        action = a[1]
        assert action in {"show", "cat", "is-active", "is-enabled"}
        if action == "cat":
            return "[Service]\nExecStart=/synthetic/web"
        if action == "show":
            sample[0] += 1
            values = dict(EFFECTIVE)
            values.update(ActiveState="inactive" if hazard == "stopped" else "active",
                          NeedDaemonReload="yes" if hazard == "reload" else "no",
                          InvocationID=("2" if hazard == "invocation" and sample[0] > 1 else "1") * 32)
            return "\n".join(k + "=" + v for k, v in values.items())
        if action == "is-enabled":
            return "enabled" if hazard == "saved" else "disabled"
        if hazard == "saved" and a[2] == "stocks-sync.timer":
            return "active"
        return "mystery" if hazard == "unknown" else "active" if ((hazard == "worker" and a[2] == "stocks-sync.service") or (hazard == "timer" and a[2] == "stocks-sync.timer")) else "inactive"
    system.command = command
    if hazard not in (None, "saved"):
        with pytest.raises(m.MigrationError):
            system.readiness({"timer_enabled": "enabled", "timer_active": True})
    else:
        result = system.readiness({"timer_enabled": "enabled", "timer_active": True}, timer_mode="saved" if hazard == "saved" else "quiescent")
        assert result["invocation_id"] == "1" * 32
        assert len(result["effective_sha256"]) == 64
    assert calls
