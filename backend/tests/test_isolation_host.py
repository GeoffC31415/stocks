"""Host adapter contracts: commands mocked; never operate real services."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


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
