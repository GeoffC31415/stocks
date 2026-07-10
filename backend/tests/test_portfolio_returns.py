import asyncio
import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.models import Base, HoldingSnapshot, ImportBatch, Instrument, Order, OrderImportBatch
from app.services.portfolio_service import get_portfolio_return_summary


async def _calculate(
    snapshots: list[tuple[str, dt.date, float | None]],
    orders: list[tuple[str, dt.date, str, float, bool]] | None = None,
    *,
    account_name: str | None = None,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
) -> dict:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        instruments: dict[str, Instrument] = {}
        for index, account in enumerate(sorted({row[0] for row in snapshots}), start=1):
            instrument = Instrument(
                account_name=account,
                identifier=f"asset-{index}",
                security_name=f"{account} asset",
                is_cash=False,
            )
            session.add(instrument)
            instruments[account] = instrument
        await session.flush()

        for index, (account, as_of_date, value) in enumerate(snapshots, start=1):
            batch = ImportBatch(
                as_of_date=as_of_date,
                file_sha256=f"snapshot-{index}",
                filename=f"snapshot-{index}.csv",
            )
            session.add(batch)
            await session.flush()
            session.add(
                HoldingSnapshot(
                    import_batch_id=batch.id,
                    instrument_id=instruments[account].id,
                    investment_label=f"{account} asset",
                    value_gbp=value,
                )
            )

        if orders:
            order_batch = OrderImportBatch(file_sha256="orders", filename="orders.csv", row_count=len(orders))
            session.add(order_batch)
            await session.flush()
            for index, (account, order_date, side, amount, is_drip) in enumerate(orders, start=1):
                session.add(
                    Order(
                        order_import_batch_id=order_batch.id,
                        security_name=f"{account} asset",
                        order_date=dt.datetime.combine(order_date, dt.time(), tzinfo=dt.UTC),
                        order_status="Completed",
                        account_name=account,
                        side=side,
                        quantity=1,
                        cost_proceeds_gbp=amount,
                        is_drip=is_drip,
                        order_fingerprint=f"order-{index}",
                    )
                )
        await session.commit()
        result = await get_portfolio_return_summary(
            session,
            account_name=account_name,
            from_date=from_date,
            to_date=to_date,
        )

    await engine.dispose()
    return result


def calculate(*args, **kwargs) -> dict:
    return asyncio.run(_calculate(*args, **kwargs))


def test_portfolio_return_endpoint_is_registered_with_response_schema() -> None:
    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/portfolio/returns")

    assert route.methods == {"GET"}
    assert route.response_model.__name__ == "PortfolioReturnSummary"


def test_portfolio_return_is_unavailable_without_snapshots() -> None:
    result = calculate([])

    assert result["period_start"] is None
    assert result["period_end"] is None
    assert result["modified_dietz_return_pct"] is None
    assert result["annualised_return_pct"] is None
    assert any("No portfolio snapshots" in note for note in result["notes"])


def test_portfolio_return_uses_boundary_values_without_cashflows() -> None:
    result = calculate(
        [("ISA", dt.date(2025, 1, 1), 1000), ("ISA", dt.date(2025, 12, 31), 1100)]
    )

    assert result["period_start"] == dt.date(2025, 1, 1)
    assert result["period_end"] == dt.date(2025, 12, 31)
    assert result["start_value_gbp"] == 1000
    assert result["end_value_gbp"] == 1100
    assert result["contributions_gbp"] == 0
    assert result["withdrawals_gbp"] == 0
    assert result["net_external_flow_gbp"] == 0
    assert result["absolute_gain_after_flows_gbp"] == 100
    assert result["modified_dietz_return_pct"] == pytest.approx(10)


def test_portfolio_return_weights_multiple_dated_contributions() -> None:
    result = calculate(
        [("ISA", dt.date(2025, 1, 1), 1000), ("ISA", dt.date(2025, 1, 11), 1800)],
        [
            ("ISA", dt.date(2025, 1, 3), "Buy", 300, False),
            ("ISA", dt.date(2025, 1, 9), "Buy", 200, False),
        ],
    )

    # Gain = 1800 - 1000 - 500 = 300; denominator = 1000 + 300*0.8 + 200*0.2.
    assert result["contributions_gbp"] == 500
    assert result["absolute_gain_after_flows_gbp"] == 300
    assert result["modified_dietz_return_pct"] == pytest.approx(300 / 1280 * 100)


def test_portfolio_return_excludes_drip_as_internal_cashflow() -> None:
    result = calculate(
        [("ISA", dt.date(2025, 1, 1), 1000), ("ISA", dt.date(2025, 2, 1), 1100)],
        [("ISA", dt.date(2025, 1, 15), "Buy", 50, True)],
    )

    assert result["contributions_gbp"] == 0
    assert result["net_external_flow_gbp"] == 0
    assert result["modified_dietz_return_pct"] == pytest.approx(10)
    assert any("DRIP" in note and "internal" in note for note in result["notes"])


def test_portfolio_return_treats_sale_proceeds_as_withdrawals() -> None:
    result = calculate(
        [("ISA", dt.date(2025, 1, 1), 1000), ("ISA", dt.date(2025, 1, 11), 900)],
        [("ISA", dt.date(2025, 1, 6), "Sell", 200, False)],
    )

    assert result["withdrawals_gbp"] == 200
    assert result["net_external_flow_gbp"] == -200
    assert result["absolute_gain_after_flows_gbp"] == 100
    assert result["modified_dietz_return_pct"] == pytest.approx(100 / 900 * 100)
    assert any("sale proceeds" in note and "withdrawals" in note for note in result["notes"])


def test_portfolio_return_is_unavailable_for_invalid_dietz_denominator() -> None:
    result = calculate(
        [("ISA", dt.date(2025, 1, 1), 100), ("ISA", dt.date(2025, 1, 11), 50)],
        [("ISA", dt.date(2025, 1, 6), "Sell", 200, False)],
    )

    assert result["absolute_gain_after_flows_gbp"] == 150
    assert result["modified_dietz_return_pct"] is None
    assert result["annualised_return_pct"] is None
    assert any("denominator" in note for note in result["notes"])


def test_portfolio_return_annualises_a_period_of_at_least_one_year() -> None:
    result = calculate(
        [("ISA", dt.date(2024, 1, 1), 100), ("ISA", dt.date(2025, 12, 31), 121)]
    )

    assert result["modified_dietz_return_pct"] == pytest.approx(21)
    assert result["annualised_return_pct"] == pytest.approx(10, abs=0.02)


def test_portfolio_return_filters_snapshots_and_orders_to_one_account() -> None:
    result = calculate(
        [
            ("ISA", dt.date(2025, 1, 1), 1000),
            ("SIPP", dt.date(2025, 1, 2), 5000),
            ("ISA", dt.date(2025, 1, 11), 1200),
            ("SIPP", dt.date(2025, 1, 12), 9000),
        ],
        [
            ("ISA", dt.date(2025, 1, 6), "Buy", 100, False),
            ("SIPP", dt.date(2025, 1, 7), "Buy", 2000, False),
        ],
        account_name="ISA",
    )

    assert result["period_start"] == dt.date(2025, 1, 1)
    assert result["period_end"] == dt.date(2025, 1, 11)
    assert result["start_value_gbp"] == 1000
    assert result["end_value_gbp"] == 1200
    assert result["contributions_gbp"] == 100
    assert result["modified_dietz_return_pct"] == pytest.approx(100 / 1050 * 100)
