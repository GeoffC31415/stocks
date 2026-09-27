"""Nonprivileged guards only: never invoke systemd or change ownership."""
import importlib.util
import os
import sqlite3
import stat
import subprocess
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
        for setting in ["User=0", "Group=0", "SupplementaryGroups=", "CapabilityBoundingSet=CAP_SETUID CAP_SETGID CAP_SETPCAP", "ProtectSystem=strict", "ProtectHome=true", "NoNewPrivileges=true", "RestrictAddressFamilies=AF_UNIX", "RuntimeMaxSec=45s", "KillMode=control-group", f"InaccessiblePaths={root / other}"]:
            assert "--property=" + setting in cmd
        launcher = cmd.index('/usr/bin/setpriv')
        assert all(arg.startswith('--') for arg in cmd[1:launcher])
        assert cmd[launcher:launcher + 13] == [
            '/usr/bin/setpriv', f'--reuid={uid}', f'--regid={uid}',
            '--groups=60003', '--bounding-set=-all', '--inh-caps=-all',
            '--ambient-caps=-all', '--no-new-privs', '--',
            '/usr/bin/python3', '-I', '-B', '-u']
        assert cmd[launcher + 13] == str(root / 'probe.py')
        assert cmd.count('/usr/bin/python3') == 1
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


@pytest.mark.parametrize('field, value', [
    (field, ' '.join('0' if n == index else '60001' for n in range(4)))
    for field in ('Uid', 'Gid') for index in range(4)
] + [(field, '1') for field in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')]
  + [('Groups', '60003 0'), ('Groups', ''), ('Groups', '60001'),
     ('NoNewPrivs', '0'), ('Uid', '60001'), ('CapEff', None)])
def test_probe_rejects_residual_privilege_before_access(field, value):
    import ast
    module = load()
    tree = ast.parse(module.PROBE)
    functions: list[ast.stmt] = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == 'check_credentials']
    assert len(functions) == 1, 'probe must validate full credentials before access'
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'credentials', 'exec'), namespace)  # noqa: S102 - trusted probe helper only
    status = {'Uid': '60001 60001 60001 60001', 'Gid': '60001 60001 60001 60001',
              'Groups': '60003', 'NoNewPrivs': '1',
              **{name: '0000000000000000' for name in
                 ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')}}
    def text():
        return '\n'.join(f'{key}:\t{val}' for key, val in status.items())
    namespace['check_credentials'](text(), 60001, 60003)
    if value is None:
        del status[field]
    else:
        status[field] = value
    with pytest.raises((AssertionError, KeyError, ValueError)):
        namespace['check_credentials'](text(), 60001, 60003)
    assert module.PROBE.index("check_credentials(Path('/proc/self/status')") < module.PROBE.index('denied(root')
    assert "'capabilities': True" in module.PROBE
    assert "'capabilities'" in SCRIPT.read_text().split("report['passed'] =", 1)[1]


def database_probe(root, action):
    # Execute the actual probe's database block, without privileged setup/checks.
    block = load().PROBE.split("db = root / 'shared' / database\n", 1)[1]
    block = "db = root / 'shared' / database\n" + block.split("for suffix in", 1)[0]
    namespace = {"root": root, "action": action, "database": "proof.db", "role": "web",
                 "os": os, "sqlite3": sqlite3}
    try:
        exec(compile(block, "probe-database", "exec"), namespace)  # noqa: S102 - trusted repository probe
    except BaseException:
        connection = namespace.get("connection")
        if isinstance(connection, sqlite3.Connection):
            connection.close()
        raise
    connection = namespace["connection"]
    assert isinstance(connection, sqlite3.Connection)
    return connection


@pytest.mark.skipif(os.geteuid() == 0, reason="must exercise unprivileged SQLite")
def test_probe_live_wal_permissions(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o2770)
    previous = os.umask(0o007)
    connection = None
    try:
        connection = database_probe(tmp_path, "hold")
        for suffix in ("", "-wal", "-shm"):
            info = (shared / ("proof.db" + suffix)).stat()
            assert stat.S_IMODE(info.st_mode) == 0o660, (suffix, oct(info.st_mode))
            assert info.st_uid == os.geteuid()
            assert info.st_gid == shared.stat().st_gid
        writer = database_probe(tmp_path, "write")
        writer.close()
        assert connection.execute("SELECT COUNT(*) FROM proof").fetchone() == (2,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        if connection is not None:
            connection.close()
        os.umask(previous)


@pytest.mark.parametrize("symlink", [False, True])
def test_holder_refuses_existing_database_without_mutation(tmp_path, symlink):
    shared = tmp_path / "shared"
    shared.mkdir()
    target = tmp_path / "target"
    target.write_bytes(b"untouched")
    target.chmod(0o600)
    db = shared / "proof.db"
    if symlink:
        db.symlink_to(target)
    else:
        db.write_bytes(b"untouched")
        db.chmod(0o600)
    before = db.stat()
    with pytest.raises(FileExistsError):
        database_probe(tmp_path, "hold")
    after = db.stat()
    assert db.read_bytes() == target.read_bytes() == b"untouched"
    assert (after.st_ino, after.st_mode, after.st_uid, after.st_gid) == (
        before.st_ino, before.st_mode, before.st_uid, before.st_gid)
    assert list(shared.iterdir()) == [db]


def test_readiness_failure_retains_bounded_synthetic_stderr():
    module = load()
    with subprocess.Popen(
        ['/usr/bin/python3', '-I', '-c',
         "import sys; sys.stderr.write('synthetic credential failure ' + 'x' * 3000)"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) as child:
        child.wait(timeout=5)
        message = module.readiness_error(child)
    assert 'synthetic credential failure' in message
    assert len(message) <= 2100


def test_readiness_error_does_not_wait_for_running_child():
    module = load()
    with subprocess.Popen(
        ['/usr/bin/python3', '-I', '-c', 'import sys; sys.stdin.read()'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) as child:
        try:
            assert 'no stderr available' in module.readiness_error(child)
            assert child.poll() is None
        finally:
            child.communicate(timeout=5)


def test_writer_requires_existing_database(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    with pytest.raises(sqlite3.OperationalError, match="unable to open"):
        database_probe(tmp_path, "write")
    assert list(shared.iterdir()) == []
