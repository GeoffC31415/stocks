from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from app.allocation_target_schemas import AllocationTargets


class ContributionAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: int = Field(gt=0, strict=True)
    amount_gbp: FiniteFloat = Field(ge=0, le=1e12)


class ContributionScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contribution_gbp: FiniteFloat = Field(ge=0, le=1e12)
    allocations: list[ContributionAllocation] = Field(max_length=100)
    cash_policy: Literal["excluded"]


class ContributionResult(BaseModel):
    before: AllocationTargets
    after: AllocationTargets
    contribution_gbp: FiniteFloat
    assumption: str = "Hypothetical contribution; no orders created. Real cash is unchanged."
