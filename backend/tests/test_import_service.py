import asyncio
import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Instrument
from app.services.barclays_parser import ParsedHoldingRow
from app.services.hl_parser import HL_ACCOUNT_NAME
from app.services.import_service import compare_import_batches, import_holding_snapshot
from app.services.portfolio_service import portfolio_value_timeseries


def _holding(
    *,
    account_name: str,
    identifier: str,
    investment: str,
    value_gbp: float,
    quantity: float = 1,
) -> ParsedHoldingRow:
    return ParsedHoldingRow(
        account_name=account_name,
        investment=investment,
        identifier=identifier,
        quantity=quantity,
        last_price=None,
        last_price_ccy=None,
        value=None,
        value_ccy="GBP",
        fx_rate=None,
        last_price_pence=None,
        value_gbp=value_gbp,
        book_cost=None,
        book_cost_ccy="GBP",
        average_fx_rate=None,
        book_cost_gbp=value_gbp,
        pct_change=0,
        is_cash=False,
    )


async def _import_hl_after_barclays() -> tuple[Instrument, dict, list[dict]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        await import_holding_snapshot(
            session,
            parsed_rows=[
                _holding(
                    account_name="Barclays ISA",
                    identifier="VWRL",
                    investment="Vanguard FTSE All-World",
                    value_gbp=1000,
                )
            ],
            as_of_date=dt.date(2026, 5, 1),
            filename="barclays.xls",
            file_sha256="barclays",
        )
        _, summary = await import_holding_snapshot(
            session,
            parsed_rows=[
                _holding(
                    account_name=HL_ACCOUNT_NAME,
                    identifier="EQQQ",
                    investment="Invesco Nasdaq 100",
                    value_gbp=2000,
                )
            ],
            as_of_date=dt.date(2026, 5, 4),
            filename="hl.csv",
            file_sha256="hl",
        )
        barclays = (
            await session.execute(
                select(Instrument).where(
                    Instrument.account_name == "Barclays ISA",
                    Instrument.identifier == "VWRL",
                )
            )
        ).scalar_one()
        timeseries = await portfolio_value_timeseries(session)

    await engine.dispose()
    return barclays, summary, timeseries


def test_importing_hl_snapshot_does_not_close_barclays_instruments() -> None:
    barclays, summary, _ = asyncio.run(_import_hl_after_barclays())

    assert barclays.closed_at is None
    assert summary["closed"] == []


def test_portfolio_timeseries_carries_forward_other_account_snapshots() -> None:
    _, _, timeseries = asyncio.run(_import_hl_after_barclays())

    assert [row["total_value_gbp"] for row in timeseries] == [1000.0, 3000.0]


async def _compare_multi_account_snapshots() -> dict:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        batch1, _ = await import_holding_snapshot(
            session,
            parsed_rows=[
                _holding(
                    account_name="Barclays ISA",
                    identifier="VWRL",
                    investment="Vanguard FTSE All-World",
                    value_gbp=1000,
                    quantity=10,
                )
            ],
            as_of_date=dt.date(2026, 5, 1),
            filename="barclays-1.xls",
            file_sha256="barclays-1",
        )
        batch2, _ = await import_holding_snapshot(
            session,
            parsed_rows=[
                _holding(
                    account_name=HL_ACCOUNT_NAME,
                    identifier="EQQQ",
                    investment="Invesco Nasdaq 100",
                    value_gbp=2000,
                    quantity=20,
                )
            ],
            as_of_date=dt.date(2026, 5, 2),
            filename="hl.csv",
            file_sha256="hl",
        )
        batch3, _ = await import_holding_snapshot(
            session,
            parsed_rows=[
                _holding(
                    account_name="Barclays ISA",
                    identifier="VWRL",
                    investment="Vanguard FTSE All-World",
                    value_gbp=1200,
                    quantity=10,
                )
            ],
            as_of_date=dt.date(2026, 5, 3),
            filename="barclays-2.xls",
            file_sha256="barclays-2",
        )

        after_hl = await compare_import_batches(
            session,
            from_batch_id=batch1.id,
            to_batch_id=batch2.id,
        )
        after_barclays_update = await compare_import_batches(
            session,
            from_batch_id=batch2.id,
            to_batch_id=batch3.id,
        )
        after_barclays_update_filtered = await compare_import_batches(
            session,
            from_batch_id=batch2.id,
            to_batch_id=batch3.id,
            account_name="Barclays ISA",
        )

    await engine.dispose()
    return {
        "after_hl": after_hl,
        "after_barclays_update": after_barclays_update,
        "after_barclays_update_filtered": after_barclays_update_filtered,
    }


def test_snapshot_diff_carries_forward_other_accounts() -> None:
    result = asyncio.run(_compare_multi_account_snapshots())

    rows = {row["identifier"]: row for row in result["after_hl"]["rows"]}
    assert rows["VWRL"]["status"] == "unchanged"
    assert rows["VWRL"]["value_from_gbp"] == 1000
    assert rows["VWRL"]["value_to_gbp"] == 1000
    assert rows["EQQQ"]["status"] == "new"
    assert rows["EQQQ"]["value_from_gbp"] is None
    assert rows["EQQQ"]["value_to_gbp"] == 2000

    rows = {row["identifier"]: row for row in result["after_barclays_update"]["rows"]}
    assert rows["EQQQ"]["status"] == "unchanged"
    assert rows["EQQQ"]["value_from_gbp"] == 2000
    assert rows["EQQQ"]["value_to_gbp"] == 2000
    assert rows["VWRL"]["status"] == "changed"
    assert rows["VWRL"]["delta_value_gbp"] == 200

    rows = result["after_barclays_update_filtered"]["rows"]
    assert [row["identifier"] for row in rows] == ["VWRL"]
    assert rows[0]["weight_from_pct"] == 100
    assert rows[0]["weight_to_pct"] == 100
