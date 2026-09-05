"""Cash-excluded exclusive target-set response contracts."""

from typing import Literal

from pydantic import BaseModel, FiniteFloat


class TargetGroup(BaseModel):
    group_id: int
    name: str
    instrument_ids: list[int]
    actual_value_gbp: FiniteFloat
    actual_weight_pct: FiniteFloat | None
    target_weight_pct: FiniteFloat | None
    drift_pp: FiniteFloat | None
    gap_gbp: FiniteFloat | None
    within_tolerance: bool | None


class AllocationTargets(BaseModel):
    status: Literal["available", "unavailable"]
    account_name: str | None
    invested_value_gbp: FiniteFloat
    excluded_cash_gbp: FiniteFloat | None
    tolerance_pp: FiniteFloat
    target_sum_tolerance_pp: float = 0.01
    cash_policy: str = "Excluded; positive current non-cash GBP values form the denominator."
    reasons: list[str]
    groups: list[TargetGroup]
