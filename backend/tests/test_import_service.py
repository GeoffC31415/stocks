import datetime as dt
from typing import Any

import app.routers.imports as imports_router
import pytest
from app.models import ImportBatch, Instrument
from app.services.barclays_parser import ParsedHoldingRow
from app.services.hl_parser import HL_ACCOUNT_NAME
from app.services.import_service import import_holding_snapshot
from app.services.portfolio_service import portfolio_value_timeseries
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


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


async def _import_hl_after_barclays(
    async_session: AsyncSession,
) -> tuple[Instrument, dict[str, Any], list[dict[str, Any]]]:
    await import_holding_snapshot(
        async_session,
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
        async_session,
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
        await async_session.execute(
            select(Instrument).where(
                Instrument.account_name == "Barclays ISA",
                Instrument.identifier == "VWRL",
            )
        )
    ).scalar_one()
    timeseries = await portfolio_value_timeseries(async_session)

    return barclays, summary, timeseries


async def test_importing_hl_snapshot_does_not_close_barclays_instruments(
    async_session: AsyncSession,
) -> None:
    barclays, summary, _ = await _import_hl_after_barclays(async_session)

    assert barclays.closed_at is None
    assert summary["closed"] == []


async def test_portfolio_timeseries_carries_forward_other_account_snapshots(
    async_session: AsyncSession,
) -> None:
    _, _, timeseries = await _import_hl_after_barclays(async_session)

    assert [row["total_value_gbp"] for row in timeseries] == [1000.0, 3000.0]


async def test_create_import_endpoint_uses_overridden_session(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_import_barclays_xls(
        session: AsyncSession,
        *,
        file_bytes: bytes,
        filename: str | None,
        as_of_date: dt.date | None,
        file_metadata_as_of: dt.date | None = None,
        force: bool = False,
    ) -> tuple[ImportBatch, dict[str, Any]]:
        batch = ImportBatch(
            as_of_date=as_of_date or file_metadata_as_of or dt.date(2026, 5, 4),
            file_sha256="fake-sha",
            filename=filename,
            diff_summary={"row_count": 0},
        )
        session.add(batch)
        await session.flush()
        return batch, {"row_count": 0, "force": force, "bytes": len(file_bytes)}

    monkeypatch.setattr(imports_router, "import_barclays_xls", fake_import_barclays_xls)

    response = await client.post(
        "/api/imports",
        data={"as_of_date": "2026-05-04", "force": "true"},
        files={"file": ("snapshot.xls", b"synthetic workbook bytes", "application/vnd.ms-excel")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["batch"]["filename"] == "snapshot.xls"
    assert payload["batch"]["as_of_date"] == "2026-05-04"
    assert payload["summary"] == {"row_count": 0, "force": True, "bytes": 24}
