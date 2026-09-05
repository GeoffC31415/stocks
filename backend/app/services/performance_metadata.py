"""Additive availability contract for snapshot performance (not proxy risk)."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.services.drawdown_service import build_drawdown_episodes

if TYPE_CHECKING:
    import datetime as dt

METRIC_UNITS = {
    "total_return_pct": "percent",
    "annualised_return_pct": "percent",
    "annualised_volatility_pct": "percent",
    "sharpe_ratio": "ratio",
    "sortino_ratio": "ratio",
    "max_drawdown_pct": "percent",
}


def with_performance_metadata(
    payload: dict, *, account_name: str | None,
    requested_start: dt.date | None = None,
    valuation_dates: list[dict] | None = None,
) -> dict:
    flow = payload.get("flow_adjusted") or {}
    start, end = payload["period_start"], payload["period_end"]
    observations = len(payload["growth_curve"])
    chain_valid = flow.get("total_return_pct") is not None and bool(payload["flow_adjusted_curve"])
    states = {}
    for key, unit in METRIC_UNITS.items():
        value = flow.get(key) if chain_valid else None
        if value is not None and not math.isfinite(value):
            value = None
        reasons = []
        if value is None:
            if observations < 2:
                code, message = "insufficient_snapshots", "At least two distinct snapshot dates are required."
            elif not chain_valid:
                code = "invalid_return_chain"
                message = "An unusable snapshot interval prevents a complete flow-adjusted return."
                if flow.get("contributions_gbp") is None:
                    code, message = "flows_unavailable", "Transaction flows could not be read for this window."
            elif key == "annualised_return_pct":
                code = "short_annualisation_window" if (end - start).days < 365 else "total_loss"
                message = ("Annualisation requires at least 365 days. Cumulative return remains available."
                           if code == "short_annualisation_window" else
                           "Annualised return is not reported after a total loss.")
            elif flow.get("num_periods", 0) < 2:
                code, message = "insufficient_intervals", "At least two interval returns are required for risk statistics."
            elif key == "sortino_ratio":
                code, message = "no_downside", "No downside deviation in the observed window; Sortino is undefined."
            else:
                code, message = "zero_variance", "Zero interval-return variance; this risk ratio is undefined."
            reasons = [{"code": code, "message": message, "action_href": None}]
        states[key] = {
            "status": "available" if value is not None else "unavailable", "value": value,
            "unit": unit, "method": flow.get("method", "Chain-linked interval Modified Dietz"),
            "start_date": start, "end_date": end, "observations": observations, "reasons": reasons,
        }
    warnings = []
    dates = valuation_dates or []
    if len({item["date"] for item in dates}) > 1:
        warnings.append("Account valuation dates differ; older account snapshots are carried forward.")
    if payload.get("coverage_start") is not None:
        warnings.append("Combined performance begins only once every selected account has snapshot coverage.")
    payload["drawdown_episodes"] = build_drawdown_episodes(payload["flow_adjusted_curve"]) if chain_valid else []
    payload["metrics"] = states
    payload["scope"] = {
        "account_name": account_name, "requested_start": requested_start,
        "requested_end": None, "effective_start": start, "effective_end": end,
        "valuation_dates": dates, "warnings": warnings,
    }
    return payload
