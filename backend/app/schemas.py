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


class OrderInstrumentRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    security_name: str
    identifier: str


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    security_name: str
    instrument_id: int | None = None
    instrument: OrderInstrumentRef | None = None
    order_date: dt.datetime
    order_status: str
    account_name: str
    side: str
    quantity: float | None
    cost_proceeds_gbp: float | None
    country: str | None
    is_drip: bool
    match_status: str | None = None
    match_method: str | None = None
    match_confidence: float | None = None
    matched_at: dt.datetime | None = None


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


# ---------------------------------------------------------------------------
# Matching admin schemas
# ---------------------------------------------------------------------------

class AccountAliasIn(BaseModel):
    source: str
    source_account_name: str
    canonical_account_name: str
    notes: str | None = None


class AccountAliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_account_name: str
    canonical_account_name: str
    created_at: dt.datetime
    created_by: str | None = None
    notes: str | None = None


class InstrumentAliasIn(BaseModel):
    instrument_id: int
    source: str
    source_account_name: str | None = None
    canonical_account_name: str | None = None
    source_security_name: str
    alias_type: str = "manual"
    confidence: float | None = None
    notes: str | None = None


class InstrumentAliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instrument_id: int
    source: str
    source_account_name: str | None = None
    canonical_account_name: str | None = None
    source_security_name: str
    source_security_name_norm: str
    alias_type: str
    confidence: float | None = None
    created_at: dt.datetime
    created_by: str | None = None
    notes: str | None = None


class OrderMatchAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    old_instrument_id: int | None = None
    new_instrument_id: int | None = None
    old_status: str | None = None
    new_status: str | None = None
    method: str | None = None
    confidence: float | None = None
    evidence: dict[str, Any] | None = None
    changed_at: dt.datetime
    changed_by: str | None = None
    reason: str | None = None


class MatchSummary(BaseModel):
    orders_total: int
    orders_matched: int
    orders_unmatched: int
    orders_auto_high: int
    orders_auto_review: int
    orders_manual: int
    orders_ignored: int
    orders_legacy: int = 0
    unmatched_groups: int
    instruments_with_reconciliation_issues: int = 0


class MatchCandidate(BaseModel):
    instrument_id: int
    security_name: str
    score: float
    method: str | None = None


class UnmatchedGroup(BaseModel):
    group_key: str
    source: str
    account_name: str
    canonical_account_name: str | None = None
    security_name: str
    normalised_name: str
    order_count: int
    first_order_date: str | None = None
    last_order_date: str | None = None
    net_quantity: float | None = None
    buy_total_gbp: float | None = None
    sell_total_gbp: float | None = None
    candidate_count: int = 0
    best_candidate: MatchCandidate | None = None


class ResolveGroupBody(BaseModel):
    source: str
    account_name: str
    security_name: str
    instrument_id: int
    create_alias: bool = True
    apply_to_existing_orders: bool = True
    reason: str | None = None


class ResolveOrderBody(BaseModel):
    instrument_id: int | None = None
    match_status: str | None = None
    reason: str | None = None


class BackfillRequest(BaseModel):
    mode: str = "unmatched_only"
    dry_run: bool = True
    min_auto_confidence: float = 0.92
    include_review_candidates: bool = True


class BackfillResult(BaseModel):
    dry_run: bool
    orders_examined: int
    would_auto_match: int = 0
    would_mark_review: int = 0
    would_remain_unmatched: int = 0
    actually_linked: int = 0
    examples: list[dict[str, Any]] = Field(default_factory=list)


class ReconciliationRow(BaseModel):
    instrument_id: int
    security_name: str
    account_name: str
    is_closed: bool
    latest_snapshot_date: str | None = None
    snapshot_quantity: float | None = None
    order_derived_quantity: float | None = None
    quantity_delta: float | None = None
    snapshot_book_cost_gbp: float | None = None
    order_net_cost_gbp: float | None = None
    drip_total_gbp: float | None = None
    buy_total_gbp: float | None = None
    sell_total_gbp: float | None = None
    unmatched_order_count: int = 0
    matched_order_count: int = 0
    match_status_summary: dict[str, int] = Field(default_factory=dict)
    latest_value_gbp: float | None = None
    status: str = "ok"


class CreateHistoricalInstrumentBody(BaseModel):
    """Create a new instrument for historical/order-only securities."""
    security_name: str
    account_name: str | None = None
    identifier: str | None = None  # optional real identifier; auto-generated if omitted
    closed: bool = True  # historical instruments are closed by default
    reason: str | None = None


# ---------------------------------------------------------------------------
# CGT schemas
# ---------------------------------------------------------------------------

class CGTMismatchEntry(BaseModel):
    source: str  # "same_day", "b&f", "pool"
    order_id: int | None = None
    order_date: str | None = None
    security_name: str | None = None
    quantity: float = 0.0
    cost: float = 0.0
    proceeds: float = 0.0


class CGTSaleDetail(BaseModel):
    order_id: int
    order_date: str
    quantity: float
    proceeds_gbp: float
    total_cost: float
    realised_gain: float
    matches: list[CGTMismatchEntry] = Field(default_factory=list)
    pool_quantity_before: float = 0.0
    pool_cost_before: float = 0.0


class CGTTaxYearSummary(BaseModel):
    tax_year: str  # e.g. "2023-24"
    year_end: int
    total_proceeds: float
    total_cost: float
    total_gain: float
    total_loss: float
    gain_count: int
    loss_count: int


class CGTInstrumentSummary(BaseModel):
    instrument_id: int
    security_name: str
    identifier: str
    account_name: str
    is_exempt: bool = False
    total_proceeds_gbp: float
    total_cost_gbp: float
    total_gain_gbp: float
    total_loss_gbp: float
    net_gain_gbp: float
    tax_year_summaries: list[CGTTaxYearSummary] = Field(default_factory=list)
    sales: list[CGTSaleDetail] = Field(default_factory=list)


class CGTTaxYearTotals(BaseModel):
    tax_year: str
    # Taxable (non-ISA) amounts
    taxable_proceeds: float
    taxable_cost: float
    taxable_gain: float
    taxable_loss: float
    exempt_proceeds: float
    exempt_cost: float
    exempt_gain: float
    exempt_loss: float
    gain_count: int
    loss_count: int
    instrument_count: int
    exempt_count: int = 0


class CGTSummaryResponse(BaseModel):
    instruments: list[CGTInstrumentSummary] = Field(default_factory=list)
    tax_year_totals: list[CGTTaxYearTotals] = Field(default_factory=list)

