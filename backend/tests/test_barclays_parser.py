import datetime as dt
from pathlib import Path

from app.services.barclays_order_parser import parse_barclays_order_xls_bytes
from app.services.barclays_parser import parse_barclays_xls_bytes

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def test_parse_barclays_xls_bytes() -> None:
    rows, as_of = parse_barclays_xls_bytes(
        (FIXTURE_DIR / "barclays-portfolio.xls").read_bytes(),
        default_as_of_date=dt.date(2026, 5, 4),
    )

    assert as_of == dt.date(2026, 5, 4)
    assert len(rows) == 3

    first = rows[0]
    assert first.account_name == "Barclays ISA"
    assert first.identifier == "VWRL"
    assert first.investment == "Vanguard FTSE All-World"
    assert first.quantity == 10
    assert first.value_gbp == 1040
    assert first.book_cost_gbp == 900


def test_parse_barclays_order_xls_bytes() -> None:
    rows = parse_barclays_order_xls_bytes((FIXTURE_DIR / "barclays-orders.xls").read_bytes())

    assert len(rows) == 2
    assert {row.side for row in rows} == {"Buy", "Sell"}

    first = rows[0]
    assert first.security_name == "Vanguard FTSE All-World"
    assert first.order_date == dt.datetime(2026, 3, 25, tzinfo=dt.UTC)
    assert first.account_name == "Barclays ISA"
    assert first.quantity == 10
    assert first.cost_proceeds_gbp == 1040
    assert first.country == "GB"
