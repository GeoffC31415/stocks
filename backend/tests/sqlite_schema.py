"""Schema setup for disposable SQLite test databases only."""

from functools import lru_cache

from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import CreateIndex, CreateTable

from app.models import Base


@lru_cache(maxsize=1)
def _compiled_sqlite_ddl_script() -> str:
    dialect = sqlite_dialect.dialect()
    statements: list[str] = ["BEGIN;"]
    for table in Base.metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect)) + ";")
        for index in table.indexes:
            statements.append(str(CreateIndex(index).compile(dialect=dialect)) + ";")
    statements.append("COMMIT;")
    return "\n".join(statements)


async def create_file_schema(engine: AsyncEngine) -> None:
    """Create the current schema in one physical SQLite transaction without altering later connections."""
    script = _compiled_sqlite_ddl_script()
    async with engine.connect() as connection:
        # Execute the precompiled schema in one physical BEGIN/COMMIT batch on the
        # raw SQLite connection so setup pays a single round-trip and durability
        # barrier without installing hooks or altering later owner transactions.
        raw = await connection.get_raw_connection()
        await raw.driver_connection.executescript(script)
