"""Synthetic release contracts; no personal data or application lifespan."""
import datetime as dt

import pytest

from app.services.performance_service import (
    build_drawdown_curve,
    build_flow_adjusted_curve,
    compute_flow_adjusted_metrics,
)


def test_invalid_common_chain_cannot_publish_a_curve_or_drawdown():
    day = dt.date(2026, 1, 1)
    points = [(day, 100.0), (day, 150.0), (day + dt.timedelta(days=10), 165.0)]
    metrics = compute_flow_adjusted_metrics(points, [], contributions=0, withdrawals=0)
    assert metrics["total_return_pct"] is None
    curve = build_flow_adjusted_curve(points, [])
    assert curve == [], "An invalid full-window KPI must not publish a partial adjusted curve"
    assert build_drawdown_curve(curve) == []


@pytest.mark.parametrize("status,value,reasons", [
    ("available", None, []), ("available", float("inf"), []),
    ("unavailable", 0, [{"code": "missing", "message": "Missing"}]),
    ("unavailable", None, []),
])
def test_metric_state_enforces_finite_values_and_unavailable_reasons(status, value, reasons):
    from pydantic import ValidationError

    from app.schemas import MetricState

    with pytest.raises(ValidationError):
        MetricState(status=status, value=value, unit="percent", method="Dietz",
                    start_date=None, end_date=None, observations=0, reasons=reasons)
