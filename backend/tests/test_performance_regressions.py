import datetime as dt

import pytest

from app.services.performance_service import (
    build_flow_adjusted_curve,
    compute_flow_adjusted_metrics,
    compute_performance_metrics,
    max_flow_adjusted_drawdown,
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


@pytest.mark.parametrize("values,flows,expected", [
    ([100, 200], [(10, 100)], 0),
    ([100, 50], [(10, -50)], 0),
    ([100, 0], [], -100),
    ([100, 50], [(5, -200)], None),
    ([100, 110], [(5, float("nan"))], None),
])
def test_contributions_withdrawals_loss_and_invalid_denominators(values, flows, expected):
    start = dt.date(2026, 1, 1)
    points = [(start, values[0]), (start + dt.timedelta(days=10), values[1])]
    signed = [(start + dt.timedelta(days=day), amount) for day, amount in flows]
    curve = build_flow_adjusted_curve(points, signed)
    metrics = compute_flow_adjusted_metrics(points, signed, contributions=0, withdrawals=0)
    if expected is None:
        assert not curve
        assert metrics["total_return_pct"] is None
        assert max_flow_adjusted_drawdown(curve) is None
    else:
        assert curve[-1]["index"] - 100 == pytest.approx(expected)
        assert metrics["total_return_pct"] == pytest.approx(expected)
        assert max_flow_adjusted_drawdown(curve) == pytest.approx(min(0, expected))
    assert metrics["annualised_volatility_pct"] is None  # one interval is not zero volatility


def test_curve_and_kpi_reconcile_before_display_rounding():
    start = dt.date(2025, 1, 1)
    points = [(start + dt.timedelta(days=i * 10), value)
              for i, value in enumerate([137.17, 145.386, 151.9283])]
    curve = build_flow_adjusted_curve(points, [])
    metrics = compute_flow_adjusted_metrics(points, [], contributions=0, withdrawals=0)
    assert metrics["total_return_pct"] == curve[-1]["index"] - 100


def test_finite_inputs_that_overflow_are_not_published_as_infinity():
    import json

    points = [(dt.date(2025, 1, 1), 1e-300), (dt.date(2025, 1, 2), 1e300)]
    raw = compute_performance_metrics(points)
    adjusted = compute_flow_adjusted_metrics(points, [], contributions=0, withdrawals=0)
    assert raw["total_return_pct"] is None
    assert adjusted["total_return_pct"] is None
    assert build_flow_adjusted_curve(points, []) == []
    json.dumps(raw, allow_nan=False, default=str)
    json.dumps(adjusted, allow_nan=False, default=str)

