"""Test the additive migration against a real isolated SQLite database."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_cash_ledger_migration_preserves_existing_data_and_roundtrips(tmp_path):
    path = Path(__file__).parents[1] / "alembic/versions/7e4b8c2a901d_external_cash_flows.py"
    assert path.exists(), "Cash ledger needs a deployable database migration"
    spec = importlib.util.spec_from_file_location("cash_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE preservation_test (value TEXT)")
        conn.exec_driver_sql("INSERT INTO preservation_test VALUES ('untouched')")
        module.op = Operations(MigrationContext.configure(conn))
        module.upgrade()
        assert {"external_cash_flows", "cash_flow_coverage"}.issubset(
            sa.inspect(conn).get_table_names()
        )
        conn.exec_driver_sql(
            "INSERT INTO external_cash_flows (source, account_name, reference, occurred_at, amount_gbp) VALUES ('trading212', 'test', 'ref', '2026-01-01', 1)"
        )
        assert conn.exec_driver_sql("SELECT value FROM preservation_test").scalar() == "untouched"
        module.downgrade()
        assert sa.inspect(conn).get_table_names() == ["preservation_test"]
    engine.dispose()
