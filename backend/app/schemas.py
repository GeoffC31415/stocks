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


class OrderImportBatchOut(BaseModel):
    id: int
    created_at: dt.datetime
    filename: str | None
    row_count: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    security_name: str
    instrument_id: int | None = None
    order_date: dt.datetime
    order_status: str
    account_name: str
    side: str
    quantity: float | None
    cost_proceeds_gbp: float | None
    country: str | None
    is_drip: bool


class AnnualDripPoint(BaseModel):
    year: int
    total_gbp: float


class OrderAnalytics(BaseModel):
    total_orders: int
    total_buy_gbp: float
    total_drip_gbp: float
    total_sell_gbp: float
    cash_deployed_gbp: float
    net_cash_invested_gbp: float
    drip_count: int
    buy_count: int
    sell_count: int
    drip_threshold_gbp: float
    annual_drip: list[AnnualDripPoint]
    first_order_date: str | None = None


class CashflowPoint(BaseModel):
    month: str
    monthly_discretionary: float
    monthly_drip: float
    monthly_sells: float
    cumulative_net_deployed: float
    cumulative_drip: float
    cumulative_sells: float


class PositionSummary(BaseModel):
    security_name: str
    instrument_id: int | None = None
    total_buy_gbp: float
    discretionary_buy_gbp: float
    total_drip_gbp: float
    total_sell_gbp: float
    net_cost_gbp: float
    order_count: int
    drip_count: int
    first_order_date: str
    last_order_date: str
    current_value_gbp: float | None
    estimated_pnl_gbp: float | None
    annualised_return_pct: float | None
    realized_pnl_gbp: float | None
    is_closed: bool


class EstimatedTimeseriesPoint(BaseModel):
    month: str
    estimated_value_gbp: float


class GroupPerformanceTimeseriesPoint(BaseModel):
    as_of_date: dt.date
    value_gbp: float
    book_cost_gbp: float


class GroupPerformanceMember(BaseModel):
    instrument_id: int
    security_name: str
    identifier: str
    current_value_gbp: float | None
    net_cost_gbp: float
    pnl_gbp: float | None
    annualised_return_pct: float | None
    weight_pct: float | None
    first_order_date: str | None


class GroupPerformance(BaseModel):
    group_id: int
    name: str
    color: str | None
    member_count: int
    members_with_value: int
    total_current_value_gbp: float
    total_net_cost_gbp: float
    total_pnl_gbp: float
    pnl_pct: float | None
    combined_cagr_pct: float | None
    weighted_cagr_pct: float | None
    earliest_order_date: str | None
    timeseries: list[GroupPerformanceTimeseriesPoint]
    members: list[GroupPerformanceMember]
