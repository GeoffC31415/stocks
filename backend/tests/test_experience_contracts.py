"""Synthetic release contracts; no personal data or application lifespan."""
import datetime as dt

import pytest

from app.services.performance_service import (
    build_drawdown_curve,
    build_flow_adjusted_curve,
    compute_flow_adjusted_metrics,
)


@pytest.mark.xfail(strict=True, reason="T01: duplicate dates invalidate KPI but publish curve")
def test_invalid_common_chain_cannot_publish_a_curve_or_drawdown():
    day = dt.date(2026, 1, 1)
    points = [(day, 100.0), (day, 150.0), (day + dt.timedelta(days=10), 165.0)]
    metrics = compute_flow_adjusted_metrics(points, [], contributions=0, withdrawals=0)
    assert metrics["total_return_pct"] is None
    curve = build_flow_adjusted_curve(points, [])
    assert curve == [], "An invalid full-window KPI must not publish a partial adjusted curve"
    assert build_drawdown_curve(curve) == []
