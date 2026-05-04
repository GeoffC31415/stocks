import datetime as dt
from pathlib import Path

from app.services.hl_parser import (
    HL_ACCOUNT_NAME,
    parse_hl_activity_csv_bytes,
    parse_hl_holdings_csv_bytes,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def test_parse_hl_holdings_csv_bytes() -> None:
    rows, as_of = parse_hl_holdings_csv_bytes((DATA_DIR / "HL-Summary.csv").read_bytes())

    assert as_of == dt.date(2026, 5, 4)
    assert len(rows) == 6

    first = rows[0]
    assert first.account_name == HL_ACCOUNT_NAME
    assert first.identifier == "BCHS"
    assert first.investment == "Invesco Markets II plc CoinShares Global Blockchain UCITS ETF *1"
    assert first.quantity == 38
    assert first.last_price_pence == 12662
    assert first.value_gbp == 4811.56
    assert first.book_cost_gbp == 4931.22
    assert first.pct_change == -2.43


def test_parse_hl_activity_csv_bytes_skips_cash_events() -> None:
    rows = parse_hl_activity_csv_bytes((DATA_DIR / "hl-portfolio-summary.csv").read_bytes())

    assert len(rows) == 7
    assert {row.account_name for row in rows} == {HL_ACCOUNT_NAME}
    assert {row.side for row in rows} == {"Buy"}

    first = rows[0]
    assert first.security_name == "Vanguard Funds Plc FTSE All-World UCITS ETF (USD) Distributing - GBP"
    assert first.order_date == dt.datetime(2026, 3, 25, tzinfo=dt.UTC)
    assert first.quantity == 164
    assert first.cost_proceeds_gbp == 19976.13
    assert first.country == "GB"
