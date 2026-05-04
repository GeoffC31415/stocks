import asyncio
import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Instrument
from app.services.barclays_parser import ParsedHoldingRow
from app.services.import_service import import_holding_snapshot
from app.services.hl_parser import HL_ACCOUNT_NAME
from app.services.portfolio_service import portfolio_value_timeseries


def _holding(
    *,
    account_name: str,
    identifier: str,
    investment: str,
    value_gbp: float,
) -> ParsedHoldingRow:
    return ParsedHoldingRow(
        account_name=account_name,
        investment=investment,
        identifier=identifier,
        quantity=1,
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
