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


class ImportChangedEntry(BaseModel):
    instrument_id: int
    identifier: str
    account_name: str
    security_name: str | None = None
    quantity_before: float | None = None
    quantity_after: float | None = None
    value_before: float | None = None
    value_after: float | None = None
    delta_value_gbp: float | None = None


class ImportClosedEntry(BaseModel):
    instrument_id: int
    identifier: str
    account_name: str
    security_name: str


class ImportDiffSummary(BaseModel):
    batch_id: int
    as_of_date: dt.date
    previous_batch_id: int | None = None
    previous_as_of_date: dt.date | None = None
    new_instrument_ids: list[int] = Field(default_factory=list)
    closed: list[ImportClosedEntry] = Field(default_factory=list)
    changed: list[ImportChangedEntry] = Field(default_factory=list)
    row_count: int | None = None
    orders_linked: int | None = None


class SnapshotDiffRow(BaseModel):
    instrument_id: int
    identifier: str
    security_name: str
    account_name: str
    quantity_from: float | None = None
    quantity_to: float | None = None
    delta_quantity: float | None = None
    value_from_gbp: float | None = None
    value_to_gbp: float | None = None
    delta_value_gbp: float | None = None
    price_from: float | None = None
    price_to: float | None = None
    delta_price: float | None = None
    weight_from_pct: float | None = None
    weight_to_pct: float | None = None
    delta_weight_pct: float | None = None
    status: str


class SnapshotDiffResponse(BaseModel):
    from_batch: ImportBatchOut
    to_batch: ImportBatchOut
    rows: list[SnapshotDiffRow]


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
    ticker: str | None = None
    sector: str | None = None
    region: str | None = None
    asset_class: str | None = None
    closed_at: dt.datetime | None
    latest_value_gbp: float | None = None
    latest_book_cost_gbp: float | None = None
    latest_pct_change: float | None = None
    pnl_gbp: float | None = None
    latest_quote_price_gbp: float | None = None
    latest_quote_as_of_date: dt.date | None = None
    latest_quote_fetched_at: dt.datetime | None = None
    snapshot_as_of_date: dt.date | None = None
    trailing_drip_yield_pct: float | None = None
    delta_value_gbp_since_prev_snapshot: float | None = None
    delta_quantity_since_prev_snapshot: float | None = None
    peak_value_gbp: float | None = None
    peak_last_price: float | None = None
    drawdown_from_peak_pct: float | None = None
    quantity_unchanged_snapshot_count: int | None = None
    group_ids: list[int] = Field(default_factory=list)


class InstrumentHistoryPoint(BaseModel):
    as_of_date: dt.date
    value_gbp: float | None
    book_cost_gbp: float | None
    discretionary_cost_basis_gbp: float | None = None
    quantity: float | None
    pct_change: float | None


class AllocationRow(BaseModel):
    label: str
    kind: str
    value_gbp: float
    weight_pct: float
    target_pct: float | None = None
    drift_pct: float | None = None
    is_concentration_risk: bool = False


class PortfolioSummary(BaseModel):
    as_of_date: dt.date | None
    import_batch_id: int | None
    total_value_gbp: float
    total_book_cost_gbp: float
    total_pnl_gbp: float
    by_account: dict[str, float]
    by_group: dict[str, float]
    allocation: list[AllocationRow] = Field(default_factory=list)
    group_allocation: list[AllocationRow] = Field(default_factory=list)
    worst_pct: list[InstrumentOut]
    best_pct: list[InstrumentOut]


class InstrumentGroupCreate(BaseModel):
    name: str
    color: str | None = None
    target_allocation_pct: float | None = Field(default=None, ge=0, le=100)


class InstrumentGroupPatch(BaseModel):
    name: str | None = None
    color: str | None = None
    target_allocation_pct: float | None = Field(default=None, ge=0, le=100)


class InstrumentGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None
    target_allocation_pct: float | None = None
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


class UnlinkedOrdersResponse(BaseModel):
    count: int
    orders: list[OrderOut]


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
    trailing_drip_yield_pct: float | None = None
    realized_pnl_gbp: float | None
    is_closed: bool


class EstimatedTimeseriesPoint(BaseModel):
    month: str
    estimated_value_gbp: float


class BenchmarkPoint(BaseModel):
    date: dt.date
    symbol: str
    close: float
    rebased_value: float


class InstrumentQuoteOut(BaseModel):
    instrument_id: int
    ticker: str
    price_gbp: float | None = None
    price_ccy: str | None = None
    as_of_date: dt.date | None = None
    fetched_at: dt.datetime | None = None


class InstrumentMarketPatch(BaseModel):
    ticker: str | None = None
    sector: str | None = None
    region: str | None = None
    asset_class: str | None = None


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
