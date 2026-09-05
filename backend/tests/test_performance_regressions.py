import datetime as dt

import pytest

from app.services.performance_service import (
    build_flow_adjusted_curve,
    compute_flow_adjusted_metrics,
)


def test_headline_return_matches_chain_linked_curve_with_middle_contribution():
    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i * 10) for i in range(3)]
    points = list(zip(dates, [100.0, 220.0, 242.0], strict=True))
    flows = [(dates[1], 100.0)]
    curve = build_flow_adjusted_curve(points, flows)
    metrics = compute_flow_adjusted_metrics(points, flows, contributions=100, withdrawals=0)
    assert curve[-1]['index'] == pytest.approx(132.0)
    assert metrics['total_return_pct'] == pytest.approx(curve[-1]['index'] - 100)


@pytest.mark.parametrize('values', [[0.0, 100.0, 110.0], [100.0, float('inf'), 120.0], [100.0, -20.0, 50.0]])
def test_invalid_interval_is_unavailable_not_flat_or_silently_skipped(values):
    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(3)]
    points = list(zip(dates, values, strict=True))
    assert build_flow_adjusted_curve(points, []) == []
    metrics = compute_flow_adjusted_metrics(points, [], contributions=0, withdrawals=0)
    assert metrics['total_return_pct'] is None
    assert any('unusable' in note for note in metrics['notes'])
