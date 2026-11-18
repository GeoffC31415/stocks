"""Worker orchestration through real parsers, mocked HTTP and disposable SQLite."""

import asyncio
import datetime as dt

import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlite_schema import create_file_schema

from app.models import (
    CashFlowCoverage,
    ExternalCashFlow,
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    Order,
    OrderImportBatch,
)
from app.routers import trading212 as router
from app.services.trading212 import Trading212Client

# Synthetic ISINs with valid check digits. Display names deliberately collide.
OLD_ISIN = "GB00TEST0005"
NEW_ISIN = "GB00TEST0013"


class Broker:
    def __init__(self):
        self.calls = []
        self.arrived_at = {}
        self.pages = {
            "positions": [
                {
                    "instrument": {"isin": OLD_ISIN, "name": "Test"},
                    "quantity": 1,
                    "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
                }
            ],
            "summary": {
                "currency": "GBP",
                "cash": {"availableToTrade": 3, "inPies": 0, "reservedForOrders": 0},
            },
            "orders": {"items": [], "nextPagePath": None},
            "transactions": {"items": [], "nextPagePath": None},
        }
        self.client = Trading212Client(
            api_key="synthetic",
            api_secret="synthetic",
            page_delay=0,
            transport=httpx.MockTransport(self.respond),
        )

    def respond(self, request):
        assert request.method == "GET"
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if "cursor" in request.url.params:
            endpoint += "/next"
        self.calls.append(endpoint)
        self.arrived_at[endpoint] = dt.datetime.now(dt.UTC)
        page = self.pages[endpoint]
        return page if isinstance(page, httpx.Response) else httpx.Response(200, json=page)

    def add_history(self, n):
        self.pages["orders"]["items"].append(
            {
                "order": {"side": "BUY", "instrument": {"name": "Test"}},
                "fill": {
                    "id": n,
                    "filledAt": "2020-01-01T12:00:00Z",
                    "type": "TRADE",
                    "quantity": 1,
                    "walletImpact": {"currency": "GBP", "netValue": -9},
                },
            }
        )
        self.pages["transactions"]["items"].append(
            {
                "reference": f"synthetic-{n}",
                "dateTime": "2020-01-01T12:00:00Z",
                "currency": "GBP",
                "amount": 10,
                "type": "DEPOSIT",
            }
        )


@pytest.fixture
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'synthetic.db'}")
    await create_file_schema(engine)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False), engine
    finally:
        await engine.dispose()


async def read_state(sessions):
    async with sessions() as check:
        return {
            model: (
                await check.execute(
                    select(model.__table__).order_by(model.__table__.primary_key.columns[0])
                )
            ).all()
            for model in (
                ImportBatch,
                HoldingSnapshot,
                Instrument,
                OrderImportBatch,
                Order,
                ExternalCashFlow,
                CashFlowCoverage,
            )
        }


async def test_complete_worker_sync_imports_then_validates_unchanged(db):
    sessions, engine = db
    commits = []
    event.listen(engine.sync_engine, "commit", lambda _: commits.append(True))
    broker = Broker()
    broker.add_history(1)
    for expected in ("imported", "unchanged"):
        async with sessions() as owner:
            result = await router.run_trading212_worker_sync(owner, broker.client)
        assert isinstance(result, router.Trading212SyncResult)
        assert result.snapshot == result.orders == expected
        assert result.cash_flows_total == 1
        assert result.cash_flows_imported == (1 if expected == "imported" else 0)
    assert len(commits) == 2
    assert broker.calls == ["positions", "summary", "orders", "transactions"] * 2
    state = await read_state(sessions)
    assert len(state[ImportBatch]) == len(state[Order]) == len(state[ExternalCashFlow]) == 1


@pytest.mark.parametrize("replace,extra_fill", [(True, False), (False, False), (True, True)])
async def test_partial_fills_remain_unlinked_until_manual_match(
    db, monkeypatch, replace, extra_fill
):
    from app.routers.matching import get_unmatched_groups, resolve_order_endpoint, unmatch_order
    from app.routers.orders import backfill_instruments
    from app.schemas import ResolveOrderBody
    from app.services.order_service import get_order_positions

    sessions, _ = db
    broker = Broker()

    async def run(broker):
        async with sessions() as owner:
            return await router.run_trading212_worker_sync(owner, broker.client)

    assert (await run(broker)).snapshot == "imported"
    instrument = broker.pages["positions"][0]["instrument"]
    old_isin = instrument["isin"]
    if replace:
        instrument["isin"] = NEW_ISIN  # Same display name after the sale.
    for n, isin in [(1, old_isin), (2, instrument["isin"])]:
        broker.add_history(n)
        broker.pages["orders"]["items"][-1]["order"]["instrument"]["isin"] = isin
    ledger = broker.pages["transactions"]
    broker.pages["transactions"] = httpx.Response(403)
    assert (await run(broker)).sections["orders"]["status"] == "imported"
    async with sessions() as check:
        manual, pending = (await check.scalars(select(Order).order_by(Order.id))).all()
        assert manual.instrument_id is None and pending.instrument_id is None
        # These executions are in the trade ledger, not guessed closed positions.
        assert await get_order_positions(check) == []
        old_id = await check.scalar(select(Instrument.id).where(Instrument.identifier == old_isin))
        await resolve_order_endpoint(manual.id, ResolveOrderBody(instrument_id=old_id), check)
        # Neither clearing a prior link nor applying an empty choice opts into
        # automatic matching. Manual selection must remain possible afterwards.
        await resolve_order_endpoint(pending.id, ResolveOrderBody(instrument_id=old_id), check)
        await unmatch_order(pending.id, check)
        await resolve_order_endpoint(pending.id, ResolveOrderBody(instrument_id=None), check)

    # Another account's successful imports run the shared global matcher.
    with monkeypatch.context() as m:
        m.setattr(router.settings, "trading212_account_name", "Other synthetic account")
        assert (await run(Broker())).snapshot == "imported"
    async with sessions() as check:
        assert (await check.get(Order, pending.id)).instrument_id is None

    broker.pages["transactions"] = ledger
    # Even a later explicit ISIN (consistent or changed) is not manual confirmation.
    broker.pages["orders"]["items"][1]["order"]["instrument"]["isin"] = NEW_ISIN
    if extra_fill:
        broker.add_history(3)
        broker.pages["orders"]["items"][-1]["order"]["instrument"]["isin"] = instrument["isin"]
    result = await run(broker)
    assert result.snapshot == ("imported" if replace else "unchanged")
    assert result.orders in {
        "imported",
        "unchanged",
    }  # A revised provider claim can create an audit batch.
    async with sessions() as check:
        links = (
            await check.execute(
                select(Order.match_status, Instrument.identifier)
                .outerjoin(Order.instrument)
                .order_by(Order.id)
            )
        ).all()
        assert (
            links
            == [("manual", old_isin), ("unmatched", None)]
            + [("auto_high", instrument["isin"])] * extra_fill
        )
        assert await backfill_instruments(check) == {"orders_linked": 0}
        groups = await get_unmatched_groups(session=check)
        assert any(g.order_count == 1 for g in groups)
        await resolve_order_endpoint(pending.id, ResolveOrderBody(instrument_id=old_id), check)
    async with sessions() as check:
        retained = await check.get(Order, pending.id)
        assert (retained.instrument_id, retained.match_status) == (old_id, "manual")


@pytest.mark.parametrize(
    ("bad", "expected_code"),
    [
        ("positions", "invalid_position_identity"),
        ("orders", "invalid_order_fill_type"),
        ("transactions", "cash_history_conflict"),
    ],
)
async def test_late_validation_keeps_only_complete_independent_history(db, bad, expected_code):
    sessions, engine = db
    broker = Broker()
    broker.add_history(1)
    async with sessions() as owner:
        await router.run_trading212_sync(owner, broker.client)
    before = await read_state(sessions)
    broker.calls.clear()
    broker.pages["positions"] = []  # A genuine sale only if the whole refresh succeeds.
    broker.add_history(2)
    if bad == "positions":
        broker.pages["positions"].append({})
    elif bad == "orders":
        broker.pages["orders"]["items"].append({"fill": {"type": "PRIVATE_SENTINEL"}})
    else:
        broker.pages["transactions"]["items"].pop(
            0
        )  # A missing retained event, not a fresh ledger.

    commits = []
    event.listen(engine.sync_engine, "commit", lambda _: commits.append(True))
    async with sessions() as owner:
        result = await router.run_trading212_worker_sync(owner, broker.client)
        assert len(commits) == 1
        await owner.commit()  # Must not resurrect a discarded valuation/section.
    assert isinstance(result, router.Trading212Incomplete)
    assert [(e.code, e.t212_endpoint, e.t212_phase) for e in result.errors] == [
        (expected_code, bad, "import")
    ]
    assert broker.calls == ["positions", "summary", "orders", "transactions"]
    assert set(result.sections) == {"cash", "holdings", "transactions", "orders"}
    for section, item in result.sections.items():
        if section in {"cash", "holdings", bad}:
            assert not item.get("verified_at") and not item.get("valuation_at")
            assert item["status"] not in {"ok", "imported", "unchanged"}
            assert item["coverage"] != "complete"
        else:
            assert item["status"] == "imported"
            assert item["verified_at"] and item["coverage"] == "complete"
            assert not item.get("valuation_at")
    assert "PRIVATE_SENTINEL" not in str(result.sections)
    after = await read_state(sessions)
    for model in (ImportBatch, Instrument, HoldingSnapshot):
        assert after[model] == before[model]
    for section, models in [
        ("orders", (OrderImportBatch, Order)),
        ("transactions", (ExternalCashFlow, CashFlowCoverage)),
    ]:
        for model in models:
            if section == bad:
                assert after[model] == before[model]
            elif model is CashFlowCoverage:
                assert after[model][0].fetched_at > before[model][0].fetched_at
            else:
                assert after[model][:-1] == before[model]


@pytest.mark.parametrize("bad", ["positions", "orders", "transactions"])
async def test_endpoint_fetch_failure_discards_every_row_from_that_endpoint(db, bad):
    sessions, _ = db
    broker = Broker()
    broker.add_history(1)
    if bad == "positions":
        broker.pages["positions"] = {}  # client rejects response shape
    else:
        broker.pages[bad]["nextPagePath"] = f"/api/v0/equity/history/{bad}?cursor=2&limit=50"
        broker.pages[bad + "/next"] = httpx.Response(403)
    async with sessions() as owner:
        result = await router.run_trading212_worker_sync(owner, broker.client)
    expected_calls = ["positions", "summary", "orders", "transactions"]
    if bad != "positions":
        expected_calls.insert(expected_calls.index(bad) + 1, bad + "/next")
    assert broker.calls == expected_calls  # no retries/refetch of already observed pages
    assert [(e.t212_endpoint, e.t212_phase) for e in result.errors] == [(bad, "fetch")]
    assert (
        not result.sections["holdings"]["verified_at"]
        and not result.sections["cash"]["verified_at"]
    )
    state = await read_state(sessions)
    assert not state[ImportBatch] and not state[Instrument]
    for section, model in [
        ("orders", Order),
        ("transactions", ExternalCashFlow),
        ("transactions", CashFlowCoverage),
    ]:
        assert bool(state[model]) == (section != bad)
        assert bool(result.sections[section]["verified_at"]) == (section != bad)


async def test_independent_failures_without_eligible_history_do_not_commit(db):
    sessions, engine = db
    broker = Broker()
    broker.pages["summary"] = httpx.Response(403)
    broker.pages["orders"] = {"items": [{}], "nextPagePath": None}
    broker.pages["transactions"] = {"items": [{}]}  # not a completed ledger
    commits = []
    event.listen(engine.sync_engine, "commit", lambda _: commits.append(True))
    async with sessions() as owner:
        result = await router.run_trading212_worker_sync(owner, broker.client)
    assert {e.t212_endpoint for e in result.errors} == {"account_summary", "transactions", "orders"}
    assert all(s["verified_at"] is None for s in result.sections.values())
    assert commits == [] and not any((await read_state(sessions)).values())


@pytest.mark.parametrize("denied_summary", [True, False])
async def test_worker_cannot_add_changed_fill_as_a_second_trade(db, denied_summary):
    sessions, _ = db
    broker = Broker()
    broker.add_history(1)
    async with sessions() as owner:
        await router.run_trading212_worker_sync(owner, broker.client)
    before = await read_state(sessions)
    if denied_summary:
        broker.pages["summary"] = httpx.Response(403)
    broker.pages["positions"] = []
    broker.pages["orders"]["items"][0]["fill"]["quantity"] = 2  # same provider fill ID
    broker.add_history(2)
    async with sessions() as owner:
        result = await router.run_trading212_worker_sync(owner, broker.client)
    after = await read_state(sessions)
    assert after[ImportBatch] == before[ImportBatch]
    assert after[Order] == before[Order] and after[OrderImportBatch] == before[OrderImportBatch]
    assert after[ExternalCashFlow][:-1] == before[ExternalCashFlow]
    assert (
        not result.sections["orders"]["verified_at"]
        and result.sections["transactions"]["verified_at"]
    )
    assert ("orders", "import") in {(e.t212_endpoint, e.t212_phase) for e in result.errors}


async def test_partial_verification_and_ledger_cutoff_use_section_observation_not_replay_time(db):
    sessions, _ = db
    broker = Broker()
    broker.add_history(1)
    broker.pages["summary"] = httpx.Response(403)
    for expected in ("imported", "unchanged"):
        async with sessions() as owner:
            result = await router.run_trading212_worker_sync(owner, broker.client)
        for section in ("orders", "transactions"):
            assert result.sections[section]["status"] == expected
            verified = dt.datetime.fromisoformat(result.sections[section]["verified_at"])
            assert verified <= broker.arrived_at[section]
        coverage = (await read_state(sessions))[CashFlowCoverage][0]
        assert coverage.fetched_at.replace(tzinfo=dt.UTC) == verified


async def test_expired_shared_budget_before_partial_commit_is_hard_failure(db, monkeypatch):
    sessions, _ = db
    broker = Broker()
    broker.add_history(1)
    broker.pages["summary"] = httpx.Response(403)
    clock = [0.0]
    client = Trading212Client(
        api_key="synthetic",
        api_secret="synthetic",
        page_delay=0,
        transport=httpx.MockTransport(broker.respond),
        clock=lambda: clock[0],
        runtime_budget=1,
    )
    real_cash = router.sync_cash_history

    async def finish_after_deadline(*args, **kwargs):
        staged = await real_cash(*args, **kwargs)
        clock[0] = 2
        return staged

    monkeypatch.setattr(router, "sync_cash_history", finish_after_deadline)
    async with sessions() as owner:
        with pytest.raises(router.Trading212DataError) as rejected:
            await router.run_trading212_worker_sync(owner, client)
        assert rejected.value.code == "runtime_budget_exhausted"
        await owner.commit()
    assert not any((await read_state(sessions)).values())


@pytest.mark.parametrize("failure", ["cancel", "db", "commit", "unclassified"])
async def test_hard_failure_after_partial_staging_leaves_no_committed_history(
    db, monkeypatch, failure
):
    from sqlalchemy.exc import OperationalError

    sessions, _ = db
    broker = Broker()
    broker.add_history(1)
    broker.pages["summary"] = httpx.Response(403)
    entered = asyncio.Event()
    real_cash = router.sync_cash_history

    async def interrupt(joined, *args, **kwargs):
        result = await real_cash(joined, *args, **kwargs)
        await joined.commit()  # Inner legacy helpers must never reach the physical commit.
        entered.set()
        if failure == "cancel":
            await asyncio.Event().wait()
        if failure == "db":
            raise OperationalError("synthetic", {}, RuntimeError())
        if failure == "unclassified":
            raise router.Trading212DataError("synthetic unknown rejection")
        return result

    monkeypatch.setattr(router, "sync_cash_history", interrupt)
    async with sessions() as owner:
        commit = owner.commit
        if failure == "commit":

            async def reject_commit():
                # Even a classified data exception at this phase MUST NOT recover.
                raise router.Trading212DataError("synthetic", code="cash_history_conflict")

            monkeypatch.setattr(owner, "commit", reject_commit)
        task = asyncio.create_task(router.run_trading212_worker_sync(owner, broker.client))
        await asyncio.wait_for(entered.wait(), 3)
        if failure == "cancel":
            task.cancel()
        expected = {"cancel": asyncio.CancelledError, "db": OperationalError}.get(
            failure, router.Trading212DataError
        )
        with pytest.raises(expected) as rejected:
            await task
        if failure == "commit":
            assert (rejected.value.t212_endpoint, rejected.value.t212_phase) == ("sync", "commit")
        await commit()
    assert not any((await read_state(sessions)).values())


@pytest.mark.parametrize(
    "failure,expected", [(401, httpx.HTTPStatusError), (429, router.Trading212DataError)]
)
async def test_global_auth_and_budget_never_release_staged_history(db, failure, expected):
    sessions, _ = db
    broker = Broker()
    broker.add_history(1)
    broker.pages["summary"] = httpx.Response(403)
    broker.pages["transactions"] = httpx.Response(failure, headers={"Retry-After": "900"})
    async with sessions() as owner:
        with pytest.raises(expected):
            await router.run_trading212_worker_sync(owner, broker.client)
        await owner.commit()
    assert broker.calls == ["positions", "summary", "orders", "transactions"]
    assert not any((await read_state(sessions)).values())


async def test_partial_replay_serializes_retained_checks_with_commit(db, monkeypatch):
    from sqlalchemy.exc import OperationalError

    sessions, engine = db
    broker = Broker()
    broker.add_history(1)
    async with sessions() as owner:
        await router.run_trading212_sync(owner, broker.client)
    broker.pages["positions"] = {}
    real_orders = router.sync_order_history

    async def compete_after_duplicate_check(*args, **kwargs):
        try:
            return await real_orders(*args, **kwargs)
        finally:
            # A successful unchanged history still depends on its read baseline.
            async with engine.begin() as competitor:
                await competitor.exec_driver_sql("PRAGMA busy_timeout=0")
                with pytest.raises(OperationalError, match="database is locked"):
                    await competitor.exec_driver_sql(
                        "UPDATE order_import_batches SET id = id WHERE 0"
                    )

    monkeypatch.setattr(router, "sync_order_history", compete_after_duplicate_check)
    async with sessions() as owner:
        result = await router.run_trading212_worker_sync(owner, broker.client)
    assert result.sections["orders"]["status"] == "unchanged"
