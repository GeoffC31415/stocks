import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.resolved_database_url(),
    echo=False,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _run_migrations() -> None:
    """Blocking alembic upgrade. Runs in a worker thread, never the event loop.

    Alembic's ``command.upgrade`` is synchronous and opens its own connection;
    calling it directly inside the async ``lifespan`` handler blocks (and can
    deadlock) the event loop before the app ever starts serving. Offloading it
    to a thread keeps startup responsive and unblocks the server.
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini))
    command.upgrade(alembic_cfg, "head")


async def init_db() -> None:
    """Run alembic migrations to ensure the database schema is up to date."""
    await asyncio.to_thread(_run_migrations)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
