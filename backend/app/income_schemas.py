import datetime as dt
from typing import Literal

from pydantic import BaseModel, FiniteFloat


class IncomeMonth(BaseModel):
    month: int
    current_recorded_gbp: FiniteFloat | None
    prior_recorded_gbp: FiniteFloat | None
    current_count: int
    prior_count: int


class IncomeDriver(BaseModel):
    key: str
    instrument_id: int | None
    account_name: str
    navigation_account: str
    name: str
    holding_status: Literal["current", "closed", "unlinked"]
    current_recorded_gbp: FiniteFloat | None
    prior_recorded_gbp: FiniteFloat | None
    change_gbp: FiniteFloat | None
    order_ids: list[int]


class IncomeAnalysis(BaseModel):
    account_name: str | None
    as_of: dt.date
    current_start: dt.date
    prior_start: dt.date
    prior_end: dt.date
    first_transaction_date: dt.date | None
    latest_transaction_date: dt.date | None
    basis: str = "stored_import_classification"
    completeness: str = "unknown"
    current_recorded_gbp: FiniteFloat | None
    prior_recorded_gbp: FiniteFloat | None
    change_gbp: FiniteFloat | None
    current_count: int
    prior_count: int
    warnings: list[str]
    months: list[IncomeMonth]
    drivers: list[IncomeDriver]
