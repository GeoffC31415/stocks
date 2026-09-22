"""Installer safety entry points; no sudo, network, or service writes."""
import os
from pathlib import Path
import sqlite3
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/install-surface.sh"


def run(*args):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, timeout=20)


def test_check_finds_uv_outside_normal_terminal_path(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    database = tmp_path / "fixture.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE fixture(value TEXT)")
    before = database.read_bytes()
    result = run("--check", "--database", str(database))
    assert result.returncode == 0, result.stderr
    assert "No files changed" in result.stdout
    assert database.read_bytes() == before


def test_help_explains_non_install_modes():
    result = run("--help")
    assert result.returncode == 0
    assert "--check" in result.stdout
    assert "--prepare-only" in result.stdout
    assert "--install" in result.stdout


def test_missing_database_is_not_silently_created(tmp_path):
    missing = tmp_path / "missing.db"
    result = run("--check", "--database", str(missing))
    assert result.returncode != 0
    assert "database" in result.stderr.lower()
    assert not missing.exists()


def test_check_is_read_only_with_real_synthetic_database(tmp_path):
    database = tmp_path / "synthetic.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sentinel(value TEXT)")
    before = database.read_bytes()
    result = run("--check", "--database", str(database))
    assert result.returncode == 0, result.stderr
    assert "No files changed" in result.stdout
    assert database.read_bytes() == before
    assert set(tmp_path.iterdir()) == {database}


def test_internal_activation_cannot_run_unprivileged(tmp_path):
    assert os.getuid() != 0, "Run installer tests as an ordinary user"
    result = run("--activate", str(tmp_path))
    assert result.returncode != 0
    assert "root" in result.stderr.lower()


@pytest.mark.parametrize("existing", [
    "stocks.service", "stocks-proxy.service", "stocks.service.d",
    "stocks-proxy.service.d", "stocks-.service.d", "service.d",
])
def test_refuses_units_and_dropins_in_any_effective_unit_path(tmp_path, monkeypatch, existing):
    import shlex

    database = tmp_path / "fixture.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE fixture (value TEXT)")
    unit_dir = tmp_path / "vendor-units"
    unit_dir.mkdir()
    (unit_dir / existing).touch()
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    # Deliberately report not-found: orphaned drop-ins can still be inherited later.
    tools = {
        "systemd-analyze": "#!/bin/bash\nprintf '%s\\n' " + shlex.quote(str(unit_dir)) + "\n",
        "systemctl": "#!/bin/bash\nif [[ $1 == show ]]; then printf 'not-found\\n'; else exit 1; fi\n",
    }
    for name, content in tools.items():
        program = binary_dir / name
        program.write_text(content)
        program.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary_dir) + os.pathsep + os.environ["PATH"])
    result = run("--check", "--database", str(database))
    assert result.returncode != 0
    assert "unit" in result.stderr.lower() or "drop-in" in result.stderr.lower()
