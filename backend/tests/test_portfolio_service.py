from app.models import HoldingSnapshot
from app.services.portfolio_service import snapshot_metrics


def _snapshot(
    *,
    instrument_id: int,
    quantity: float,
    last_price: float | None,
    value_gbp: float,
) -> HoldingSnapshot:
    return HoldingSnapshot(
        import_batch_id=1,
        instrument_id=instrument_id,
        investment_label="Example",
        quantity=quantity,
        last_price=last_price,
        value_gbp=value_gbp,
    )


def test_snapshot_metrics_uses_price_drawdown_before_value_drawdown() -> None:
    metrics = snapshot_metrics(
        {
            1: [
                _snapshot(instrument_id=1, quantity=10, last_price=100, value_gbp=1000),
                _snapshot(instrument_id=1, quantity=12, last_price=80, value_gbp=960),
            ]
        }
    )

    assert metrics[1]["peak_value_gbp"] == 1000
    assert metrics[1]["peak_last_price"] == 100
    assert metrics[1]["drawdown_from_peak_pct"] == -20
    assert metrics[1]["quantity_unchanged_snapshot_count"] == 1


def test_snapshot_metrics_counts_consecutive_unchanged_latest_quantity() -> None:
    metrics = snapshot_metrics(
        {
            1: [
                _snapshot(instrument_id=1, quantity=8, last_price=None, value_gbp=800),
                _snapshot(instrument_id=1, quantity=10, last_price=None, value_gbp=900),
                _snapshot(instrument_id=1, quantity=10, last_price=None, value_gbp=850),
                _snapshot(instrument_id=1, quantity=10, last_price=None, value_gbp=800),
            ]
        }
    )

    assert metrics[1]["drawdown_from_peak_pct"] == -100 / 900 * 100
    assert metrics[1]["quantity_unchanged_snapshot_count"] == 3
