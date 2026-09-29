"""Synthetic file-backed regressions; no live data or broker access."""

import datetime as dt
import hashlib
import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_gate_a_trading212 import Reader

from app.models import Base, ImportBatch, Instrument
from app.services.closure_review import review_closure_observation
from app.services.trading212 import Trading212DataError, sync_portfolio_snapshot


@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize(
    "case", ["predates", "wrong_id", "wrong_hash", "ingestion_as_valuation", "valid"]
)
async def test_closure_binds_ingestion_and_retained_valuation(tmp_path, apply, case, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'synthetic.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as owner:
            retained, _ = await sync_portfolio_snapshot(owner, Reader(), account_name="Trading 212")
            retained.as_of_date = dt.date(2026, 1, 1)
            await owner.commit()
            latest, _ = await sync_portfolio_snapshot(
                owner, Reader(), account_name="Trading 212", force=True
            )
            latest.as_of_date = dt.date(2020, 1, 1)
            await owner.commit()
            client = Reader()
            client.omit = True
            positions = await client.fetch_positions()
            summary = await client.fetch_account_summary()
            digest = hashlib.sha256(
                json.dumps(
                    {"account_name": "Trading 212", "account": summary, "positions": positions},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            args = {
                "account_name": "Trading 212",
                "expected_batch_id": latest.id,
                "expected_batch_sha256": latest.file_sha256,
                "observation_sha256": digest,
                "expected_valuation_batch_id": (
                    retained.id + 99
                    if case == "wrong_id"
                    else latest.id
                    if case == "ingestion_as_valuation"
                    else retained.id
                ),
                "expected_valuation_batch_sha256": "0" * 64
                if case == "wrong_hash"
                else retained.file_sha256,
                "identifiers": frozenset({"TWO"}),
                "positions": positions,
                "account_summary": summary,
                "observation_date": dt.date(2021 if case == "predates" else 2026, 1, 1),
                "apply": apply,
            }
            if case == "valid":
                from sqlalchemy import text
                from sqlalchemy.exc import OperationalError

                from app.services import closure_review

                competing = create_async_engine(
                    f"sqlite+aiosqlite:///{tmp_path / 'synthetic.db'}",
                    connect_args={"timeout": 0.01},
                )
                original = closure_review.get_latest_observation_for_account

                async def read_while_writer_is_reserved(*args):
                    async with competing.connect() as connection:
                        with pytest.raises(OperationalError, match="locked"):
                            await connection.execute(text("BEGIN IMMEDIATE"))
                    return await original(*args)

                monkeypatch.setattr(
                    closure_review,
                    "get_latest_observation_for_account",
                    read_while_writer_is_reserved,
                )
                try:
                    result = await review_closure_observation(owner, **args)
                finally:
                    await competing.dispose()
                assert result["expected_valuation_batch_id"] == args["expected_valuation_batch_id"]
                assert result["closed"][0]["identifier"] == "TWO"
            else:
                with pytest.raises(Trading212DataError, match="valuation"):
                    await review_closure_observation(owner, **args)
            await owner.commit()  # A caught rejection must not leak staged writes.
        async with factory() as reader:
            assert await reader.scalar(select(func.count()).select_from(ImportBatch)) == (
                3 if case == "valid" and apply else 2
            )
            instrument = await reader.scalar(
                select(Instrument).where(Instrument.identifier == "TWO")
            )
            assert (instrument.closed_at is not None) == (case == "valid" and apply)
    finally:
        await engine.dispose()


@pytest.mark.parametrize("value", [[], {}, ["PRIVATE"], {"PRIVATE": "PRIVATE"}, None, 7])
def test_public_report_malformed_values_are_opaque_unknown(value):
    from app.services.sync_control import public_report

    report = public_report(
        {
            "started_at": "2026-09-29T10:00:00+00:00",
            "outcome": value,
            "steps": [{"name": value, "status": value, "detail": "PRIVATE"}],
            "files": [{"status": value, "filename": "PRIVATE"}],
            "freshness": {
                "Hargreaves Lansdown": {
                    "orders": {
                        "status": value,
                        "coverage": value,
                        "reason_code": value,
                        "action_code": value,
                    }
                }
            },
        }
    )
    assert report["steps"][0]["name"] == "Sync step"
    assert report["steps"][0]["status"] == report["files"][0]["status"] == "unknown"
    assert report["freshness"]["Hargreaves Lansdown"]["orders"]["coverage"] == "unknown"
    assert "PRIVATE" not in json.dumps(report)


@pytest.mark.parametrize("value", [None, 7, "PRIVATE", {"PRIVATE": "PRIVATE"}])
def test_public_report_nonlist_collections_are_ignored(value):
    from app.services.sync_control import public_report

    report = public_report(
        {"started_at": "2026-09-29T10:00:00+00:00", "steps": value, "files": value}
    )
    assert report["steps"] == report["files"] == []


@pytest.mark.parametrize(
    "case",
    [
        "legacy_unpinned",
        "empty_unpinned",
        "name_changed",
        "number_changed",
        "both_changed",
        "ambiguous",
        "verified_alias",
    ],
)
async def test_hl_owner_pin_is_explicit_and_immutable(tmp_path, case):
    from test_gate_a_hl_pair import ACTIVITY, HOLDINGS, enroll_synthetic_hl_owner

    from app.models import AccountAlias, Order
    from app.services.hl_parser import hl_client_identity_key
    from app.services.hl_sync_service import import_pair
    from app.services.import_service import import_hl_holdings_csv
    from app.services.order_service import import_hl_orders_csv

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'synthetic-hl.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as owner:
            if case == "verified_alias":
                owner.add(
                    AccountAlias(
                        source="holdings",
                        source_account_name="HL Fund & Share Account",
                        canonical_account_name="Canonical HL owner",
                    )
                )
                await owner.commit()
            if case != "empty_unpinned":
                await import_hl_holdings_csv(
                    owner,
                    file_bytes=HOLDINGS.encode(),
                    filename="legacy.csv",
                    as_of_date=dt.date(2026, 9, 29),
                )
                await import_hl_orders_csv(
                    owner,
                    file_bytes=ACTIVITY.encode(),
                    filename="legacy-orders.csv",
                    drip_threshold_gbp=1000,
                )
            if case not in {"legacy_unpinned", "empty_unpinned"}:
                await enroll_synthetic_hl_owner(
                    owner,
                    "Canonical HL owner" if case == "verified_alias" else "HL Fund & Share Account",
                )
            if case == "ambiguous":
                owner.add(
                    AccountAlias(
                        source="hl-client-identity",
                        source_account_name=hl_client_identity_key("Different Person", "OTHER-001"),
                        canonical_account_name="HL Fund & Share Account",
                    )
                )
                await owner.commit()
            prior_fingerprint = await owner.scalar(select(Order.order_fingerprint))
            await owner.rollback()
            # A coherent, reconciled smaller pair would close TWO if identity
            # validation were bypassed. The economic ONE trade remains identical.
            holdings = (
                HOLDINGS.replace("TWO,Two,2,1000,20,18,11.11\n", "")
                .replace("Stock value:,30", "Stock value:,10")
                .replace("Number of holdings:,2", "Number of holdings:,1")
                .replace(",Totals,,,30,27,", ",Totals,,,10,9,")
            )
            activity = ACTIVITY
            replacements = []
            if case in {"name_changed", "both_changed", "legacy_unpinned"}:
                replacements.append(("Synthetic Person", "Different Person"))
            if case in {"number_changed", "both_changed"}:
                replacements.append(("SYNTHETIC-001", "OTHER-001"))
            for before, after in replacements:
                holdings, activity = (
                    holdings.replace(before, after),
                    activity.replace(before, after),
                )
            if case == "verified_alias":
                await import_pair(
                    owner, holdings.encode(), activity.encode(), as_of=dt.date(2026, 9, 29)
                )
            else:
                with pytest.raises(ValueError, match="owner identity.*operator review"):
                    await import_pair(
                        owner, holdings.encode(), activity.encode(), as_of=dt.date(2026, 9, 29)
                    )
            await owner.commit()
        async with factory() as reader:
            assert await reader.scalar(select(func.count()).select_from(ImportBatch)) == (
                0 if case == "empty_unpinned" else 2 if case == "verified_alias" else 1
            )
            assert await reader.scalar(
                select(func.count())
                .select_from(Instrument)
                .where(Instrument.closed_at.is_not(None))
            ) == (1 if case == "verified_alias" else 0)
            assert await reader.scalar(select(func.count()).select_from(Order)) == (
                0 if case == "empty_unpinned" else 1
            )
            assert await reader.scalar(select(Order.order_fingerprint)) == prior_fingerprint
    finally:
        await engine.dispose()
