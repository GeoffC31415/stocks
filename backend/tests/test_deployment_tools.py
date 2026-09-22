"""Deployment tools use disposable files, never a user's portfolio."""

import importlib.util
import sqlite3
import stat
from pathlib import Path

import pytest
from dotenv import dotenv_values


def tool():
    path = Path(__file__).resolve().parents[2] / "scripts" / "deployment.py"
    assert path.is_file(), "Deployment helper is missing"
    spec = importlib.util.spec_from_file_location("deployment", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_configuration_is_private_hashed_and_never_overwritten(tmp_path):
    module = tool()
    output = tmp_path / "production.env"
    password = "test-only-long-password"
    module.configure(
        output,
        "https://stocks.example.net",
        "geoff",
        password,
        tmp_path / "portfolio.db",
        tmp_path / "dist",
    )
    values = dotenv_values(output)
    assert password not in output.read_text()
    assert values["PORTFOLIO_DEPLOYMENT_MODE"] == "public"
    assert values["PORTFOLIO_AUTH_PASSWORD_HASH"].startswith("scrypt$")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        module.configure(
            output,
            "https://stocks.example.net",
            "geoff",
            password,
            tmp_path / "portfolio.db",
            tmp_path / "dist",
        )
    assert output.read_bytes() == before


@pytest.mark.parametrize(
    "origin,password",
    [
        ("http://stocks.example.net", "test-only-long-password"),
        ("https://stocks.example.net/path", "test-only-long-password"),
        ("https://stocks.example.net", "short"),
    ],
)
def test_invalid_setup_writes_nothing(tmp_path, origin, password):
    output = tmp_path / "production.env"
    with pytest.raises((ValueError, RuntimeError)):
        tool().configure(output, origin, "geoff", password, tmp_path / "db", tmp_path / "dist")
    assert not output.exists()


def test_backup_uses_sqlite_snapshot_preserves_rows_and_refuses_overwrite(tmp_path):
    module = tool()
    source, destination = tmp_path / "source.db", tmp_path / "backup.db"
    with sqlite3.connect(source) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE records (value TEXT)")
        db.execute("INSERT INTO records VALUES ('synthetic fixture')")
        db.commit()
        module.backup(source, destination)
        with sqlite3.connect(destination) as restored:
            assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert restored.execute("SELECT value FROM records").fetchall() == [
                ("synthetic fixture",)
            ]
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        module.backup(source, destination)
    with pytest.raises(FileNotFoundError):
        module.backup(tmp_path / "missing", tmp_path / "new.db")
    assert not (tmp_path / "new.db").exists()
