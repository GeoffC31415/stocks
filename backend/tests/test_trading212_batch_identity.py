"""Trading 212 batch identity from synthetic HTTP responses, never reconstructed rows."""

import copy
import datetime as dt
import hashlib
import json
from functools import partial

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlite_schema import create_file_schema
from test_gate_a_trading212 import Reader

from app.models import AccountAlias, CashFlowCoverage, ImportBatch, Order, OrderImportBatch
from app.routers.trading212 import run_trading212_sync
from app.services.closure_review import review_closure_observation
from app.services.import_service import DuplicateImportError, import_holding_snapshot
from app.services.order_service import DuplicateOrderImportError
from app.services.trading212 import (
    Trading212Client,
    Trading212DataError,
    positions_to_rows,
    sync_order_history,
    sync_portfolio_snapshot,
)


@pytest.fixture
async def sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'synthetic.db'}")
    try:
        await create_file_schema(engine)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def provider():
    fixture = Reader()
    positions = await fixture.fetch_positions()
    account = await fixture.fetch_account_summary()
    orders = await fixture.fetch_historical_orders()
    payloads = {
        "/api/v0/equity/positions": positions,
        "/api/v0/equity/account/summary": account,
        "/api/v0/equity/history/orders": {"items": orders, "nextPagePath": None},
        "/api/v0/equity/history/transactions": {
            "items": await fixture.fetch_transactions(),
            "nextPagePath": None,
        },
    }
    client = Trading212Client(
        api_key="synthetic",
        api_secret="synthetic",
        page_delay=0,
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=payloads[req.url.path])),
    )
    return client, positions, account, orders


def raw_digest(**fields):
    # Published legacy evidence format, independent of the service under test.
    for name in ("positions", "items"):
        if name in fields:
            fields[name] = sorted(fields[name], key=lambda row: json.dumps(row, sort_keys=True))
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def test_portfolio_projects_before_sorting_but_retains_raw_hash_and_valuation(
    sessions, provider
):
    client, positions, account, _ = provider
    # Already-present unknown metadata can change raw sort order on the next fetch.
    positions[0]["_extra"] = 2
    positions[1]["_extra"] = 1
    async with sessions() as db:
        first = await run_trading212_sync(db, client)
        retained_raw = raw_digest(
            account_name=first.account_name, positions=positions, account=account
        )
        batch = await db.scalar(select(ImportBatch))
        batch.as_of_date = dt.date(2020, 1, 1)
        await db.commit()
    positions.reverse()
    del positions[0]["_extra"]
    positions[1]["_extra"] = 0
    positions[0]["walletImpact"]["_extra"] = None
    account["cash"]["_extra"] = {"opaque": [1, 2]}
    async with sessions() as db:
        second = await run_trading212_sync(db, client)
        assert second.snapshot == "unchanged"
        assert second.valuation_at == dt.date(2020, 1, 1)
        assert second.fetched_at > first.fetched_at
    async with sessions() as db:
        (batch,) = (await db.scalars(select(ImportBatch))).all()
        assert batch.file_sha256 == retained_raw
        coverage = await db.get(CashFlowCoverage, first.account_name)
        assert coverage.fetched_at == second.fetched_at.replace(tzinfo=None)


async def test_orders_new_metadata_matches_retained_source_not_fill_fingerprints(
    sessions, provider
):
    client, _, _, orders = provider
    orders[0]["order"]["side"] = "SELL"
    orders[0]["fill"].update(quantity=-1, price=9)
    orders.append(copy.deepcopy(orders[0]))
    orders[1]["fill"]["id"] = 2
    async with sessions() as db:
        first = await run_trading212_sync(db, client)
        assert first.order_rows == 2
        retained_raw = raw_digest(account_name=first.account_name, items=orders)
    orders.reverse()
    orders[0]["_extra"] = 1
    orders[1]["order"]["instrument"]["_extra"] = {"opaque": True}
    orders[1]["fill"]["walletImpact"]["_extra"] = [1]
    async with sessions() as db:
        assert (await run_trading212_sync(db, client)).orders == "unchanged"
    async with sessions() as db:
        (batch,) = (await db.scalars(select(OrderImportBatch))).all()
        assert batch.file_sha256 == retained_raw
        # Legacy signed-SELL fingerprints for two otherwise identical distinct fills.
        assert set(await db.scalars(select(Order.order_fingerprint))) == {
            "a38123081119817b956dabea7971213c801fa51837fd6a758414f195bc7820d4",
            "46b0319244052f2c1765f98516eca7fcb73541447f5c02837ed83b91446c5f89",
        }
        # A documented price change must be retained even though no trade is inserted.
        orders[1]["fill"]["price"] += 1
        changed = await run_trading212_sync(db, client)
        assert (changed.orders, changed.order_rows) == ("imported", 0)


async def test_latest_holdings_only_and_canonical_alias_scope(sessions, provider):
    client, _, account, _ = provider
    async with sessions() as db:
        db.add(
            AccountAlias(source="holdings", source_account_name="Alias", canonical_account_name="A")
        )
        await db.commit()
        account["_extra"] = 0
        first, _ = await sync_portfolio_snapshot(db, client, account_name="A")
        # Separate cash buckets (not just their mapped sum) are significant.
        account["cash"].update(availableToTrade=20, inPies=5)
        middle, _ = await sync_portfolio_snapshot(db, client, account_name="Alias")
        account["cash"].update(availableToTrade=25, inPies=0)
        account["_extra"] = 1
        last, _ = await sync_portfolio_snapshot(db, client, account_name="Alias")
        assert first.id < middle.id < last.id
        other, _ = await sync_portfolio_snapshot(db, client, account_name="B")
        assert other.id > last.id
        account.pop("_extra")
        with pytest.raises(DuplicateImportError) as unchanged:
            await sync_portfolio_snapshot(db, client, account_name="A")
        assert unchanged.value.batch_id == last.id
        # Documented but not mapped: appearing is not the same as absent.
        account["totalValue"] = 45
        changed, _ = await sync_portfolio_snapshot(db, client, account_name="A")
        assert changed.id > other.id


@pytest.mark.parametrize("legacy_has_extra", [False, True])
async def test_forward_evidence_does_not_backfill_legacy_holdings(
    sessions, provider, legacy_has_extra
):
    client, positions, account, _ = provider
    if legacy_has_extra:
        account["_extra"] = "old"
    legacy_raw = raw_digest(account_name="A", account=account, positions=positions)
    async with sessions() as db:
        old, old_summary = await import_holding_snapshot(
            db,
            parsed_rows=positions_to_rows(positions, account, account_name="A"),
            as_of_date=dt.date(2020, 1, 1),
            filename="trading212-api-portfolio.json",
            file_sha256=legacy_raw,
        )
        account["_extra"] = "new"
        if legacy_has_extra:
            new, _ = await sync_portfolio_snapshot(db, client, account_name="A")
            assert new.id > old.id  # Can't prove anything about the old raw hash.
            account["_extra"] = "newer"
            retained_id = new.id
        else:
            retained_id = old.id  # The incoming projection exactly reproduces the old raw bytes.
        with pytest.raises(DuplicateImportError) as unchanged:
            await sync_portfolio_snapshot(db, client, account_name="A")
        assert unchanged.value.batch_id == retained_id
        await db.commit()
    async with sessions() as db:
        retained = await db.get(ImportBatch, old.id)
        assert (retained.file_sha256, retained.diff_summary) == (legacy_raw, old_summary)


async def test_portfolio_does_not_compare_digests_across_schemes(sessions, provider):
    client, _, account, _ = provider
    account["_extra"] = 1
    async with sessions() as db:
        prior, summary = await sync_portfolio_snapshot(db, client, account_name="A")
        proof = summary["source_projection"]
        prior.diff_summary = {**summary, "source_projection": {**proof, "scheme": "other"}}
        await db.commit()
        account["_extra"] = 2
        batch, _ = await sync_portfolio_snapshot(db, client, account_name="A")
        assert batch.id != prior.id


async def test_no_equivalence_for_order_batches_with_only_unmatched_raw_hashes(sessions, provider):
    client, _, _, orders = provider
    orders[0]["_extra"] = 1
    async with sessions() as db:
        a, inserted = await sync_order_history(db, client, account_name="A")
        assert inserted == 1
        assert a.file_sha256 == raw_digest(account_name="A", items=orders)
        orders[0]["_extra"] = 2
        b, inserted = await sync_order_history(db, client, account_name="A")
        assert b.id != a.id and inserted == 0
        assert b.file_sha256 == raw_digest(account_name="A", items=orders)
        # Nor can an exact projected raw source under a different label establish a match.
        orders[0].pop("_extra")
        await sync_order_history(db, client, account_name="B")
        orders[0]["_extra"] = 3
        c, inserted = await sync_order_history(db, client, account_name="A")
        assert c.id > b.id and inserted == 0
        with pytest.raises(DuplicateOrderImportError) as exact:
            await sync_order_history(db, client, account_name="A")
        assert exact.value.batch_id == c.id


async def test_metadata_does_not_hide_changed_history_multiplicity(sessions, provider):
    client, _, _, orders = provider
    async with sessions() as db:
        await sync_order_history(db, client, account_name="A")
        orders.append(copy.deepcopy(orders[0]))
        orders[1]["fill"]["_extra"] = True
        batch, inserted = await sync_order_history(db, client, account_name="A")
        assert inserted == 0
        assert batch.file_sha256 == raw_digest(account_name="A", items=orders)


async def test_force_bypasses_projections_not_raw_order_uniqueness(sessions, provider):
    client, _, account, orders = provider
    async with sessions() as db:
        await run_trading212_sync(db, client)
        account["_extra"] = True
        orders[0]["fill"]["_extra"] = True
        duplicate = await run_trading212_sync(db, client)
        assert (duplicate.snapshot, duplicate.orders) == ("unchanged", "unchanged")
        forced = await run_trading212_sync(db, client, force=True)
        assert (forced.snapshot, forced.orders, forced.order_rows) == ("imported", "imported", 0)
        # Exact raw duplicate keeps its original batch ID, not the projection match.
        with pytest.raises(DuplicateOrderImportError) as exact:
            await sync_order_history(db, client, account_name=forced.account_name)
        assert exact.value.batch_id == await db.scalar(
            select(OrderImportBatch.id).order_by(OrderImportBatch.id.desc())
        )
        with pytest.raises(IntegrityError):
            await sync_order_history(db, client, account_name=forced.account_name, force=True)
        await db.rollback()
    async with sessions() as db:
        assert len((await db.scalars(select(ImportBatch.id))).all()) == 2
        assert len((await db.scalars(select(OrderImportBatch.id))).all()) == 2


async def test_review_still_requires_exact_raw_evidence_when_projections_match(sessions, provider):
    client, positions, account, _ = provider
    async with sessions() as db:
        valuation, _ = await sync_portfolio_snapshot(
            db,
            client,
            account_name="A",
            observation_date=dt.date(2026, 1, 2),
        )
        positions.pop()
        projected = raw_digest(account_name="A", positions=positions, account=account)
        account["_extra"] = 1
        latest, _ = await sync_portfolio_snapshot(
            db,
            client,
            account_name="A",
            observation_date=dt.date(2026, 1, 1),
        )
        account["_extra"] = 2
        review = partial(
            review_closure_observation,
            db,
            account_name="A",
            expected_batch_id=latest.id,
            expected_batch_sha256=latest.file_sha256,
            expected_valuation_batch_id=valuation.id,
            expected_valuation_batch_sha256=valuation.file_sha256,
            identifiers=frozenset({"TWO"}),
            positions=positions,
            account_summary=account,
            observation_date=dt.date(2026, 1, 3),
            apply=True,
        )
        with pytest.raises(Trading212DataError, match="staged observation does not match"):
            await review(observation_sha256=projected)
        raw = raw_digest(account_name="A", positions=positions, account=account)
        result = await review(observation_sha256=raw)
        assert result["applied"] and result["observation_sha256"] == raw
    async with sessions() as db:
        assert (
            await db.scalar(select(ImportBatch.file_sha256).order_by(ImportBatch.id.desc())) == raw
        )
