from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: dt.datetime
    as_of_date: dt.date
    file_sha256: str
    filename: str | None
    diff_summary: dict[str, Any] | None


class ImportResult(BaseModel):
    batch: ImportBatchOut
    summary: dict[str, Any]


class HoldingSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    import_batch_id: int
    investment_label: str
    quantity: float | None
    value_gbp: float | None
    book_cost_gbp: float | None
    pct_change: float | None
    last_price: float | None


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_name: str
    identifier: str
    security_name: str
    is_cash: bool
    closed_at: dt.datetime | None
    latest_value_gbp: float | None = None
    latest_book_cost_gbp: float | None = None
    latest_pct_change: float | None = None
    pnl_gbp: float | None = None
    group_ids: list[int] = Field(default_factory=list)


class InstrumentHistoryPoint(BaseModel):
    as_of_date: dt.date
    value_gbp: float | None
    book_cost_gbp: float | None
    quantity: float | None
    pct_change: float | None


class PortfolioSummary(BaseModel):
    as_of_date: dt.date | None
    import_batch_id: int | None
    total_value_gbp: float
    total_book_cost_gbp: float
    total_pnl_gbp: float
    by_account: dict[str, float]
    by_group: dict[str, float]
    worst_pct: list[InstrumentOut]
    best_pct: list[InstrumentOut]


class InstrumentGroupCreate(BaseModel):
    name: str
    color: str | None = None


class InstrumentGroupPatch(BaseModel):
    name: str | None = None
    color: str | None = None


class InstrumentGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None
    member_count: int = 0
    total_value_gbp: float | None = None


class GroupMembersBody(BaseModel):
    instrument_ids: list[int]
