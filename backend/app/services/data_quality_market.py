"""Cached prerequisites only: this does not approve D01 provider/identity readiness."""
import datetime as dt
import math
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HoldingSnapshot
from app.services.market_data_service import SOURCE, load_points
from app.services.portfolio_risk_service import _load_gbp_series


async def cached_prerequisites(session: AsyncSession, snapshots: Sequence[HoldingSnapshot], as_of: dt.date | None) -> dict:
    holdings = [s for s in snapshots if not s.instrument.is_cash]
    valid_values = all(s.value_gbp is not None and math.isfinite(s.value_gbp) and s.value_gbp >= 0 for s in holdings)
    total = sum(s.value_gbp for s in holdings if s.value_gbp is not None and math.isfinite(s.value_gbp) and s.value_gbp > 0)
    by_ticker: dict[str, float] = {}
    for snapshot in holdings:
        if snapshot.instrument.ticker and snapshot.value_gbp is not None and snapshot.value_gbp > 0:
            by_ticker[snapshot.instrument.ticker] = by_ticker.get(snapshot.instrument.ticker, 0) + snapshot.value_gbp
    covered = 0.0
    date_sets = []
    for ticker, value in by_ticker.items():
        points = await load_points(session, ticker, source=SOURCE)
        if not points or as_of is None:
            continue
        # Reuse the tested dated-FX/price-basis conversion, never provider fetch.
        series = await _load_gbp_series(session, ticker, points[0].currency, as_of=as_of)
        if not series or any(not math.isfinite(price) or price <= 0 for _, price in series):
            continue
        if (as_of - series[-1][0]).days > 14:
            continue
        date_sets.append({date for date, _ in series})
        covered += value
    aligned = len(set.intersection(*date_sets)) if date_sets else 0
    pct = covered / total * 100 if total > 0 and valid_values else None
    gate_met = pct is not None and pct >= 80 and aligned >= 126
    reasons = ["Cached prerequisites only; full provider, identity and benchmark validation remains pending (D01)."]
    if not valid_values:
        reasons.append("Missing, negative or non-finite holding values prevent a reliable coverage denominator.")
    if pct is None:
        reasons.append("No valid non-cash denominator is available.")
    elif pct < 80:
        reasons.append(f"Usable cached history covers {pct:.1f}% of non-cash value; at least 80% is required.")
    if aligned < 126:
        reasons.append(f"{aligned} aligned daily price observations; at least 126 are required.")
    return {"covered_value_gbp": covered, "non_cash_value_gbp": total, "covered_pct": pct,
            "aligned_observations": aligned, "cache_gate_met": gate_met, "validation_pending": True, "reasons": reasons}
