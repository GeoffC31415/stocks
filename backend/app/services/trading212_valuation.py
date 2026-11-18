"""Local bounds on a worker valuation, not a provider as-of or cash watermark."""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from app.models import ImportBatch

PORTFOLIO_FILENAME = "trading212-api-portfolio.json"


def utc(value: dt.datetime) -> dt.datetime:
    # SQLite returns our stored UTC datetimes without tzinfo.
    return value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value.astimezone(dt.UTC)


def ledger_scope(account_name: str) -> str:
    # Bind to the actual ledger key, without copying private labels into the diff.
    return hashlib.sha256(account_name.encode()).hexdigest()


@dataclass(frozen=True)
class ValuationObservation:
    key: ClassVar[str] = "trading212_valuation_observation_v1"
    positions_requested_at: dt.datetime
    account_summary_received_at: dt.datetime
    ledger_scope_sha256: str

    def metadata(self) -> dict[str, str]:
        return {
            "positions_requested_at": self.positions_requested_at.isoformat(),
            "account_summary_received_at": self.account_summary_received_at.isoformat(),
            "ledger_scope_sha256": self.ledger_scope_sha256,
        }

    @classmethod
    def from_batch(cls, batch: ImportBatch) -> ValuationObservation | None:
        summary = batch.diff_summary
        if (
            batch.filename != PORTFOLIO_FILENAME
            or not isinstance(summary, dict)
            or cls.key not in summary
        ):
            return None
        value = summary[cls.key]
        if not isinstance(value, dict):
            raise ValueError("Invalid valuation observation")

        def timestamp(key: str) -> dt.datetime:
            raw = value.get(key)
            if not isinstance(raw, str):
                raise ValueError("Missing valuation timestamp")
            parsed = dt.datetime.fromisoformat(raw)
            if parsed.utcoffset() != dt.timedelta(0) or parsed.isoformat() != raw:
                raise ValueError("Invalid UTC valuation timestamp")
            return parsed

        start = timestamp("positions_requested_at")
        end = timestamp("account_summary_received_at")
        if not (
            start.date() == end.date() == batch.as_of_date and start <= end <= utc(batch.created_at)
        ):
            raise ValueError("Inconsistent valuation observation")
        scope = value.get("ledger_scope_sha256")
        if not isinstance(scope, str) or len(scope) != 64:
            raise ValueError("Invalid ledger scope")
        return cls(start, end, scope)
