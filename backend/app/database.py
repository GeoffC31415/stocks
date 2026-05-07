from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base
from app.services.order_fingerprint import order_fingerprint

engine = create_async_engine(
    settings.resolved_database_url(),
    echo=False,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _migrate_order_dedupe(sync_conn) -> None:
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
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_orders_order_fingerprint "
        "ON orders(order_fingerprint)"
    )


def _add_column_if_missing(sync_conn, table_name: str, column_name: str, ddl: str) -> None:
    columns = {
        row[1] for row in sync_conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        sync_conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def _migrate_match_metadata(sync_conn) -> None:
    """Add match metadata columns to orders table and create new alias/audit tables."""
    # Match metadata columns on orders
    _add_column_if_missing(sync_conn, "orders", "match_status", "match_status VARCHAR(32)")
    _add_column_if_missing(sync_conn, "orders", "match_method", "match_method VARCHAR(64)")
    _add_column_if_missing(sync_conn, "orders", "match_confidence", "match_confidence FLOAT")
    _add_column_if_missing(sync_conn, "orders", "match_evidence", "match_evidence JSON")
    _add_column_if_missing(sync_conn, "orders", "matched_at", "matched_at DATETIME")
    _add_column_if_missing(sync_conn, "orders", "matched_by", "matched_by VARCHAR(128)")

    # Backfill match_status for existing orders
    sync_conn.exec_driver_sql(
        "UPDATE orders SET match_status = 'legacy_matched', match_method = 'legacy', "
        "matched_at = datetime('now'), matched_by = 'system_backfill' "
        "WHERE match_status IS NULL AND instrument_id IS NOT NULL"
    )
    sync_conn.exec_driver_sql(
        "UPDATE orders SET match_status = 'unmatched' "
        "WHERE match_status IS NULL AND instrument_id IS NULL"
    )

    # account_aliases table
    sync_conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS account_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source VARCHAR(64) NOT NULL,
            source_account_name VARCHAR(512) NOT NULL,
            canonical_account_name VARCHAR(512) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT (datetime('now')),
            created_by VARCHAR(128),
            notes VARCHAR(1024),
            UNIQUE(source, source_account_name)
        )
        """
    )

    # instrument_aliases table
    sync_conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS instrument_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
            source VARCHAR(64) NOT NULL,
            source_account_name VARCHAR(512),
            canonical_account_name VARCHAR(512),
            source_security_name VARCHAR(1024) NOT NULL,
            source_security_name_norm VARCHAR(1024) NOT NULL,
            alias_type VARCHAR(32) NOT NULL,
            confidence FLOAT,
            created_at DATETIME NOT NULL DEFAULT (datetime('now')),
            created_by VARCHAR(128),
            notes VARCHAR(1024),
            UNIQUE(source, source_account_name, source_security_name_norm)
        )
        """
    )

    # order_match_audit table
    sync_conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS order_match_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            old_instrument_id INTEGER REFERENCES instruments(id) ON DELETE SET NULL,
            new_instrument_id INTEGER REFERENCES instruments(id) ON DELETE SET NULL,
            old_status VARCHAR(32),
            new_status VARCHAR(32),
            method VARCHAR(64),
            confidence FLOAT,
            evidence JSON,
            changed_at DATETIME NOT NULL DEFAULT (datetime('now')),
            changed_by VARCHAR(128),
            reason VARCHAR(1024)
        )
        """
    )

    # Seed account_aliases: self-aliases for known snapshot account names
    # This ensures every account seen in snapshots has a canonical mapping
    snapshot_accounts = sync_conn.exec_driver_sql(
        "SELECT DISTINCT account_name FROM instruments WHERE account_name IS NOT NULL"
    ).fetchall()
    for (acct,) in snapshot_accounts:
        sync_conn.exec_driver_sql(
            "INSERT OR IGNORE INTO account_aliases (source, source_account_name, canonical_account_name) "
            "VALUES ('barclays_snapshot', ?, ?)",
            (acct, acct),
        )

    # Seed account_aliases for order account names
    order_accounts = sync_conn.exec_driver_sql(
        "SELECT DISTINCT account_name FROM orders WHERE account_name IS NOT NULL"
    ).fetchall()
    for (acct,) in order_accounts:
        sync_conn.exec_driver_sql(
            "INSERT OR IGNORE INTO account_aliases (source, source_account_name, canonical_account_name) "
            "VALUES ('barclays_orders', ?, ?)",
            (acct, acct),
        )

    # Seed instrument_aliases from existing instruments (import_name type)
    instruments = sync_conn.exec_driver_sql(
        "SELECT id, account_name, security_name FROM instruments WHERE is_cash = 0"
    ).fetchall()
    import re
    _norm_re = re.compile(r"[^a-z0-9 ]+")
    for (inst_id, acct, sec_name,) in instruments:
        norm_name = _norm_re.sub(" ", sec_name.lower()).strip()
        sync_conn.exec_driver_sql(
            "INSERT OR IGNORE INTO instrument_aliases "
            "(instrument_id, source, source_account_name, canonical_account_name, "
            "source_security_name, source_security_name_norm, alias_type, confidence) "
            "VALUES (?, 'barclays_snapshot', ?, ?, ?, ?, 'import_name', 1.0)",
            (inst_id, acct, acct, sec_name, norm_name),
        )


def _migrate_portfolio_metadata(sync_conn) -> None:
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
        await conn.run_sync(_migrate_match_metadata)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
