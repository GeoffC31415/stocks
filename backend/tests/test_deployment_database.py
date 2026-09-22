"""Deployment checks use disposable databases and a synthetic repository only."""

import configparser
import importlib.util
import shutil
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app import database


@pytest.fixture
def migration_repo(tmp_path, monkeypatch):
    source_root = Path(database.__file__).resolve().parents[2]
    root = tmp_path / "synthetic-repo"
    module = root / "backend" / "app" / "database.py"
    module.parent.mkdir(parents=True)
    module.touch()
    shutil.copytree(source_root / "backend" / "alembic", root / "backend" / "alembic")
    original = root / "original.db"
    with sqlite3.connect(original) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('do-not-migrate')")
    original_bytes = original.read_bytes()
    config = configparser.ConfigParser()
    config.read(source_root / "alembic.ini")
    config.set("alembic", "sqlalchemy.url", f"sqlite+aiosqlite:///{original}".replace("%", "%%"))
    with (root / "alembic.ini").open("w") as stream:
        config.write(stream)
    target = root / "override.db"
    monkeypatch.setattr(database, "__file__", str(module))
    monkeypatch.setattr(
        database,
        "settings",
        SimpleNamespace(resolved_database_url=lambda: f"sqlite+aiosqlite:///{target}"),
    )
    monkeypatch.chdir(root)
    yield root, original, target, config
    # Never point a test at the application's real original database.
    assert original.read_bytes() == original_bytes


def assert_migrated(target):
    assert target.is_file()
    with sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
        assert {"alembic_version", "import_batches", "external_cash_flows"} <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "7e4b8c2a901d",
        )


def test_migrations_use_settings_override_not_ini_database(migration_repo):
    _, _, target, _ = migration_repo
    database._run_migrations()
    assert_migrated(target)
    # A second startup is idempotent.
    database._run_migrations()
    assert_migrated(target)


def test_migrations_resolve_scripts_outside_repo(migration_repo, tmp_path, monkeypatch):
    root, _, target, config = migration_repo
    config.set("alembic", "script_location", "backend/alembic")
    with (root / "alembic.ini").open("w") as stream:
        config.write(stream)
    elsewhere = tmp_path / "unrelated-working-directory"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    database._run_migrations()
    assert_migrated(target)


def test_migrations_preserve_percent_in_database_url(migration_repo, monkeypatch):
    root, _, _, _ = migration_repo
    target = root / "override%database.db"
    monkeypatch.setattr(
        database,
        "settings",
        SimpleNamespace(resolved_database_url=lambda: f"sqlite+aiosqlite:///{target}"),
    )
    database._run_migrations()
    assert_migrated(target)


@pytest.mark.asyncio
async def test_application_sqlite_connections_enforce_safety_pragmas(tmp_path, monkeypatch):
    target = tmp_path / "application.db"
    with sqlite3.connect(target) as connection:
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    # Load a separate module with synthetic configuration; never connect the global engine.
    fake_settings = SimpleNamespace(
        resolved_database_url=lambda: f"sqlite+aiosqlite:///{target}?timeout=0.001"
    )
    monkeypatch.setitem(sys.modules, "app.config", SimpleNamespace(settings=fake_settings))
    spec = importlib.util.spec_from_file_location("isolated_database", database.__file__)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        # Hold both open to check the hook runs on every physical connection.
        async with module.engine.connect() as first, module.engine.connect() as second:
            for connection in (first, second):
                assert (await connection.exec_driver_sql("PRAGMA foreign_keys")).scalar() == 1
                assert (await connection.exec_driver_sql("PRAGMA busy_timeout")).scalar() == 5000
                assert (
                    await connection.exec_driver_sql("PRAGMA journal_mode")
                ).scalar() == journal_mode
                with pytest.raises(IntegrityError):
                    await connection.exec_driver_sql("INSERT INTO child VALUES (999)")
                await connection.rollback()
    finally:
        await module.engine.dispose()
