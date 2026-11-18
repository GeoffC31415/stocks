"""Synthetic position identity tests, including combined-sync persistence."""

import copy

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlite_schema import create_file_schema

from app.models import Base, HoldingSnapshot, ImportBatch, Instrument
from app.routers.trading212 import _provider_error, run_trading212_sync
from app.services.trading212 import (
    Trading212Client,
    Trading212DataError,
    positions_to_rows,
    trading212_diagnostic,
)


@pytest.fixture
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'identity.sqlite3'}")
    await create_file_schema(engine)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def persisted_state(db):
    # A separate file-backed connection reads durable data, never stale ORM objects.
    async with async_sessionmaker(db.bind, expire_on_commit=False)() as reader:
        return {
            table.name: [tuple(row) for row in (await reader.execute(select(table))).all()]
            for table in Base.metadata.sorted_tables
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        *(
            pytest.param("isin", value, id=f"isin-{index}")
            for index, value in enumerate(
                ([], ["ONE"], {}, {"isin": "ONE"}, 0, 1, False, True, 0.0, 1.5)
            )
        ),
        *(
            pytest.param("name", value, id=f"name-{index}")
            for index, value in enumerate(([], ["One"], {}, {"name": "One"}, 0, 1, False, True))
        ),
        *(
            pytest.param(field, value, id=f"{field}-{index}")
            for field in ("ticker-for-isin", "ticker-for-name")
            for index, value in enumerate(([], ["ONE"], {}, {"ticker": "ONE"}, 0, 1, False, True))
        ),
        *(
            pytest.param("instrument", value, id=f"instrument-{index}")
            for index, value in enumerate((None, [], ["ONE"], {}, "bad", 0, 1, False, True))
        ),
        pytest.param("identity-and-wallet", ["ONE"], id="bad-identity-and-wallet"),
        *(
            pytest.param("wallet-impact", value, id=f"bad-wallet-{index}")
            for index, value in enumerate(
                (["not-an-object"], [], "not-an-object", 0, 1, False, True)
            )
        ),
    ],
)
async def test_malformed_identity_never_closes_an_existing_position(db, field, bad_value):
    position = {
        "instrument": {"isin": "ONE", "ticker": "ONE_TICKER", "name": "One", "currency": "GBP"},
        "quantity": 1,
        "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
    }
    other = copy.deepcopy(position)
    other["instrument"].update(isin="TWO", ticker="TWO_TICKER", name="Two")
    payloads = {
        "/api/v0/equity/positions": [other, position],
        "/api/v0/equity/account/summary": {
            "currency": "GBP",
            "cash": {"availableToTrade": 25, "inPies": 0, "reservedForOrders": 0},
        },
        "/api/v0/equity/history/orders": {"items": [], "nextPagePath": None},
        "/api/v0/equity/history/transactions": {
            "items": [
                {
                    "reference": "deposit",
                    "type": "DEPOSIT",
                    "amount": 10,
                    "currency": "GBP",
                    "dateTime": "2026-01-01T12:00:00Z",
                }
            ],
            "nextPagePath": None,
        },
    }
    client = Trading212Client(
        api_key="SYNTHETIC_KEY",
        api_secret="SYNTHETIC_SECRET",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payloads[request.url.path])
        ),
        page_delay=0,
    )
    await run_trading212_sync(db, client)
    before = await persisted_state(db)
    baseline = await db.scalar(select(Instrument).where(Instrument.identifier == "ONE"))
    assert baseline is not None and baseline.closed_at is None
    assert await db.scalar(select(HoldingSnapshot.id)) is not None
    assert await db.scalar(select(ImportBatch.id)) is not None

    corrupted = copy.deepcopy(position)
    if field == "instrument":
        corrupted["instrument"] = bad_value
    elif field == "identity-and-wallet":
        corrupted["instrument"]["isin"] = bad_value
        corrupted["walletImpact"] = ["not-an-object"]
    elif field == "wallet-impact":
        corrupted["walletImpact"] = bad_value
    elif field.startswith("ticker-for-"):
        corrupted["instrument"][field.removeprefix("ticker-for-")] = None
        corrupted["instrument"]["ticker"] = bad_value
    else:
        corrupted["instrument"][field] = bad_value
    expected_code = (
        "invalid_position_numbers" if field == "wallet-impact" else "invalid_position_identity"
    )
    # A valid row precedes the corrupted row; no partial snapshot may survive.
    payloads["/api/v0/equity/positions"] = [other, corrupted]
    payloads["/api/v0/equity/account/summary"]["cash"]["availableToTrade"] = 30
    with pytest.raises(Trading212DataError) as rejected:
        await run_trading212_sync(db, client)
    assert rejected.value.code == expected_code
    assert rejected.value.t212_endpoint == "positions"
    assert rejected.value.t212_phase == "import"
    assert trading212_diagnostic(rejected.value) == (
        expected_code,
        "positions",
        "import",
        None,
    )
    # Even a subsequent caller commit must not persist any failed-sync writes.
    await db.commit()
    assert await persisted_state(db) == before


@pytest.mark.parametrize("bad_name", [[], ["One"], {}, {"name": "One"}, 0, 1, False, True])
def test_non_string_position_name_cannot_be_coerced_or_fallback(bad_name):
    position = {
        "instrument": {"isin": "ONE", "ticker": "ONE_TICKER", "name": bad_name},
        "quantity": 1,
        "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
    }
    with pytest.raises(Trading212DataError) as rejected:
        positions_to_rows([position], {"currency": "GBP"}, account_name="Trading 212")
    assert rejected.value.code == "invalid_position_identity"


@pytest.mark.parametrize(
    "bad_ticker", [[], ["TICKER"], {}, {"ticker": "TICKER"}, 0, 1, False, True]
)
@pytest.mark.parametrize("fallback_field", ["isin", "name"])
def test_non_string_ticker_is_rejected_when_needed_for_identity(bad_ticker, fallback_field):
    instrument = {"isin": "ONE", "ticker": bad_ticker, "name": "One"}
    instrument[fallback_field] = None
    position = {
        "instrument": instrument,
        "quantity": 1,
        "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
    }
    with pytest.raises(Trading212DataError) as rejected:
        positions_to_rows([position], {"currency": "GBP"}, account_name="Trading 212")
    assert rejected.value.code == "invalid_position_identity"


@pytest.mark.parametrize("bad_instrument", [None, [], [1], "instrument", 0, 1, False, True])
def test_non_mapping_instrument_is_a_classified_identity_error(bad_instrument):
    position = {
        "instrument": bad_instrument,
        "quantity": 1,
        "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
    }
    with pytest.raises(Trading212DataError) as rejected:
        positions_to_rows([position], {"currency": "GBP"}, account_name="Trading 212")
    assert rejected.value.code == "invalid_position_identity"


@pytest.mark.parametrize("fallback_field", ["isin", "name"])
@pytest.mark.parametrize("absent_value", [None, "", "MISSING"])
def test_missing_identity_fields_use_valid_ticker_without_extra_aliases(
    fallback_field, absent_value
):
    instrument = {"isin": "ONE", "name": "One", "ticker": " ONE_TICKER ", "currency": "GBP"}
    if absent_value == "MISSING":
        instrument.pop(fallback_field)
    else:
        instrument[fallback_field] = absent_value
    position = {
        "instrument": instrument,
        "quantity": 1,
        "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
    }
    (row,) = positions_to_rows([position], {"currency": "GBP"}, account_name="Trading 212")
    assert row.identifier == ("ONE_TICKER" if fallback_field == "isin" else "ONE")
    assert row.investment == ("ONE_TICKER" if fallback_field == "name" else "One")


@pytest.mark.parametrize("field", ["isin", "name"])
def test_whitespace_only_preferred_identity_does_not_fallback(field):
    instrument = {"isin": "ONE", "name": "One", "ticker": "ONE_TICKER"}
    instrument[field] = "  "
    position = {
        "instrument": instrument,
        "quantity": 1,
        "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
    }
    with pytest.raises(Trading212DataError) as rejected:
        positions_to_rows([position], {"currency": "GBP"}, account_name="Trading 212")
    assert rejected.value.code == "invalid_position_identity"


def test_zero_values_and_numeric_strings_keep_existing_position_semantics():
    position = {
        "instrument": {"isin": "ONE", "name": "One"},
        "quantity": "0",
        "walletImpact": {"currency": "GBP", "currentValue": 0, "totalCost": "0"},
    }
    (row,) = positions_to_rows([position], {"currency": "GBP"}, account_name="Trading 212")
    assert (row.quantity, row.value_gbp, row.book_cost_gbp, row.pct_change) == (0, 0, 0, None)


@pytest.mark.parametrize("field", ["quantity", "currentValue", "totalCost"])
@pytest.mark.parametrize("bad_number", [None, True, False, "not-a-number", "nan", "inf", [], {}])
def test_invalid_required_position_numbers_keep_existing_rejection(field, bad_number):
    position = {
        "instrument": {"isin": "ONE", "name": "One"},
        "quantity": 1,
        "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
    }
    (position if field == "quantity" else position["walletImpact"])[field] = bad_number
    with pytest.raises(Trading212DataError) as rejected:
        positions_to_rows([position], {"currency": "GBP"}, account_name="Trading 212")
    assert rejected.value.code == "invalid_position_numbers"


@pytest.mark.asyncio
@pytest.mark.parametrize("isin_variant", [None, "", "MISSING"])
async def test_real_client_accepts_ticker_fallback_and_unknown_fields(db, isin_variant):
    position = {
        "instrument": {"isin": None, "ticker": "ONE_TICKER", "name": "One", "currency": "GBP"},
        "quantity": 1,
        "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
    }
    payloads = {
        "/api/v0/equity/positions": [position],
        "/api/v0/equity/account/summary": {
            "currency": "GBP",
            "cash": {"availableToTrade": 25, "inPies": 0, "reservedForOrders": 0},
        },
        "/api/v0/equity/history/orders": {"items": [], "nextPagePath": None},
        "/api/v0/equity/history/transactions": {"items": [], "nextPagePath": None},
    }
    client = Trading212Client(
        api_key="SYNTHETIC_KEY",
        api_secret="SYNTHETIC_SECRET",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payloads[request.url.path])
        ),
        page_delay=0,
    )
    assert (await run_trading212_sync(db, client)).snapshot == "imported"
    if isin_variant == "MISSING":
        position["instrument"].pop("isin")
    else:
        position["instrument"]["isin"] = isin_variant
    position["unknown"] = {"future": [1, "x"]}
    position["instrument"]["unknown"] = ["future"]
    position["walletImpact"]["unknown"] = {"future": True}
    payloads["/api/v0/equity/account/summary"]["unknown"] = "future"
    # An unchanged null ISIN plus extras is the same observation; changing a
    # documented identifier field (null to missing/empty) still retains evidence.
    expected = "unchanged" if isin_variant is None else "imported"
    assert (await run_trading212_sync(db, client)).snapshot == expected
    db.expire_all()
    instruments = (await db.scalars(select(Instrument))).all()
    assert {instrument.identifier for instrument in instruments} == {"ONE_TICKER", "CASH"}
    assert all(instrument.closed_at is None for instrument in instruments)
    latest = await db.scalar(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
    assert latest.diff_summary["closed"] == []
    assert set(
        (
            await db.scalars(
                select(Instrument.identifier)
                .join(HoldingSnapshot)
                .where(HoldingSnapshot.import_batch_id == latest.id)
            )
        ).all()
    ) == {"ONE_TICKER", "CASH"}


def test_malformed_identity_diagnostics_are_accurate_and_do_not_leak(caplog):
    sentinel = "PRIVATE_PROVIDER_VALUE_SENTINEL"
    position = {
        "instrument": {"isin": [sentinel], "ticker": "TICKER", "name": "One"},
        "quantity": 1,
        "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
    }
    with pytest.raises(Trading212DataError) as rejected:
        positions_to_rows([position], {"currency": "GBP"}, account_name="Trading 212")
    response = _provider_error(rejected.value, operation="positions")
    assert response.status_code == 400
    assert response.detail == "Trading 212 validation failed (invalid_position_identity)."
    assert "code=invalid_position_identity endpoint=positions phase=import" in caplog.text
    assert "identifier or name is missing or invalid" in caplog.text
    assert sentinel not in caplog.text
    assert sentinel not in str(rejected.value)
    assert all(record.exc_info is None for record in caplog.records)
