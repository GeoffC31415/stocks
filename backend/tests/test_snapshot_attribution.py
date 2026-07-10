import asyncio
import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.models import Base, HoldingSnapshot, ImportBatch, Instrument, Order, OrderImportBatch
from app.services.attribution_service import get_snapshot_attribution


async def _calculate(
    snapshots: list[tuple[str, str, str, dt.date, float | None]],
    orders: list[tuple[str, str | None, dt.date, str, float | None, bool]] | None = None,
    *,
    account_name: str | None = None,
    from_batch_id: int | None = None,
    to_batch_id: int | None = None,
) -> dict:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        instruments: dict[tuple[str, str], Instrument] = {}
        batches: dict[dt.date, ImportBatch] = {}
        for account, identifier, name, as_of_date, _ in snapshots:
            key = (account, identifier)
            if key not in instruments:
                instrument = Instrument(
                    account_name=account,
                    identifier=identifier,
                    security_name=name,
                    is_cash=False,
                )
                session.add(instrument)
                instruments[key] = instrument
            if as_of_date not in batches:
                batch = ImportBatch(
                    as_of_date=as_of_date,
                    file_sha256=f"snapshot-{len(batches) + 1}",
                    filename=f"snapshot-{len(batches) + 1}.csv",
                )
                session.add(batch)
                batches[as_of_date] = batch
        await session.flush()

        for account, identifier, name, as_of_date, value in snapshots:
            session.add(
                HoldingSnapshot(
                    import_batch_id=batches[as_of_date].id,
                    instrument_id=instruments[(account, identifier)].id,
                    investment_label=name,
                    value_gbp=value,
                )
            )

        if orders is not None:
            order_batch = OrderImportBatch(
                file_sha256="orders",
                filename="orders.csv",
                row_count=len(orders),
            )
            session.add(order_batch)
            await session.flush()
            for index, (account, identifier, order_date, side, amount, is_drip) in enumerate(
                orders, start=1
            ):
                instrument = instruments.get((account, identifier)) if identifier else None
                session.add(
                    Order(
                        order_import_batch_id=order_batch.id,
                        instrument_id=instrument.id if instrument else None,
                        security_name=instrument.security_name if instrument else "Unlinked asset",
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
        ordered_batches = sorted(batches.values(), key=lambda batch: batch.id)
        result = await get_snapshot_attribution(
            session,
            account_name=account_name,
            from_batch_id=from_batch_id,
            to_batch_id=to_batch_id,
        )
        result["test_batch_ids"] = [batch.id for batch in ordered_batches]

    await engine.dispose()
    return result


def calculate(*args, **kwargs) -> dict:
    return asyncio.run(_calculate(*args, **kwargs))


def test_snapshot_attribution_reconciles_flows_drip_and_market_movement_exactly() -> None:
    result = calculate(
        [
            ("ISA", "AAA", "Alpha", dt.date(2025, 1, 1), 600),
            ("ISA", "BBB", "Beta", dt.date(2025, 1, 1), 400),
            ("ISA", "AAA", "Alpha", dt.date(2025, 2, 1), 850),
            ("ISA", "BBB", "Beta", dt.date(2025, 2, 1), 450),
        ],
        [
            ("ISA", "AAA", dt.date(2025, 1, 10), "Buy", 100, False),
            ("ISA", "BBB", dt.date(2025, 1, 15), "Sell", 50, False),
            ("ISA", "AAA", dt.date(2025, 1, 20), "Buy", 20, True),
        ],
    )

    assert result["opening_value_gbp"] == 1000
    assert result["closing_value_gbp"] == 1300
    assert result["raw_value_change_gbp"] == 300
    assert result["contributions_gbp"] == 100
    assert result["withdrawals_gbp"] == 50
    assert result["drip_proxy_gbp"] == 20
    assert result["net_external_flow_gbp"] == 50
    assert result["residual_market_movement_gbp"] == 230
    assert result["reconciliation_difference_gbp"] == pytest.approx(0, abs=1e-9)
    assert result["from_batch"]["id"] == result["test_batch_ids"][0]
    assert result["to_batch"]["id"] == result["test_batch_ids"][1]
    assert result["top_contributors"][0]["identifier"] == "AAA"
    assert result["top_contributors"][0]["estimated_market_movement_gbp"] == 130
    assert any("internal" in note and "DRIP" in note for note in result["notes"])
    assert any("withdrawals" in note and "Sales" in note for note in result["notes"])
    assert any("estimate" in note for note in result["notes"])


def test_snapshot_attribution_endpoint_is_registered_with_response_schema() -> None:
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/portfolio/attribution"
    )

    assert route.methods == {"GET"}
    assert route.response_model.__name__ == "SnapshotAttributionResponse"


def test_snapshot_attribution_returns_nulls_and_note_without_previous_snapshot() -> None:
    result = calculate(
        [("ISA", "AAA", "Alpha", dt.date(2025, 1, 1), 1000)],
        [],
        account_name="ISA",
    )

    assert result["from_batch"] is None
    assert result["to_batch"]["id"] == result["test_batch_ids"][0]
    assert result["opening_value_gbp"] is None
    assert result["residual_market_movement_gbp"] is None
    assert any("No previous snapshot" in note for note in result["notes"])


def test_snapshot_attribution_does_not_invent_flows_without_order_history() -> None:
    result = calculate(
        [
            ("ISA", "AAA", "Alpha", dt.date(2025, 1, 1), 1000),
            ("ISA", "AAA", "Alpha", dt.date(2025, 2, 1), 1100),
        ]
    )

    assert result["opening_value_gbp"] == 1000
    assert result["closing_value_gbp"] == 1100
    assert result["raw_value_change_gbp"] == 100
    assert result["contributions_gbp"] is None
    assert result["withdrawals_gbp"] is None
    assert result["drip_proxy_gbp"] is None
    assert result["net_external_flow_gbp"] is None
    assert result["residual_market_movement_gbp"] is None
    assert result["reconciliation_difference_gbp"] is None
    assert any("No imported order history" in note for note in result["notes"])


def test_snapshot_attribution_isolates_boundaries_flows_and_movements_by_account() -> None:
    result = calculate(
        [
            ("ISA", "AAA", "Alpha", dt.date(2025, 1, 1), 1000),
            ("SIPP", "ZZZ", "Zeta", dt.date(2025, 1, 5), 5000),
            ("ISA", "AAA", "Alpha", dt.date(2025, 2, 1), 1200),
            ("SIPP", "ZZZ", "Zeta", dt.date(2025, 2, 5), 9000),
        ],
        [
            ("ISA", "AAA", dt.date(2025, 1, 10), "Buy", 100, False),
            ("SIPP", "ZZZ", dt.date(2025, 1, 20), "Buy", 2000, False),
        ],
        account_name="ISA",
    )

    assert result["from_batch"]["as_of_date"] == dt.date(2025, 1, 1)
    assert result["to_batch"]["as_of_date"] == dt.date(2025, 2, 1)
    assert result["opening_value_gbp"] == 1000
    assert result["closing_value_gbp"] == 1200
    assert result["contributions_gbp"] == 100
    assert result["net_external_flow_gbp"] == 100
    assert result["residual_market_movement_gbp"] == 100
    assert [row["account_name"] for row in result["top_contributors"]] == ["ISA"]
