import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import StaticPool, create_engine, event

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add project root to sys.path so we can import app.models
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# add your model's MetaData object here
# for 'autogenerate' support
from app.models import Base  # noqa: E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    # Convert aiosqlite URL to sync sqlite URL
    sync_url = url.replace("sqlite+aiosqlite:///", "sqlite:///")
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Use the sync sqlite driver for alembic operations.
    The app uses aiosqlite for async, but alembic runs migrations
    synchronously during startup.
    """
    url = config.get_main_option("sqlalchemy.url")
    # Convert aiosqlite URL to sync sqlite URL
    sync_url = url.replace("sqlite+aiosqlite:///", "sqlite:///")
    connectable = create_engine(
        sync_url,
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(connectable, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        """Enable foreign keys for SQLite."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
