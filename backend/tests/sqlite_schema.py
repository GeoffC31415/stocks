"""Schema setup for disposable file-backed SQLite test databases only."""

from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import Base


async def create_file_schema(engine: AsyncEngine) -> None:
    """Create the current schema without changing later connection semantics."""
    async with engine.begin() as connection:
        # sqlite3 legacy transaction control leaves DDL in physical autocommit
        # despite engine.begin(). Batch only this fresh synthetic schema setup;
        # do not install connection hooks or alter later owner transactions.
        await connection.exec_driver_sql("BEGIN")
        await connection.run_sync(Base.metadata.create_all)
