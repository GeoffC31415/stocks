import datetime as dt
from types import SimpleNamespace

from app.services.valuation_service import scope_baseline_flows


def test_scope_baseline_flows_adds_new_account_value_once():
    first = SimpleNamespace(
        date=dt.date(2025, 1, 1),
        account_dates={"HL": dt.date(2025, 1, 1)},
        snapshots=[SimpleNamespace(instrument=SimpleNamespace(account_name="HL"), value_gbp=100)],
    )
    second = SimpleNamespace(
        date=dt.date(2025, 2, 1),
        account_dates={"HL": dt.date(2025, 2, 1), "Trading 212": dt.date(2025, 2, 1)},
        snapshots=[
            SimpleNamespace(instrument=SimpleNamespace(account_name="HL"), value_gbp=120),
            SimpleNamespace(instrument=SimpleNamespace(account_name="Trading 212"), value_gbp=80),
        ],
    )
    third = SimpleNamespace(
        date=dt.date(2025, 3, 1),
        account_dates={"HL": dt.date(2025, 3, 1), "Trading 212": dt.date(2025, 3, 1)},
        snapshots=second.snapshots,
    )
    assert scope_baseline_flows([first, second, third]) == [(dt.date(2025, 1, 1), 100), (dt.date(2025, 2, 1), 80)]
