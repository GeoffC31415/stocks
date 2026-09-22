"""Factory database isolation: only synthetic SQLite files, never private data."""

import sqlite3
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import database, main
from app.config import Settings


@pytest.fixture
async def databases(tmp_path, monkeypatch):
    paths = [tmp_path / "original.db", tmp_path / "supplied.db"]
    for path in paths:
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
            connection.execute("INSERT INTO sentinel VALUES (?)", (path.name,))
    before = [path.read_bytes() for path in paths]
    configs = [
        Settings(_env_file=None, database_url=f"sqlite+aiosqlite:///{path}")
        for path in paths
    ]
    engines = [create_async_engine(config.resolved_database_url()) for config in configs]
    connections = Mock(side_effect=AssertionError("No database connection is permitted"))
    for engine in engines:
        event.listen(engine.sync_engine, "do_connect", connections)
    migration = AsyncMock(side_effect=AssertionError("No migration is permitted"))
    dependency = Mock(side_effect=AssertionError("No dependency is permitted"))
    constructor = Mock(wraps=main.SecuredFastAPI)
    monkeypatch.setattr(main, "init_db", migration)
    monkeypatch.setattr(database, "get_session", dependency)
    monkeypatch.setattr(main, "SecuredFastAPI", constructor)
    try:
        yield configs, engines, constructor, migration, dependency
    finally:
        connections.assert_not_called()
        migration.assert_not_called()
        dependency.assert_not_called()
        assert [path.read_bytes() for path in paths] == before
        for engine in engines:
            await engine.dispose()


@pytest.mark.parametrize("mismatch", ["all", "engine", "session", "migration"])
async def test_factory_rejects_database_mismatch_before_app_creation(databases, monkeypatch, mismatch):
    configs, engines, constructor, _, _ = databases
    # Each independent global can otherwise silently point at the original DB.
    monkeypatch.setattr(database, "engine", engines[0 if mismatch in {"all", "engine"} else 1])
    monkeypatch.setattr(
        database, "SessionLocal",
        async_sessionmaker(engines[0 if mismatch in {"all", "session"} else 1]),
    )
    monkeypatch.setattr(database, "settings", configs[0 if mismatch in {"all", "migration"} else 1])
    monkeypatch.setattr(main, "settings", configs[0])

    with pytest.raises(ValueError, match="database configuration"):
        main.create_app(configs[1])
    constructor.assert_not_called()


@pytest.mark.parametrize("mode", ["local", "public"])
async def test_factory_accepts_same_database_with_different_web_settings(databases, monkeypatch, mode):
    configs, engines, constructor, _, _ = databases
    monkeypatch.setattr(database, "engine", engines[0])
    monkeypatch.setattr(database, "SessionLocal", async_sessionmaker(engines[0]))
    monkeypatch.setattr(database, "settings", configs[0])
    monkeypatch.setattr(main, "settings", configs[0])
    config = configs[0].model_copy(update={"deployment_mode": mode})

    application = main.create_app(config)

    assert application.state.web_config is config
    assert application.openapi_url == (None if mode == "public" else "/openapi.json")
    constructor.assert_called_once()
