import datetime as dt
from typing import Literal

from pydantic import BaseModel

from app.schemas import AnalysisScope

TimelineSourceType = Literal["order", "import", "order-import"]
TimelineKind = Literal["trade", "deposit", "withdrawal", "transaction", "snapshot", "import"]


class TimelineEvent(BaseModel):
    id: str
    kind: TimelineKind
    date: dt.date
    occurred_at: dt.datetime | None
    valuation_date: dt.date | None
    account_names: list[str]
    instrument_id: int | None
    title: str
    amount_gbp: float | None
    source_type: TimelineSourceType
    source_id: int
    source_href: str
    details: dict[str, str | None]
    note: str


class TimelineResponse(BaseModel):
    scope: AnalysisScope
    events: list[TimelineEvent]
    event_count: int
    counts_by_kind: dict[str, int]
    notes: list[str]
