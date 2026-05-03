import datetime as dt

from app.models import Order
from app.services.order_service import _modified_dietz_annualised


def _order(
    *,
    order_date: dt.datetime,
    side: str,
    cost_proceeds_gbp: float,
) -> Order:
    return Order(
        order_import_batch_id=1,
        security_name="Example",
        order_date=order_date,
        order_status="Completed",
        account_name="ISA",
        side=side,
        quantity=1,
        cost_proceeds_gbp=cost_proceeds_gbp,
        country="GB",
        is_drip=False,
        order_fingerprint="unused",
    )


def test_modified_dietz_annualised_handles_intermediate_cashflows() -> None:
    result = _modified_dietz_annualised(
        [
            _order(
                order_date=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                side="Buy",
                cost_proceeds_gbp=1000,
            ),
            _order(
                order_date=dt.datetime(2024, 7, 1, tzinfo=dt.UTC),
                side="Buy",
                cost_proceeds_gbp=500,
            ),
        ],
        end_value=1700,
        end_date=dt.date(2025, 1, 1),
        drip_threshold_gbp=100,
    )

    assert result is not None
    assert round(result, 1) == 15.9


def test_modified_dietz_annualised_ignores_drip_cashflows() -> None:
    result = _modified_dietz_annualised(
        [
            _order(
                order_date=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                side="Buy",
                cost_proceeds_gbp=1000,
            ),
            _order(
                order_date=dt.datetime(2024, 7, 1, tzinfo=dt.UTC),
                side="Buy",
                cost_proceeds_gbp=50,
            ),
        ],
        end_value=1100,
        end_date=dt.date(2025, 1, 1),
        drip_threshold_gbp=100,
    )

    assert result is not None
    assert round(result, 1) == 10.0
