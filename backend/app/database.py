import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.resolved_database_url(),
    echo=False,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


if engine.dialect.name == "sqlite":

    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        """Enforce integrity and bound lock waits without changing journal mode."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


def _run_migrations() -> None:
    """Blocking alembic upgrade. Runs in a worker thread, never the event loop.

    Alembic's ``command.upgrade`` is synchronous and opens its own connection;
    calling it directly inside the async ``lifespan`` handler blocks (and can
    deadlock) the event loop before the app ever starts serving. Offloading it
    to a thread keeps startup responsive and unblocks the server.
    """
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    project_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    # ConfigParser treats percent signs as interpolation, including URL escapes.
    alembic_cfg.set_main_option(
        "script_location", str(project_root / "backend" / "alembic").replace("%", "%%")
    )
    alembic_cfg.set_main_option(
        "sqlalchemy.url", settings.resolved_database_url().replace("%", "%%")
    )
    command.upgrade(alembic_cfg, "head")


async def init_db() -> None:
    """Run alembic migrations to ensure the database schema is up to date."""
    await asyncio.to_thread(_run_migrations)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
