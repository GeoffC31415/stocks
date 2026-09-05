"""Pure user-specified contribution calculation, never an optimiser."""

from decimal import Decimal

from app.allocation_scenario_schemas import ContributionResult, ContributionScenario
from app.allocation_target_schemas import AllocationTargets


def calculate_scenario(
    before: AllocationTargets, scenario: ContributionScenario
) -> ContributionResult:
    if before.status != "available":
        raise ValueError("Target set unavailable: " + "; ".join(before.reasons))
    ids = [a.group_id for a in scenario.allocations]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate allocation group IDs are not allowed.")
    if set(ids) - {g.group_id for g in before.groups}:
        raise ValueError("Allocations must name eligible target groups.")
    amounts_decimal = [Decimal(str(a.amount_gbp)) for a in scenario.allocations]
    contribution_decimal = Decimal(str(scenario.contribution_gbp))
    if any(v != v.quantize(Decimal("0.01")) for v in [*amounts_decimal, contribution_decimal]):
        raise ValueError("Contribution and allocations must use whole pennies.")
    if sum(amounts_decimal, Decimal(0)) != contribution_decimal:
        raise ValueError("Allocations must sum to the contribution (GBP, exact to pennies).")
    after = before.model_copy(deep=True)
    after.invested_value_gbp += scenario.contribution_gbp
    amounts = {a.group_id: a.amount_gbp for a in scenario.allocations}
    for row in after.groups:
        row.actual_value_gbp += amounts.get(row.group_id, 0)
        row.actual_weight_pct = row.actual_value_gbp / after.invested_value_gbp * 100
        target = row.target_weight_pct or 0
        row.drift_pp = row.actual_weight_pct - target
        row.gap_gbp = after.invested_value_gbp * target / 100 - row.actual_value_gbp
        row.within_tolerance = abs(row.drift_pp) <= after.tolerance_pp
    return ContributionResult(
        before=before, after=after, contribution_gbp=scenario.contribution_gbp
    )
