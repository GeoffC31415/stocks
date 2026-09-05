"""GBP-weighted allocation matching the legacy TS calculator's rounded weights.

Cash is excluded in every dimension. Currency is the snapshot's source value
currency, not a fund's underlying currency exposure. Latest snapshot selection
is shared with portfolio_service, including independent account imports.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas import AllocationDimension, AllocationGrouping
from app.services.portfolio_service import get_current_snapshots
from app.services.security_identity_service import security_identity


def _round(value: float) -> float:
    """Match JS Math.round for nonnegative allocation values (not bankers' rounding)."""
    if not math.isfinite(value * 100):
        raise ValueError("non-finite allocation value or rounding overflow")
    return math.floor(value * 100 + 0.5) / 100


async def get_allocation(
    session: AsyncSession,
    *,
    dimension: AllocationDimension = "asset_class",
    account_name: str | None = None,
    group_by: AllocationGrouping = "security",
) -> dict:
    snapshots = [
        s
        for s in await get_current_snapshots(session)
        if not s.instrument.is_cash
        and (account_name is None or s.instrument.account_name == account_name)
    ]
    if any(not math.isfinite(s.value_gbp or 0) for s in snapshots):
        raise ValueError("non-finite holding value in allocation scope")
    snapshots = [s for s in snapshots if (s.value_gbp or 0) > 0]
    total = sum(s.value_gbp or 0 for s in snapshots)
    if not math.isfinite(total):
        raise ValueError("non-finite allocation total")
    weights = [_round((s.value_gbp or 0) / total * 100) for s in snapshots]
    holdings = [
        {
            "id": s.instrument.id,
            "identifier": s.instrument.identifier,
            "label": s.instrument.security_name,
            "value": _round(s.value_gbp or 0),
            "weightPct": weight,
        }
        for s, weight in zip(snapshots, weights, strict=True)
    ]
    exposure: dict[str, dict] = {}
    for snapshot, holding in zip(snapshots, holdings, strict=True):
        identity = security_identity(snapshot.instrument, snapshot.value_ccy)
        key = identity["security_key"] if group_by == "security" else f"position:{holding['id']}"
        row = exposure.setdefault(key, {
            **holding, **identity, "value": 0, "constituents": [],
        })
        row["value"] += snapshot.value_gbp or 0
        row["constituents"].append({
            **holding, "account_name": snapshot.instrument.account_name,
            "ticker": snapshot.instrument.ticker, "source_currency": snapshot.value_ccy,
        })
    grouped_holdings = sorted(exposure.values(), key=lambda row: -row["value"])
    for row in grouped_holdings:
        row["weightPct"] = _round(row["value"] / total * 100)
        row["value"] = _round(row["value"])
    weights = [row["weightPct"] for row in grouped_holdings]
    grouped: dict[str, dict] = {}
    category_instruments: dict[str, list[int]] = {}
    classified_count = 0
    classified_value = 0.0
    for s in snapshots:
        raw = (
            s.instrument.account_name
            if dimension == "account"
            else s.value_ccy
            if dimension == "currency"
            else getattr(s.instrument, dimension)
        )
        label = (raw or "").strip() or "Unclassified"
        category_instruments.setdefault(label, []).append(s.instrument_id)
        if label != "Unclassified":
            classified_count += 1
            classified_value += s.value_gbp or 0
        category = grouped.setdefault(label, {"label": label, "value": 0, "count": 0})
        category["value"] += s.value_gbp or 0
        category["count"] += 1
    categories = sorted(
        [
            {**row, "value": _round(row["value"]), "weightPct": _round(row["value"] / total * 100)}
            for row in grouped.values()
        ],
        key=lambda row: -row["value"],
    )
    return {
        "dimension": dimension,
        "group_by": group_by,
        "account_name": account_name,
        "cash_policy": "excluded_all_dimensions",
        "denominator_description": "Open non-cash holdings with positive GBP snapshot value; "
        "account filter applies to every metric. Currency means source value currency, not FX exposure.",
        "totalValue": _round(total),
        "top1Pct": weights[0] if weights else 0,
        "top5Pct": _round(sum(weights[:5])),
        "hhi": _round(sum(weight ** 2 for weight in weights)),
        "categories": categories,
        "category_instruments": category_instruments,
        "holdings": grouped_holdings,
        "classification": {
            "holding_count": len(snapshots),
            "classified_count": classified_count,
            "classified_count_pct": _round(classified_count / len(snapshots) * 100)
            if snapshots
            else 0,
            "total_value_gbp": _round(total),
            "classified_value_gbp": _round(classified_value),
            "classified_value_pct": _round(classified_value / total * 100) if total else 0,
        },
    }
