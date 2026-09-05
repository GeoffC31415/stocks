"""Typed, read-only data-confidence contracts, separate from the legacy schema module."""
import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import AllocationClassification, AnalysisScope, MetricReason


class AttentionItem(BaseModel):
    id: str
    category: Literal["fact", "rule"]
    severity: Literal["info", "warning", "critical"]
    title: str
    evidence: list[str]
    evidence_key: str
    action_href: str
    account_name: str | None
    period: str
    dismissible: bool


class TransactionCoverage(BaseModel):
    count: int
    first_date: dt.date | None
    last_date: dt.date | None
    unmatched_count: int
    review_count: int
    completeness: Literal["unknown"] = "unknown"


class SnapshotFreshness(BaseModel):
    account_name: str
    date: dt.date
    age_days: int


class MarketReadiness(BaseModel):
    covered_value_gbp: float
    non_cash_value_gbp: float
    covered_pct: float | None
    aligned_observations: int
    cache_gate_met: bool
    validation_pending: bool = True
    reasons: list[str]


class DataConfidence(BaseModel):
    scope: AnalysisScope
    evaluated_on: dt.date
    stale_after_days: int
    snapshots: list[SnapshotFreshness]
    transactions: TransactionCoverage
    classification: dict[str, AllocationClassification]
    market_history: MarketReadiness
    metric_reasons: list[MetricReason]
    attention: list[AttentionItem] = Field(default_factory=list)
