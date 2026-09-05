"""Regression tests for dated, weighted benchmark comparisons."""
import datetime as dt

import numpy as np
import pytest

from app.services.risk_service import RiskAnalysisInput, RiskFactorSeries, compute_risk_analysis


def prices(returns):
    values = 100 * np.cumprod(np.r_[1.0, 1 + np.asarray(returns)])
    return [(dt.date(2025, 1, 1) + dt.timedelta(days=i), float(v)) for i, v in enumerate(values)]


def test_benchmark_uses_weighted_portfolio_and_cash():
    series = prices([0.01, -0.02, 0.03, -0.01] * 40)
    result = compute_risk_analysis(RiskAnalysisInput(
        factors=(RiskFactorSeries('A', series),), cash_weight=0.2,
        sleeve_weights={'A': 0.8}, full_book_weights={'A': 0.8, 'cash': 0.2},
        benchmark_prices=series,
    ))
    assert result['benchmark']['available']
    assert result['benchmark']['observations'] == 160
    assert result['benchmark']['beta'] == pytest.approx(0.8)


def test_benchmark_missing_date_never_pairs_different_intervals():
    series = prices([0.01, -0.02, 0.03, -0.01] * 40)
    benchmark = [row for i, row in enumerate(series) if i != 50]
    result = compute_risk_analysis(RiskAnalysisInput(
        factors=(RiskFactorSeries('A', series),), cash_weight=0.0,
        sleeve_weights={'A': 1.0}, full_book_weights={'A': 1.0},
        benchmark_prices=benchmark,
    ))
    assert result['benchmark']['observations'] == 158
    assert result['benchmark']['beta'] == pytest.approx(1.0)


def test_relative_risk_requires_126_paired_observations():
    series = prices([0.01, -0.02, 0.03, -0.01] * 40)
    result = compute_risk_analysis(RiskAnalysisInput(
        factors=(RiskFactorSeries('A', series),), cash_weight=0.0,
        sleeve_weights={'A': 1.0}, full_book_weights={'A': 1.0},
        benchmark_prices=series[-40:],
    ))
    assert result['benchmark']['available'] is False
    assert result['benchmark']['observations'] == 39
