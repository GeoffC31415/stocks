import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import (
    Base,
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    InstrumentGroup,
    InstrumentGroupMember,
)
from app.services.performance_service import build_value_series, get_portfolio_performance
from app.services.portfolio_service import (
    build_portfolio_summary,
    get_current_snapshots,
    get_latest_batch,
    get_latest_batch_for_account,
    portfolio_value_timeseries,
    snapshot_metrics,
)


def _snapshot(
    *,
    instrument_id: int,
    quantity: float,
    last_price: float | None,
    value_gbp: float,
) -> HoldingSnapshot:
    return HoldingSnapshot(
        import_batch_id=1,
        instrument_id=instrument_id,
        investment_label="Example",
        quantity=quantity,
        last_price=last_price,
        value_gbp=value_gbp,
    )


def test_snapshot_metrics_uses_price_drawdown_before_value_drawdown() -> None:
    metrics = snapshot_metrics(
        {
            1: [
                _snapshot(instrument_id=1, quantity=10, last_price=100, value_gbp=1000),
                _snapshot(instrument_id=1, quantity=12, last_price=80, value_gbp=960),
            ]
        }
    )

    assert metrics[1]["peak_value_gbp"] == 1000
    assert metrics[1]["peak_last_price"] == 100
    assert metrics[1]["drawdown_from_peak_pct"] == -20
    assert metrics[1]["quantity_unchanged_snapshot_count"] == 1


def test_snapshot_metrics_counts_consecutive_unchanged_latest_quantity() -> None:
    metrics = snapshot_metrics(
        {
            1: [
                _snapshot(instrument_id=1, quantity=8, last_price=None, value_gbp=800),
                _snapshot(instrument_id=1, quantity=10, last_price=None, value_gbp=900),
                _snapshot(instrument_id=1, quantity=10, last_price=None, value_gbp=850),
                _snapshot(instrument_id=1, quantity=10, last_price=None, value_gbp=800),
            ]
        }
    )

    assert metrics[1]["drawdown_from_peak_pct"] == -100 / 900 * 100
    assert metrics[1]["quantity_unchanged_snapshot_count"] == 3


@pytest.fixture
async def valuation_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add_all([
            Instrument(id=1, account_name="ISA", identifier="A", security_name="Asset A"),
            Instrument(id=2, account_name="SIPP", identifier="B", security_name="Asset B"),
            Instrument(id=3, account_name="ISA", identifier="C", security_name="Closed asset"),
        ])
        await session.flush()
        yield session
    await engine.dispose()


async def test_scoped_summary_reconciles_cash_cost_pnl_and_group_denominator(valuation_db):
    valuation_db.add(Instrument(id=4, account_name="ISA", identifier="CASH", security_name="Cash", is_cash=True))
    valuation_db.add(InstrumentGroup(id=1, name="Core", target_allocation_pct=50))
    await valuation_db.flush()
    valuation_db.add_all([InstrumentGroupMember(group_id=1, instrument_id=i) for i in (1, 2, 4)])
    await add_valuation(valuation_db, 1, 10, {1: 120, 4: 30})
    await add_valuation(valuation_db, 2, 5, {2: 200})
    await add_valuation(valuation_db, 3, 1, {1: 50})  # Later historical import cannot win.
    snapshots = await get_current_snapshots(valuation_db)
    for snapshot in snapshots:
        snapshot.book_cost_gbp = 100 if snapshot.instrument_id == 1 else 180 if snapshot.instrument_id == 2 else 0
    await valuation_db.flush()
    combined = await build_portfolio_summary(valuation_db)
    isa = await build_portfolio_summary(valuation_db, account_name="ISA")
    sipp = await build_portfolio_summary(valuation_db, account_name="SIPP")
    for field in ("total_value_gbp", "invested_value_gbp", "cash_value_gbp", "total_book_cost_gbp", "total_pnl_gbp"):
        assert combined[field] == pytest.approx(isa[field] + sipp[field])
    assert isa["total_value_gbp"] == 150
    assert isa["invested_value_gbp"] == 120
    assert isa["cash_value_gbp"] == 30
    assert isa["total_pnl_gbp"] == 20  # Cash is not an investment gain.
    assert isa["group_allocation"][0]["value_gbp"] == 120
    assert isa["group_allocation"][0]["weight_pct"] == 100
    assert isa["group_allocation"][0]["member_ids"] == [1]
    assert sipp["as_of_date"] == dt.date(2026, 1, 5)
    assert sipp["scope"]["valuation_dates"] == [{"account_name": "SIPP", "date": dt.date(2026, 1, 5)}]
    assert combined["scope"]["warnings"]
    assert isa["position_count"] == 2
    empty = await build_portfolio_summary(valuation_db, account_name="Empty")
    assert empty["position_count"] == 0
    assert empty["scope"]["account_name"] == "Empty"


async def test_performance_episodes_use_the_same_valid_index_and_maximum_depth(valuation_db):
    await add_valuation(valuation_db, 1, 1, {1: 100})
    await add_valuation(valuation_db, 2, 5, {1: 120})
    await add_valuation(valuation_db, 3, 10, {1: 90})
    performance = await get_portfolio_performance(valuation_db, account_name="ISA")
    episodes = performance.get("drawdown_episodes")
    assert episodes
    assert min(episode["depth_pct"] for episode in episodes) == performance["max_drawdown_pct"]
    assert episodes[0]["peak_date"] == dt.date(2026, 1, 5)
    assert episodes[0]["recovery_date"] is None


async def add_valuation(session, batch_id, day, values):
    session.add(ImportBatch(id=batch_id, as_of_date=dt.date(2026, 1, day), file_sha256=str(batch_id)))
    for instrument_id, value in values.items():
        session.add(HoldingSnapshot(import_batch_id=batch_id, instrument_id=instrument_id,
                                    investment_label="Asset", value_gbp=value))
    await session.flush()


@pytest.mark.asyncio
async def test_same_date_accounts_and_corrections_emit_one_complete_daily_state(valuation_db):
    await add_valuation(valuation_db, 1, 1, {1: 100})
    await add_valuation(valuation_db, 2, 1, {2: 200})
    await add_valuation(valuation_db, 3, 1, {1: 110})
    await add_valuation(valuation_db, 4, 10, {1: 121})
    await add_valuation(valuation_db, 5, 10, {2: 220})
    points, coverage = await build_value_series(valuation_db)
    assert [(p["as_of_date"].day, p["value_gbp"]) for p in points] == [(1, 310), (10, 341)]
    assert coverage == dt.date(2026, 1, 1)
    raw = await portfolio_value_timeseries(valuation_db)
    assert [p["total_value_gbp"] for p in raw] == [310, 341]
    perf = await get_portfolio_performance(valuation_db)
    assert perf["flow_adjusted"]["total_return_pct"] == pytest.approx(10)
    assert perf["flow_adjusted_curve"][-1]["index"] == pytest.approx(110)


@pytest.mark.asyncio
async def test_historical_import_cannot_move_current_account_value_backwards(valuation_db):
    await add_valuation(valuation_db, 1, 10, {1: 110})
    await add_valuation(valuation_db, 2, 10, {2: 220})
    await add_valuation(valuation_db, 3, 1, {1: 100, 3: 50})
    current = await get_current_snapshots(valuation_db)
    assert {p.instrument_id: p.value_gbp for p in current} == {1: 110, 2: 220}
    assert (await get_latest_batch(valuation_db)).id == 2
    assert (await get_latest_batch_for_account(valuation_db, "ISA")).id == 1


@pytest.mark.asyncio
async def test_account_boundaries_do_not_become_returns_or_extra_observations(valuation_db):
    await add_valuation(valuation_db, 1, 1, {1: 100})
    await add_valuation(valuation_db, 2, 5, {2: 200})
    await add_valuation(valuation_db, 3, 10, {1: 110})
    perf = await get_portfolio_performance(valuation_db)
    assert perf["period_start"] == dt.date(2026, 1, 5)
    assert perf["start_value_gbp"] == 300
    assert perf["flow_adjusted"]["total_return_pct"] == pytest.approx(100 / 30, abs=.0001)
    points, _ = await build_value_series(valuation_db, account_name="ISA")
    assert [p["as_of_date"].day for p in points] == [1, 10]
    assert perf["scope"]["valuation_dates"] == [
        {"account_name": "ISA", "date": dt.date(2026, 1, 10)},
        {"account_name": "SIPP", "date": dt.date(2026, 1, 5)},
    ]
    assert perf["scope"]["warnings"]


@pytest.mark.asyncio
@pytest.mark.parametrize("values", [[100, None, 110], [0, 100, 90]])
async def test_invalid_snapshot_chain_has_null_drawdown_and_finite_json(valuation_db, values):
    from app.schemas import PerformanceSummary

    for batch_id, value in enumerate(values, 1):
        await add_valuation(valuation_db, batch_id, batch_id, {1: value})
    perf = await get_portfolio_performance(valuation_db, account_name="ISA")
    assert perf["flow_adjusted_curve"] == []
    assert perf["max_drawdown_pct"] is None
    assert perf["metrics"]["total_return_pct"]["status"] == "unavailable"
    assert perf["metrics"]["total_return_pct"]["reasons"][0]["code"] == "invalid_return_chain"
    serialized = PerformanceSummary.model_validate(perf).model_dump_json()
    assert "NaN" not in serialized and "Infinity" not in serialized


@pytest.mark.asyncio
async def test_annualisation_unavailable_does_not_hide_valid_cumulative_return(valuation_db):
    await add_valuation(valuation_db, 1, 1, {1: 100})
    await add_valuation(valuation_db, 2, 10, {1: 110})
    perf = await get_portfolio_performance(valuation_db)
    assert perf["metrics"]["total_return_pct"]["status"] == "available"
    annualised = perf["metrics"]["annualised_return_pct"]
    assert annualised["value"] is None
    assert annualised["reasons"][0]["code"] == "short_annualisation_window"
    assert perf["metrics"]["annualised_volatility_pct"]["reasons"][0]["code"] == "insufficient_intervals"

