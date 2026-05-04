from collections.abc import AsyncGenerator

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base
from app.services.order_fingerprint import order_fingerprint

engine = create_async_engine(
    settings.resolved_database_url(),
    echo=False,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _migrate_order_dedupe(sync_conn: Connection) -> None:
    order_columns = {
        row[1] for row in sync_conn.exec_driver_sql("PRAGMA table_info(orders)").fetchall()
    }
    if "order_fingerprint" not in order_columns:
        sync_conn.exec_driver_sql("ALTER TABLE orders ADD COLUMN order_fingerprint VARCHAR(64)")

    rows = sync_conn.exec_driver_sql(
        """
        SELECT
            id,
            security_name,
            order_date,
            order_status,
            account_name,
            side,
            quantity,
            cost_proceeds_gbp,
            country
        FROM orders
        ORDER BY id
        """
    ).fetchall()

    seen_fingerprints: set[str] = set()
    duplicate_ids: list[int] = []
    fingerprints_by_id: dict[int, str] = {}

    for row in rows:
        fingerprint = order_fingerprint(
            security_name=row[1],
            order_date=row[2],
            order_status=row[3],
            account_name=row[4],
            side=row[5],
            quantity=row[6],
            cost_proceeds_gbp=row[7],
            country=row[8],
        )
        if fingerprint in seen_fingerprints:
            duplicate_ids.append(row[0])
            continue

        seen_fingerprints.add(fingerprint)
        fingerprints_by_id[row[0]] = fingerprint

    for order_id, fingerprint in fingerprints_by_id.items():
        sync_conn.exec_driver_sql(
            "UPDATE orders SET order_fingerprint = ? WHERE id = ?",
            (fingerprint, order_id),
        )

    if duplicate_ids:
        placeholders = ",".join("?" for _ in duplicate_ids)
        sync_conn.exec_driver_sql(
            f"DELETE FROM orders WHERE id IN ({placeholders})",
            tuple(duplicate_ids),
        )

    sync_conn.exec_driver_sql(
        """
        UPDATE order_import_batches
        SET row_count = (
            SELECT COUNT(*)
            FROM orders
            WHERE orders.order_import_batch_id = order_import_batches.id
        )
        """
    )
    sync_conn.exec_driver_sql("DELETE FROM order_import_batches WHERE row_count = 0")
    sync_conn.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_orders_order_fingerprint ON orders(order_fingerprint)"
    )


def _add_column_if_missing(
    sync_conn: Connection, table_name: str, column_name: str, ddl: str
) -> None:
    columns = {
        row[1] for row in sync_conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        sync_conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def _migrate_portfolio_metadata(sync_conn: Connection) -> None:
    _add_column_if_missing(sync_conn, "instruments", "ticker", "ticker VARCHAR(64)")
    _add_column_if_missing(sync_conn, "instruments", "sector", "sector VARCHAR(128)")
    _add_column_if_missing(sync_conn, "instruments", "region", "region VARCHAR(128)")
    _add_column_if_missing(sync_conn, "instruments", "asset_class", "asset_class VARCHAR(128)")
    _add_column_if_missing(
        sync_conn,
        "instrument_groups",
        "target_allocation_pct",
        "target_allocation_pct FLOAT",
    )


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_order_dedupe)
        await conn.run_sync(_migrate_portfolio_metadata)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
