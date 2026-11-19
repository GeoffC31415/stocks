"""Synthetic worker timing through real HTTP mapping, persistence and returns."""

import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from test_trading212_worker_history import Broker

from app.models import (
    AccountAlias,
    CashFlowCoverage,
    HoldingSnapshot,
    ImportBatch,
    Instrument,
)
from app.routers import trading212 as router
from app.schemas import PerformanceSummary
from app.services.attribution_service import get_snapshot_attribution
from app.services.performance_service import get_portfolio_performance
from app.services.portfolio_service import get_portfolio_return_summary
from app.services.trading212 import sync_portfolio_snapshot


@pytest.fixture
async def db():
    from sqlite_schema import create_file_schema

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await create_file_schema(engine)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False), engine
    finally:
        await engine.dispose()


@pytest.mark.parametrize("worker", [False, True], ids=["direct-control", "worker"])
async def test_changed_valuation_has_covered_flow_adjusted_gain(db, worker):
    sessions, _ = db
    broker = Broker()
    account = router.settings.trading212_account_name
    yesterday = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=1)
    async with sessions() as session:
        await sync_portfolio_snapshot(
            session, broker.client, account_name=account, observation_date=yesterday
        )
    broker.pages["positions"][0]["walletImpact"]["currentValue"] += 10
    refresh = router.run_trading212_worker_sync if worker else router.run_trading212_sync
    async with sessions() as session:
        assert (await refresh(session, broker.client)).snapshot == "imported"
    async with sessions() as check:
        returns = await get_portfolio_return_summary(check, account_name=account)
        if worker:
            batch = await check.scalar(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
            coverage = await check.get(CashFlowCoverage, account)
            assert coverage.fetched_at.replace(tzinfo=dt.UTC) <= broker.arrived_at["transactions"]
            assert coverage.fetched_at < batch.created_at
        assert returns["absolute_gain_after_flows_gbp"] == 10, returns["notes"]
        assert returns["modified_dietz_return_pct"] == pytest.approx(100 * 10 / 13)


START = dt.datetime(2020, 2, 2, 10, tzinfo=dt.UTC)
MINUTE = dt.timedelta(minutes=1)
KEY = "trading212_valuation_observation_v1"


@pytest.fixture
def timed_broker(monkeypatch):
    # Move only the network-observation clock. Creation/commit use actual time.
    class TimedBroker(Broker):
        now = START

        def respond(self, request):
            response = super().respond(request)
            self.now += MINUTE
            return response

    broker = TimedBroker()
    monkeypatch.setattr(
        router,
        "dt",
        SimpleNamespace(
            datetime=SimpleNamespace(now=lambda tz: broker.now),
            UTC=dt.UTC,
        ),
    )
    return broker


async def other_cash_snapshot(session, day, value: float | None = 100):
    cash = await session.scalar(select(Instrument).where(Instrument.account_name == "Other"))
    if cash is None:
        cash = Instrument(
            account_name="Other", identifier="CASH", security_name="Cash", is_cash=True
        )
        session.add(cash)
    batch = ImportBatch(as_of_date=day, filename="other.csv", file_sha256=f"other-{day}")
    session.add(batch)
    await session.flush()
    session.add(
        HoldingSnapshot(
            import_batch_id=batch.id,
            instrument_id=cash.id,
            investment_label="Cash",
            value_gbp=value,
        )
    )
    await session.commit()


def deposit(broker, when, amount):
    broker.pages["transactions"]["items"].append(
        {
            "type": "DEPOSIT",
            "reference": f"funding-{when.isoformat()}",
            "currency": "GBP",
            "amount": amount,
            "dateTime": when.isoformat(),
        }
    )


async def cash_valuation(session, broker, when, balance):
    broker.now = when
    broker.pages["positions"] = []
    broker.pages["summary"]["cash"]["availableToTrade"] = balance
    result = await router.run_trading212_worker_sync(session, broker.client)
    assert isinstance(result, router.Trading212SyncResult) and result.snapshot == "imported"


@pytest.mark.parametrize(
    "lead,second_deposit",
    [
        (MINUTE, START + dt.timedelta(days=1) - MINUTE),
        (dt.timedelta(days=1), START + 3 * MINUTE),
    ],
    ids=["join-day", "prior-day"],
)
async def test_aliased_late_join_counts_first_value_once(db, timed_broker, lead, second_deposit):
    sessions, _ = db
    b = timed_broker

    deposit(b, START - lead, 10)
    async with sessions() as s:
        s.add(
            AccountAlias(
                source="test",
                source_account_name=router.settings.trading212_account_name,
                canonical_account_name="Alias",
            )
        )
        await other_cash_snapshot(s, (START - lead).date() - dt.timedelta(days=1))
        await cash_valuation(s, b, START, 10)
        result = await get_portfolio_return_summary(s)
        assert (result["net_external_flow_gbp"], result["absolute_gain_after_flows_gbp"]) == (10, 0)
        curve = (await get_portfolio_performance(s))["flow_adjusted"]
        assert (curve["net_external_flow_gbp"], curve["total_return_pct"]) == (10, 0)

        # Once the join is intermediate, only the first deposit is in its baseline.
        later = START + dt.timedelta(days=1)
        deposit(b, second_deposit, 7)
        await cash_valuation(s, b, later, 17)
        result = await get_portfolio_return_summary(s)
        assert (result["net_external_flow_gbp"], result["absolute_gain_after_flows_gbp"]) == (17, 0)
        curve = (await get_portfolio_performance(s))["flow_adjusted"]
        assert (curve["net_external_flow_gbp"], curve["total_return_pct"]) == (17, 0)
        assert (START.date() in {p["date"] for p in curve["flow_adjusted_curve"]}) == (
            second_deposit.date() != START.date()
        )


async def test_late_join_does_not_hide_cash_during_valuation(db, timed_broker):
    sessions, _ = db
    async with sessions() as s:
        await other_cash_snapshot(s, START.date() - dt.timedelta(days=1))
        deposit(timed_broker, START + MINUTE, 10)
        await cash_valuation(s, timed_broker, START, 10)
        result = await get_portfolio_return_summary(s)
        assert result["net_external_flow_gbp"] is None
        assert any("during separate" in note for note in result["notes"])


@pytest.mark.parametrize(
    "funding_day,mid_day,end_day",
    [(1, 1, 2), (1, 2, 3), (2, 1, 3)],
    ids=["at-carried-point", "before-point", "after-point"],
)
async def test_aggregate_funding_across_carried_point(
    db, timed_broker, funding_day, mid_day, end_day
):
    sessions, _ = db
    day = dt.timedelta(days=1)
    mid = START + mid_day * day
    async with sessions() as s:
        await other_cash_snapshot(s, START.date())
        await cash_valuation(s, timed_broker, START, 100)
        await other_cash_snapshot(s, mid.date())
        deposit(timed_broker, START + funding_day * day, 50)
        await cash_valuation(s, timed_broker, START + end_day * day, 150)

        result = await get_portfolio_return_summary(s)
        assert (result["net_external_flow_gbp"], result["absolute_gain_after_flows_gbp"]) == (50, 0)
        performance = await get_portfolio_performance(s)
        assert [p["value_gbp"] for p in performance["growth_curve"]] == [200, 200, 250]
        block = performance["flow_adjusted"]
        assert (block["net_external_flow_gbp"], block["total_return_pct"]) == (50, 0)
        assert block["max_drawdown_pct"] == 0
        dates = [START.date(), (START + end_day * day).date()]
        if funding_day > mid_day:
            dates.insert(1, mid.date())
        assert [p["date"] for p in block["flow_adjusted_curve"]] == dates
        if funding_day <= mid_day:
            assert any("not yet reflected" in note for note in block["notes"])

        # This window *opens* on the other account's date, with the prior
        # Trading 212 valuation carried in. It is not a new scope baseline.
        segment = await get_portfolio_return_summary(s, from_date=mid.date())
        if funding_day <= mid_day:
            assert segment["absolute_gain_after_flows_gbp"] is None
            assert any("carried into the opening" in note for note in segment["notes"])
        else:
            assert (segment["net_external_flow_gbp"], segment["absolute_gain_after_flows_gbp"]) == (
                50,
                0,
            )


@pytest.mark.parametrize("aggregate", [False, True], ids=["account", "all-accounts"])
@pytest.mark.parametrize("legacy", [False, True], ids=["worker-cutoff", "legacy-cutoff"])
async def test_curve_bridges_intraday_cash_and_keeps_actual_funding_date(
    db, timed_broker, aggregate, legacy
):
    sessions, _ = db
    b = timed_broker
    middle = START + dt.timedelta(days=1)
    end = START + dt.timedelta(days=2)
    other_value = 100 if aggregate else 0
    async with sessions() as s:
        if aggregate:
            await other_cash_snapshot(s, START.date())
        await cash_valuation(s, b, START, 100)
        # A changed balance makes the middle valuation observable even without
        # another account. Its small increase is from performance, not funding.
        await cash_valuation(s, b, middle, 105)
        mid_batch = await s.scalar(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
        if legacy:
            # Reproduce a retained pre-worker snapshot: legacy API timing is
            # the same-date creation cutoff, not worker request metadata.
            middle_summary = dict(mid_batch.diff_summary)
            middle_summary.pop(KEY)
            mid_batch.diff_summary = middle_summary
            mid_batch.created_at = middle + 2 * MINUTE
            await s.commit()
        deposit(b, middle + 3 * MINUTE, 50)
        await cash_valuation(s, b, end, 170)
        account = None if aggregate else router.settings.trading212_account_name
        result = await get_portfolio_performance(s, account_name=account)
        opening = await get_portfolio_return_summary(
            s, account_name=account, from_date=middle.date()
        )
        closing = await get_portfolio_return_summary(s, account_name=account, to_date=middle.date())
        assert opening["modified_dietz_return_pct"] is None
        assert opening["net_external_flow_gbp"] is None
        assert (closing["absolute_gain_after_flows_gbp"], closing["net_external_flow_gbp"]) == (
            5,
            0,
        )
        if not aggregate:
            closing_change = await get_snapshot_attribution(
                s, account_name=account, to_batch_id=mid_batch.id
            )
            opening_change = await get_snapshot_attribution(
                s, account_name=account, from_batch_id=mid_batch.id
            )
            assert opening_change["residual_market_movement_gbp"] is None
            assert (
                closing_change["residual_market_movement_gbp"],
                closing_change["net_external_flow_gbp"],
            ) == (5, 0)

    assert [p["value_gbp"] for p in result["growth_curve"]] == [
        100 + other_value,
        105 + other_value,
        170 + other_value,
    ]
    block = result["flow_adjusted"]
    assert block["net_external_flow_gbp"] == 50
    # The deposit remains halfway through the bridged two-day interval, not
    # shifted to the end where it would get no time weight.
    expected = 100 * 20 / (100 + other_value + 25)
    assert block["total_return_pct"] == pytest.approx(expected)
    assert [p["date"] for p in result["flow_adjusted_curve"]] == [START.date(), end.date()]
    assert result["flow_adjusted_curve"][-1]["index"] == pytest.approx(100 + expected)
    assert result["metrics"]["total_return_pct"]["observations"] == 2
    wire = PerformanceSummary.model_validate(result).model_dump(mode="json")
    assert len(wire["growth_curve"]) == 3
    assert [p["date"] for p in wire["flow_adjusted_curve"]] == [
        START.date().isoformat(),
        end.date().isoformat(),
    ]
    assert wire["metrics"]["total_return_pct"]["observations"] == 2


async def test_cash_alignment_does_not_hide_missing_join_valuation(db, timed_broker):
    sessions, _ = db
    middle = START + dt.timedelta(days=1)
    end = START + dt.timedelta(days=2)
    async with sessions() as s:
        await cash_valuation(s, timed_broker, START, 100)
        await cash_valuation(s, timed_broker, middle, 105)
        await other_cash_snapshot(s, middle.date(), value=None)
        deposit(timed_broker, middle + 3 * MINUTE, 50)
        await cash_valuation(s, timed_broker, end, 170)
        await other_cash_snapshot(s, end.date())
        result = await get_portfolio_performance(s)

    assert [p["value_gbp"] for p in result["growth_curve"]] == [100, None, 270]
    assert result["flow_adjusted_curve"] == []
    assert result["metrics"]["total_return_pct"]["status"] == "unavailable"
    assert result["metrics"]["total_return_pct"]["observations"] == 0
    assert result["metrics"]["total_return_pct"]["reasons"][0]["code"] == "invalid_return_chain"


async def worker_pair(session, broker, *, transfer_at=None):
    account = router.settings.trading212_account_name
    await sync_portfolio_snapshot(
        session,
        broker.client,
        account_name=account,
        observation_date=START.date() - dt.timedelta(days=1),
    )
    broker.now = START
    broker.pages["summary"]["cash"]["availableToTrade"] += 10
    if transfer_at is not None:
        broker.pages["transactions"]["items"].append(
            {
                "type": "TRANSFER",
                "reference": "synthetic-transfer",
                "currency": "GBP",
                "amount": 10,
                "dateTime": transfer_at.isoformat(),
            }
        )
    result = await router.run_trading212_worker_sync(session, broker.client)
    assert isinstance(result, router.Trading212SyncResult) and result.snapshot == "imported"


@pytest.mark.parametrize(("minutes", "net"), [(-1, 10), (0, None), (1, None), (3, 0)])
async def test_transfer_relative_to_both_valuation_requests(db, timed_broker, minutes, net):
    sessions, _ = db
    account = router.settings.trading212_account_name
    async with sessions() as session:
        await worker_pair(session, timed_broker, transfer_at=START + minutes * MINUTE)
    async with sessions() as check:
        returns = await get_portfolio_return_summary(check, account_name=account)
        perf = await get_portfolio_performance(check, account_name=account)
        attribution = await get_snapshot_attribution(check, account_name=account)
        for result in (returns, perf["flow_adjusted"], attribution):
            assert result["net_external_flow_gbp"] == net
        assert returns["absolute_gain_after_flows_gbp"] == (None if net is None else 10 - net)


async def test_aliased_worker_valuation_uses_its_source_ledger_without_rekeying(db, timed_broker):
    sessions, _ = db
    source = router.settings.trading212_account_name
    canonical = "Synthetic canonical"
    async with sessions() as session:
        session.add(
            AccountAlias(
                source="test", source_account_name=source, canonical_account_name=canonical
            )
        )
        await session.commit()
        await worker_pair(session, timed_broker, transfer_at=START - MINUTE)
    async with sessions() as check:
        for scope in (canonical, None):
            result = await get_portfolio_return_summary(check, account_name=scope)
            assert result["net_external_flow_gbp"] == 10
            assert result["absolute_gain_after_flows_gbp"] == 0
        assert (await check.scalars(select(CashFlowCoverage.account_name))).all() == [source]
        # An independently covered canonical account is not proof that these
        # two ledgers are interchangeable.
        check.add(CashFlowCoverage(account_name=canonical, source="another", fetched_at=START))
        await check.commit()
        result = await get_portfolio_return_summary(check, account_name=canonical)
        assert result["absolute_gain_after_flows_gbp"] is None


@pytest.mark.parametrize("minutes", [1, 3], ids=["inside-requests", "after-intraday-point"])
async def test_overlap_stays_ambiguous_when_worker_valuation_is_used_as_open_or_curve_point(
    db, timed_broker, minutes
):
    sessions, _ = db
    account = router.settings.trading212_account_name
    async with sessions() as session:
        await worker_pair(session, timed_broker, transfer_at=START + minutes * MINUTE)
        timed_broker.now = START + dt.timedelta(days=1)
        timed_broker.pages["positions"][0]["walletImpact"]["currentValue"] += 1
        await router.run_trading212_worker_sync(session, timed_broker.client)
    async with sessions() as check:
        segment = await get_portfolio_return_summary(
            check, account_name=account, from_date=START.date()
        )
        assert segment["absolute_gain_after_flows_gbp"] is None
        curve = await get_portfolio_performance(check, account_name=account)
        if minutes == 1:
            assert curve["flow_adjusted"]["total_return_pct"] is None
            metric = curve["metrics"]["total_return_pct"]
            assert metric["observations"] == 0
            assert metric["reasons"][0]["code"] == "cash_flow_coverage"
            assert "during separate" in metric["reasons"][0]["message"]
        else:
            assert curve["flow_adjusted"]["net_external_flow_gbp"] == 10
            assert START.date() not in {p["date"] for p in curve["flow_adjusted_curve"]}
        attr = await get_snapshot_attribution(check, account_name=account)
        assert attr["residual_market_movement_gbp"] is None
        # The earliest and latest endpoints themselves are unambiguous.
        period = await get_portfolio_return_summary(check, account_name=account)
        assert period["absolute_gain_after_flows_gbp"] == 1


async def test_internal_trade_between_valuation_requests_cannot_be_reported_as_return(
    db, timed_broker
):
    sessions, _ = db
    timed_broker.add_history(1)
    timed_broker.pages["orders"]["items"][0]["fill"]["filledAt"] = (START + MINUTE).isoformat()
    async with sessions() as session:
        await worker_pair(session, timed_broker)
    async with sessions() as check:
        result = await get_portfolio_return_summary(
            check, account_name=router.settings.trading212_account_name
        )
        assert result["absolute_gain_after_flows_gbp"] is None


async def test_selected_correction_and_later_duplicate_preserve_original_cutoffs(db, timed_broker):
    sessions, _ = db
    account = router.settings.trading212_account_name
    async with sessions() as session:
        # Transfer just after the first window; its higher later balance is a
        # same-date correction. A subsequent duplicate is not a new valuation.
        await worker_pair(session, timed_broker, transfer_at=START + 3 * MINUTE)
        first = await session.scalar(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
        original = (first.created_at, first.diff_summary)
        assert set(first.diff_summary[KEY]) == {
            "positions_requested_at",
            "account_summary_received_at",
            "ledger_scope_sha256",
        }
        assert first.diff_summary[KEY]["positions_requested_at"] == START.isoformat()
        assert (
            first.diff_summary[KEY]["account_summary_received_at"]
            == (START + 2 * MINUTE).isoformat()
        )
        timed_broker.pages["summary"]["cash"]["availableToTrade"] += 10
        await router.run_trading212_worker_sync(session, timed_broker.client)
        second = await session.scalar(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
        later = (second.created_at, second.diff_summary)
        timed_broker.now += dt.timedelta(days=1)
        repeated = await router.run_trading212_worker_sync(session, timed_broker.client)
        assert (
            isinstance(repeated, router.Trading212SyncResult) and repeated.snapshot == "unchanged"
        )
        assert repeated.valuation_at == START.date()
    async with sessions() as check:
        assert [
            (b.created_at, b.diff_summary)
            for b in (await check.scalars(select(ImportBatch).order_by(ImportBatch.id))).all()
        ][1:] == [original, later]
        selected = await get_snapshot_attribution(check, account_name=account, to_batch_id=first.id)
        latest = await get_snapshot_attribution(check, account_name=account)
        assert selected["net_external_flow_gbp"] == 0 and latest["net_external_flow_gbp"] == 10
        assert (
            selected["residual_market_movement_gbp"] == latest["residual_market_movement_gbp"] == 10
        )


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "naive",
        "reversed",
        "wrong-day",
        "cross-midnight",
        "after-creation",
        "wrong-scope",
        "stale",
        "legacy-api",
        "file",
    ],
)
async def test_unusable_evidence_never_weakens_coverage_or_other_broker_cutoffs(
    db, timed_broker, defect
):
    sessions, _ = db
    account = router.settings.trading212_account_name
    async with sessions() as session:
        await worker_pair(session, timed_broker)
        batch = await session.scalar(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
        meta = dict(batch.diff_summary[KEY])
        end = "account_summary_received_at"
        if defect == "missing":
            meta.pop(end)
        elif defect == "naive":
            meta[end] = START.replace(tzinfo=None).isoformat()
        elif defect == "reversed":
            meta[end] = (START - MINUTE).isoformat()
        elif defect == "wrong-day":
            batch.as_of_date += dt.timedelta(days=1)
        elif defect == "cross-midnight":
            meta["positions_requested_at"] = (START - dt.timedelta(hours=11)).isoformat()
        elif defect == "after-creation":
            batch.created_at = START + MINUTE
        elif defect == "wrong-scope":
            meta["ledger_scope_sha256"] = "0" * 64
        elif defect == "stale":
            (await session.get(CashFlowCoverage, account)).fetched_at = START + MINUTE
        elif defect == "file":
            batch.filename = "other-broker.csv"
        if defect == "legacy-api":
            batch.created_at = START + 4 * MINUTE  # after covered request start
            batch.diff_summary = None
        else:
            batch.diff_summary = {KEY: meta}
        await session.commit()
    async with sessions() as check:
        result = await get_portfolio_return_summary(check, account_name=account)
        assert result["absolute_gain_after_flows_gbp"] is None
        if defect in {"file", "legacy-api", "stale"}:
            assert any("does not cover" in n for n in result["notes"])


async def test_unchanged_legacy_snapshot_is_not_backfilled(db, timed_broker):
    sessions, _ = db
    account = router.settings.trading212_account_name
    async with sessions() as session:
        batch, _ = await sync_portfolio_snapshot(
            session, timed_broker.client, account_name=account, observation_date=START.date()
        )
        before = batch.created_at, batch.diff_summary
        result = await router.run_trading212_worker_sync(session, timed_broker.client)
        assert isinstance(result, router.Trading212SyncResult) and result.snapshot == "unchanged"
    async with sessions() as check:
        retained = (await check.scalars(select(ImportBatch))).one()
        assert (retained.created_at, retained.diff_summary) == before
        assert KEY not in retained.diff_summary
