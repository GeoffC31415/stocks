"""Independent spec regressions. Disposable synthetic SQLite; no live brokers."""

import asyncio
import datetime as dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_gate_a_trading212 import Reader

from app.models import Base, ImportBatch, Order
from app.routers.trading212 import run_trading212_sync
from app.services import sync_runner


@pytest.mark.parametrize("runner", [False, "cancel", "timeout"])
async def test_cancelled_final_cash_cannot_survive_owner_commit(tmp_path, monkeypatch, runner):
    from app.routers import trading212

    entered = asyncio.Event()

    async def suspended(*args, **kwargs):
        entered.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(trading212, "sync_cash_history", suspended)
    monkeypatch.setattr(sync_runner, "_trading212_configured", lambda: True)
    monkeypatch.setattr(trading212, "get_trading212_client", Reader)
    if runner == "timeout":
        monkeypatch.setattr(sync_runner, "FETCH_TIMEOUT_SECONDS", 0.1)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'disposable.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as owner:
            if runner:
                task = asyncio.create_task(
                    sync_runner.run_sync_all(owner, inbox=tmp_path / "inbox")
                )
                await asyncio.wait_for(entered.wait(), 5)
                if runner == "cancel":
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    report = await task
                    assert report.outcome == "failed"
                    assert report.steps[-1].status == "failed"
            else:
                with pytest.raises(TimeoutError):
                    async with asyncio.timeout(0.1):
                        await run_trading212_sync(owner, Reader())
            await owner.commit()
        async with async_sessionmaker(engine)() as reader:
            for model in (ImportBatch, Order):
                assert await reader.scalar(select(func.count()).select_from(model)) == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize("coverage", ["partial", "unknown"])
def test_incomplete_coverage_never_claims_complete(coverage):
    sections = {
        name: {
            "status": "unchanged",
            "verified_at": "2026-09-29T10:00:00+00:00",
            "coverage": "complete",
        }
        for name in ("holdings", "orders", "cash", "transactions")
    }
    sections["orders"]["coverage"] = coverage
    report = sync_runner.RunReport(
        "2026-09-29", steps=[sync_runner.StepResult("Trading 212", "ok", sections=sections)]
    )
    assert report.outcome == "partial"


def test_required_skipped_orders_and_duplicate_only_are_not_complete():
    report = sync_runner.RunReport(
        "2026-09-29",
        steps=[
            sync_runner.StepResult(
                "Trading 212",
                "ok",
                sections={
                    "holdings": {"status": "imported", "coverage": "complete"},
                    "orders": {"status": "skipped"},
                },
            )
        ],
    )
    assert report.outcome == "partial"
    duplicate = sync_runner.RunReport(
        "2026-09-29",
        steps=[sync_runner.StepResult("Import files", "unchanged")],
        files=[{"status": "duplicate"}],
    )
    assert duplicate.outcome == "no_op"


def test_import_success_is_not_coverage_evidence():
    from app.services.sync_freshness import verified_sections

    section = verified_sections({"orders": "imported"}, "2026-09-29", None)["orders"]
    assert section["coverage"] == "unknown"
    assert section["reason_code"] == "partial_coverage"
    assert section["action_code"] == "operator_review"


@pytest.mark.parametrize("bounded", [False, True])
async def test_hl_ninety_day_window_is_bounded_not_universal(tmp_path, bounded):
    from test_sync_hl_integration import ACTIVITY, HOLDINGS

    from app.services.hl_sync_service import FetchedHLPair

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async def fetch(inbox):
            options = (
                {"activity_start": dt.date(2026, 7, 1), "activity_end": dt.date(2026, 9, 29)}
                if bounded
                else {}
            )
            return FetchedHLPair(
                HOLDINGS, ACTIVITY, dt.datetime(2026, 9, 29, 11, tzinfo=dt.UTC), **options
            )

        async with async_sessionmaker(engine)() as session:
            report = await sync_runner.run_sync_all(
                session,
                inbox=tmp_path,
                fetchers=[("Hargreaves Lansdown", fetch)],
                include_trading212=False,
            )
        assert report.outcome == "partial"
        section = report.freshness["Hargreaves Lansdown"]["orders"]
        assert section["coverage"] != "complete"
        # Generic pairs have no attested fetch range: they must remain unknown.
        assert section["coverage"] == ("partial" if bounded else "unknown")
        if bounded:
            assert section["coverage_start"] == "2026-07-01"
            assert section["coverage_end"] == "2026-09-29"
    finally:
        await engine.dispose()


async def test_t212_retained_valuation_date_does_not_advance_with_check(tmp_path, monkeypatch):
    from app.routers import trading212
    from app.services.trading212 import sync_portfolio_snapshot

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            batch, _ = await sync_portfolio_snapshot(session, Reader(), account_name="Trading 212")
            batch.as_of_date = dt.date(2026, 1, 1)
            await session.commit()
            monkeypatch.setattr(sync_runner, "_trading212_configured", lambda: True)
            monkeypatch.setattr(trading212, "get_trading212_client", Reader)
            step = await sync_runner._trading212_step(session)
            assert step.sections["holdings"]["valuation_at"] == "2026-01-01"
            assert step.sections["holdings"]["verified_at"].startswith("2026-")
            assert step.sections["cash"]["valuation_at"] == "2026-01-01"
    finally:
        await engine.dispose()


async def test_hl_valuation_metadata_is_not_spreadsheet_check_date(tmp_path):
    from test_sync_hl_integration import ACTIVITY, HOLDINGS

    from app.services.hl_parser import parse_hl_holdings_csv_bytes
    from app.services.hl_sync_service import import_pair

    holdings = b"Valuation as at:,28-09-2026 16:00\n" + HOLDINGS
    _, valued = parse_hl_holdings_csv_bytes(holdings)
    assert valued == dt.date(2026, 9, 28)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as session:
            await import_pair(session, holdings, ACTIVITY, as_of=dt.date(2026, 9, 29))
            assert (await session.scalar(select(ImportBatch))).as_of_date == valued
    finally:
        await engine.dispose()


async def test_first_t212_observation_denied_cash_rejects_all_writes(tmp_path):
    from app.services.trading212 import Trading212DataError

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            client = Reader()
            client.denied = True
            with pytest.raises(Trading212DataError, match="cash"):
                await run_trading212_sync(session, client)
            await session.commit()
            for table in Base.metadata.sorted_tables:
                assert await session.scalar(select(func.count()).select_from(table)) == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize("payload", [{"items": []}, {"items": [{}] * 51, "nextPagePath": None}])
async def test_order_pagination_requires_terminal_evidence_and_bounded_pages(payload):
    from app.services.trading212 import Trading212Client, Trading212DataError

    class Client(Trading212Client):
        async def _get(self, path):
            return payload

    with pytest.raises(Trading212DataError):
        await Client(api_key="synthetic", api_secret="synthetic").fetch_historical_orders()


@pytest.mark.parametrize(
    "identity", [b"", b"Client Name:,Synthetic Person\n", b"Client Number:,SYNTHETIC-001\n"]
)
async def test_hl_pair_requires_actual_identity_on_both_halves(tmp_path, identity):
    from test_sync_hl_integration import ACTIVITY, HOLDINGS

    from app.services.hl_sync_service import import_pair

    HOLDINGS = HOLDINGS.replace(
        b"Client Name:,Synthetic Person\nClient Number:,SYNTHETIC-001\n", b""
    )
    ACTIVITY = ACTIVITY.replace(
        b"Client Name:,Synthetic Person\nClient Number:,SYNTHETIC-001\n", b""
    )
    # Equal legacy account labels cannot attest actual ownership.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as session:
            with pytest.raises(ValueError, match="identity"):
                await import_pair(
                    session, identity + HOLDINGS, identity + ACTIVITY, as_of=dt.date(2026, 9, 29)
                )
            assert await session.scalar(select(func.count()).select_from(ImportBatch)) == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "case",
    [
        "alias",
        "wrong_account",
        "wrong_provider",
        "shifted_baseline",
        "stale",
        "cash",
        "wrong_observation",
        "old_observation",
        "preview",
    ],
)
async def test_operational_closure_review_is_exact_and_offline(tmp_path, case):
    import hashlib
    import json

    from app.models import AccountAlias, Instrument
    from app.services.closure_review import review_closure_observation
    from app.services.trading212 import Trading212DataError, sync_portfolio_snapshot

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            session.add(
                AccountAlias(
                    source="holdings",
                    source_account_name="Alias",
                    canonical_account_name="Trading 212",
                )
            )
            await session.commit()
            batch, _ = await sync_portfolio_snapshot(session, Reader(), account_name="Trading 212")
            if case == "wrong_provider":
                batch.filename = "hl-pair-holdings.csv"
                await session.commit()
            if case == "shifted_baseline":
                newer, _ = await sync_portfolio_snapshot(
                    session, Reader(), account_name="Trading 212", force=True
                )
                newer.as_of_date = dt.date(2020, 1, 1)
                await session.commit()
            client = Reader()
            client.omit = True
            positions, summary = (
                await client.fetch_positions(),
                await client.fetch_account_summary(),
            )
            digest = hashlib.sha256(
                json.dumps(
                    {"account_name": "Trading 212", "account": summary, "positions": positions},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            args = {
                "account_name": "Wrong" if case == "wrong_account" else "Alias",
                "expected_batch_id": batch.id + (case == "stale"),
                "expected_batch_sha256": batch.file_sha256,
                "observation_sha256": "0" * 64 if case == "wrong_observation" else digest,
                "identifiers": frozenset({"CASH" if case == "cash" else "TWO"}),
                "positions": positions,
                "account_summary": summary,
                "apply": case != "preview",
            }
            if case == "old_observation":
                args["observation_date"] = dt.date(2020, 1, 1)
            if case in {"alias", "preview"}:
                result = await review_closure_observation(session, **args)
                assert result["applied"] == (case == "alias")
            else:
                with pytest.raises(Trading212DataError):
                    await review_closure_observation(session, **args)
            await session.commit()
            closed = await session.scalar(select(Instrument).where(Instrument.identifier == "TWO"))
            assert (closed.closed_at is not None) == (case == "alias")
            assert await session.scalar(select(func.count()).select_from(ImportBatch)) == (
                2 if case in {"alias", "shifted_baseline"} else 1
            )
    finally:
        await engine.dispose()


@pytest.mark.parametrize("database_name", ["operator.db", "operator?copy.db"])
async def test_closure_cli_preview_then_explicit_apply_on_disposable_database(
    tmp_path, database_name
):
    import hashlib
    import json
    import os
    import subprocess
    import sys

    from sqlalchemy.engine import URL

    from app.services.trading212 import sync_portfolio_snapshot

    database = tmp_path / database_name
    engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(database)))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            batch, _ = await sync_portfolio_snapshot(session, Reader(), account_name="Trading 212")
            reader = Reader()
            reader.omit = True
            positions, account = (
                await reader.fetch_positions(),
                await reader.fetch_account_summary(),
            )
            digest = hashlib.sha256(
                json.dumps(
                    {"account_name": "Trading 212", "account": account, "positions": positions},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            manifest = {
                "account_name": "Trading 212",
                "expected_batch_id": batch.id,
                "expected_batch_sha256": batch.file_sha256,
                "observation_sha256": digest,
                "identifiers": ["TWO"],
                "positions": positions,
                "account_summary": account,
                "observed_at": dt.datetime.now(dt.UTC).isoformat(),
            }
        review = tmp_path / "synthetic-review.json"
        review.write_text(json.dumps(manifest))
        argv = [
            sys.executable,
            "-m",
            "app.closure_review_cli",
            "--database",
            str(database),
            "--review",
            str(review),
        ]
        for apply in (False, True):
            result = subprocess.run(
                argv + (["--apply"] if apply else []),
                capture_output=True,
                text=True,
                env=os.environ.copy(),
                timeout=20,
            )
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["applied"] == apply
            async with async_sessionmaker(engine)() as check:
                assert await check.scalar(select(func.count()).select_from(ImportBatch)) == (
                    2 if apply else 1
                )
    finally:
        await engine.dispose()


def test_public_status_preserves_only_valid_coverage_range():
    from app.services.sync_control import public_report

    report = sync_runner.RunReport(
        "2026-09-29T10:00:00+00:00",
        freshness={
            "Hargreaves Lansdown": {
                "orders": {
                    "coverage": "partial",
                    "coverage_start": "2026-07-01",
                    "coverage_end": "2026-09-29",
                    "secret": "PRIVATE",
                }
            }
        },
    )
    section = public_report(report.to_json())["freshness"]["Hargreaves Lansdown"]["orders"]
    assert section["coverage_start"] == "2026-07-01"
    assert section["coverage_end"] == "2026-09-29"
    report.freshness["Hargreaves Lansdown"]["orders"]["coverage_start"] = "PRIVATE"
    assert "PRIVATE" not in str(public_report(report.to_json()))


@pytest.mark.parametrize(
    "start,end",
    [(dt.date(2026, 9, 29), dt.date(2026, 7, 1)), (dt.date(2026, 9, 20), dt.date(2026, 9, 29))],
)
async def test_hl_claimed_window_must_contain_export_activity(tmp_path, start, end):
    from test_sync_hl_integration import ACTIVITY, HOLDINGS

    from app.services.hl_sync_service import FetchedHLPair

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async def fetch(inbox):
            return FetchedHLPair(
                HOLDINGS,
                ACTIVITY,
                dt.datetime(2026, 9, 29, 11, tzinfo=dt.UTC),
                activity_start=start,
                activity_end=end,
            )

        async with async_sessionmaker(engine)() as session:
            report = await sync_runner.run_sync_all(
                session,
                inbox=tmp_path,
                fetchers=[("Hargreaves Lansdown", fetch)],
                include_trading212=False,
            )
            assert report.steps[0].status == "failed"
            assert await session.scalar(select(func.count()).select_from(ImportBatch)) == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize("dates", ["prior_valuation", "missing"])
async def test_hl_pair_requires_real_valuation_date_evidence(tmp_path, dates):
    from test_sync_hl_integration import ACTIVITY, HOLDINGS

    from app.services.hl_sync_service import import_pair

    if dates == "prior_valuation":
        holdings = b"Valuation as at:,28-09-2026 16:00\n" + HOLDINGS
        activity = b"Valuation as at:,28-09-2026 16:00\n" + ACTIVITY
    else:
        holdings = HOLDINGS.replace(b"Spreadsheet created at,29-09-2026 10:00\n", b"")
        activity = ACTIVITY
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as session:
            if dates == "missing":
                with pytest.raises(ValueError, match="date"):
                    await import_pair(session, holdings, activity, as_of=dt.date(2026, 9, 29))
                assert await session.scalar(select(func.count()).select_from(ImportBatch)) == 0
            else:
                await import_pair(session, holdings, activity, as_of=dt.date(2026, 9, 29))
                assert (await session.scalar(select(ImportBatch))).as_of_date == dt.date(
                    2026, 9, 28
                )
    finally:
        await engine.dispose()


@pytest.mark.parametrize("provider", ["trading212", "hl"])
async def test_latest_observation_dedupe_allows_a_b_a_then_unchanged(tmp_path, provider):
    from test_sync_hl_integration import ACTIVITY, HOLDINGS

    from app.services.hl_sync_service import import_pair
    from app.services.import_service import DuplicateImportError
    from app.services.trading212 import sync_portfolio_snapshot

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sequence.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            for index, cash in enumerate([25, 26, 25, 25]):
                if provider == "trading212":

                    class Observation(Reader):
                        async def fetch_account_summary(self, cash=cash):
                            result = await super().fetch_account_summary()
                            result["cash"]["availableToTrade"] = cash
                            return result

                    if index == 3:
                        with pytest.raises(DuplicateImportError):
                            await sync_portfolio_snapshot(
                                session, Observation(), account_name="Trading 212"
                            )
                    else:
                        await sync_portfolio_snapshot(
                            session, Observation(), account_name="Trading 212"
                        )
                else:
                    payload = (
                        HOLDINGS
                        if cash == 25
                        else HOLDINGS.replace(b"10,9,11.11", b"11,9,11.11")
                        .replace(b"30", b"31")
                        .replace(b"29-09-2026", b"30-09-2026")
                    )
                    result = await import_pair(
                        session, payload, ACTIVITY, as_of=dt.date(2026, 9, 30)
                    )
                    assert result["snapshot"] == ("unchanged" if index == 3 else "imported")
            batches = list(
                (await session.scalars(select(ImportBatch).order_by(ImportBatch.id))).all()
            )
            assert len(batches) == 3
            assert batches[0].file_sha256 == batches[2].file_sha256 != batches[1].file_sha256
            # Historical local inbox classification remains duplicate-safe even
            # when live observations legitimately share the same fingerprint.
            from app.services.import_service import import_holding_snapshot
            from app.services.trading212 import positions_to_rows

            reader = Reader()
            from app.services.hl_parser import parse_hl_holdings_csv_bytes

            if provider == "trading212":
                rows = positions_to_rows(
                    await reader.fetch_positions(),
                    await reader.fetch_account_summary(),
                    account_name="Trading 212",
                )
            else:
                rows, _ = parse_hl_holdings_csv_bytes(HOLDINGS)
            with pytest.raises(DuplicateImportError):
                await import_holding_snapshot(
                    session,
                    parsed_rows=rows,
                    as_of_date=dt.date(2026, 9, 29),
                    filename="synthetic-local",
                    file_sha256=batches[0].file_sha256,
                )
    finally:
        await engine.dispose()
