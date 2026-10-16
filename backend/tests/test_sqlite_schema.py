"""Structural checks for test-only DDL batching; no timing thresholds."""

from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlite_schema import create_file_schema

from app.models import Base, Instrument


async def test_file_schema_has_one_physical_transaction(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'batched.db'}")
    statements = []

    @event.listens_for(engine.sync_engine, "connect")
    def trace(dbapi_connection, _record):
        dbapi_connection.run_async(lambda connection: connection.set_trace_callback(statements.append))

    try:
        await create_file_schema(engine)
        # SQLAlchemy's logical begin alone does not start SQLite's DDL transaction.
        assert [sql for sql in statements if sql.upper().startswith("BEGIN")] == ["BEGIN"]
        assert statements.count("COMMIT") == 1
        assert "ROLLBACK" not in statements
        assert any("CREATE TABLE" in sql for sql in statements)
        assert statements.index("BEGIN") < next(
            i for i, sql in enumerate(statements) if "CREATE TABLE" in sql
        ) < statements.index("COMMIT")
    finally:
        await engine.dispose()


async def test_file_schema_matches_unbatched_metadata(tmp_path):
    engines = [
        create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
        for name in ("reference.db", "batched.db")
    ]
    try:
        async with engines[0].begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await create_file_schema(engines[1])
        schemas = []
        for engine in engines:
            async with engine.connect() as connection:
                schemas.append((await connection.execute(text(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
                ))).all())
        assert schemas[0]
        assert schemas[0] == schemas[1]
    finally:
        for engine in engines:
            await engine.dispose()


async def test_file_schema_preserves_isolation_and_default_transactions(tmp_path):
    engines = [
        create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
        for name in ("first.db", "fresh.db")
    ]

    @event.listens_for(engines[0].sync_engine, "connect")
    def configure(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=100")
        cursor.close()

    try:
        for engine in engines:
            await create_file_schema(engine)
        factory = async_sessionmaker(engines[0], expire_on_commit=False)
        count = select(func.count()).select_from(Instrument)
        async with engines[0].connect() as connection:
            assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
            assert await connection.scalar(text("PRAGMA busy_timeout")) == 100
            raw = await connection.get_raw_connection()
            assert raw.driver_connection.isolation_level == ""
            assert not raw.driver_connection.in_transaction
        async with factory() as owner, factory() as reader:
            owner.add(Instrument(account_name="Synthetic", identifier="A", security_name="Asset"))
            await owner.flush()
            assert await owner.scalar(count) == 1
            assert await reader.scalar(count) == 0  # Independent connection, no dirty reads.
            await reader.rollback()
            await owner.rollback()
            assert await owner.scalar(count) == 0
            owner.add(Instrument(account_name="Synthetic", identifier="B", security_name="Asset"))
            await owner.commit()
            assert await reader.scalar(count) == 1
        async with async_sessionmaker(engines[1])() as fresh:
            assert await fresh.scalar(count) == 0
    finally:
        for engine in engines:
            await engine.dispose()
