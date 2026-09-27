"""Nonprivileged guards only: never invoke systemd or change ownership."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/rehearse_broker_isolation.py"


def load():
    assert SCRIPT.exists(), "rehearsal implementation is missing"
    spec = importlib.util.spec_from_file_location("rehearsal", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nonroot_refused_before_any_command(monkeypatch):
    module = load()
    monkeypatch.setattr(module.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("command executed"))
    with pytest.raises(RuntimeError, match="root"):
        module.preflight()


def test_wrong_host_refused(monkeypatch):
    module = load()
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.socket, "gethostname", lambda: "other-host")
    with pytest.raises(RuntimeError, match="host"):
        module.preflight()


@pytest.mark.parametrize("path", ["relative", "/var/lib/stocks", "/var/tmp/wrong", "/var/tmp/stocks-isolation-rehearsal-../x"])
def test_output_guard(path):
    with pytest.raises(RuntimeError):
        load().validate_output(Path(path))


def test_output_symlink_refused(tmp_path):
    link = tmp_path / "stocks-isolation-rehearsal-test"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RuntimeError):
        load().validate_output(link)


def test_commands_are_transient_and_fixture_scoped():
    module = load()
    root = Path("/var/tmp/stocks-isolation-rehearsal-test")
    ids = (60001, 60002, 60003)
    for role, uid, other in [("web", 60001, "worker"), ("worker", 60002, "web")]:
        cmd = module.command(root, ids, role, "stocks-rehearsal-test-1.service", "hold", "web.db")
        assert cmd[:5] == ["/usr/bin/systemd-run", "--quiet", "--wait", "--pipe", "--collect"]
        for setting in [f"User={uid}", f"Group={uid}", "SupplementaryGroups=60003", "ProtectSystem=strict", "ProtectHome=true", "NoNewPrivileges=true", "RestrictAddressFamilies=AF_UNIX", "RuntimeMaxSec=45s", "KillMode=control-group", f"InaccessiblePaths={root / other}"]:
            assert "--property=" + setting in cmd
        assert str(root / "probe.py") in cmd
        assert not any("/var/lib/stocks" in x or "EnvironmentFile" in x for x in cmd)
    with pytest.raises(RuntimeError):
        module.command(root, ids, "web", "stocks.service", "hold", "web.db")


@pytest.mark.parametrize("output, expected", [("ActiveState=inactive\nMainPID=0\n", True), ("ActiveState=failed\nMainPID=0\n", True), ("", False), ("ActiveState=active\nMainPID=12\n", False), ("ActiveState=inactive\nMainPID=12\n", False)])
def test_cleanup_requires_explicit_inactive_no_pid(output, expected):
    assert load().stopped(output) is expected


def test_fixture_modes():
    layout = load().layout((60001, 60002, 60003))
    assert layout["web"] == (60001, 60001, 0o700)
    assert layout["worker"] == (60002, 60002, 0o700)
    assert layout["shared"] == (0, 60003, 0o2770)
    assert layout["status"] == (60002, 60001, 0o2750)


def test_probe_compiles_and_has_no_provider_calls():
    module = load()
    compile(module.PROBE, "probe.py", "exec")
    assert "integrity_check" in module.PROBE
    assert "-wal" in module.PROBE and "-shm" in module.PROBE
