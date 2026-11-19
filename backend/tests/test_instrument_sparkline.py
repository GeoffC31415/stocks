from types import SimpleNamespace

from app.services.portfolio_service import _sparkline_series, build_instrument_out, snapshot_metrics


def test_sparkline_prefers_last_price_and_caps_at_24_points():
    snaps = [
        SimpleNamespace(
            value_gbp=100.0 * (i + 1),
            last_price=10.0 + i,
            quantity=10.0,
            book_cost_gbp=90.0,
            pct_change=1.0,
        )
        for i in range(30)
    ]
    series = _sparkline_series(snaps)
    assert len(series) == 24
    assert series[0] == 16.0
    assert series[-1] == 39.0


def test_sparkline_falls_back_to_value_gbp_when_prices_missing():
    snaps = [
        SimpleNamespace(value_gbp=100.0, last_price=None, quantity=1.0, book_cost_gbp=100.0, pct_change=0.0),
        SimpleNamespace(value_gbp=112.5, last_price=None, quantity=1.0, book_cost_gbp=100.0, pct_change=12.5),
    ]
    assert _sparkline_series(snaps) == [100.0, 112.5]


def test_build_instrument_out_omits_sparkline_for_cash():
    snaps = [
        SimpleNamespace(value_gbp=100.0, last_price=10.0, quantity=10.0, book_cost_gbp=90.0, pct_change=1.0),
        SimpleNamespace(value_gbp=110.0, last_price=11.0, quantity=10.0, book_cost_gbp=90.0, pct_change=2.0),
    ]
    m = snapshot_metrics({1: snaps})
    equity = SimpleNamespace(
        id=1, account_name="ISA", identifier="VWRL", security_name="Vanguard",
        is_cash=False, ticker="VWRL.L", sector="Equity", region="Global", asset_class="ETF", closed_at=None,
    )
    cash = SimpleNamespace(
        id=2, account_name="ISA", identifier="CASH", security_name="Cash",
        is_cash=True, ticker=None, sector=None, region=None, asset_class=None, closed_at=None,
    )
    assert build_instrument_out(equity, snaps[-1], metrics=m[1]).sparkline_values == [10.0, 11.0]
    assert build_instrument_out(cash, snaps[-1], metrics=m[1]).sparkline_values == []
