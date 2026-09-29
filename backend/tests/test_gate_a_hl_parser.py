import pytest

from app.services.hl_parser import parse_hl_activity_csv_bytes, parse_hl_holdings_csv_bytes

HOLDINGS_HEADER = "Code,Stock,Units held,Price (pence),Value (£),Cost (£),Gain/loss (%)\n"
HOLDINGS = (
    "Spreadsheet created at,29-09-2026 10:00\nStock value:,30\nNumber of holdings:,2\n"
    + HOLDINGS_HEADER
    + "ONE,One,1,1000,10,9,11.11\nTWO,Two,2,1000,20,18,11.11\n"
    + ",Totals,,,30,27,\n"
)
ACTIVITY_HEADER = "Trade date,Reference,Description,Unit cost (p),Quantity,Value (£)\n"
ACTIVITY = ACTIVITY_HEADER + "01/09/2026,B1,One 1 @ 1000,1000,1,-10\n"


@pytest.mark.parametrize(
    "data",
    [
        HOLDINGS.replace("TWO,Two", ",Two"),
        HOLDINGS.replace("TWO,Two,2,1000,20,18,11.11", "TWO,Two"),
        HOLDINGS.replace("20,18,11.11", "NaN,18,11.11"),
        HOLDINGS.replace("20,18,11.11", "20,inf,11.11"),
        HOLDINGS.replace(HOLDINGS_HEADER, "Code,Stock\n"),
        "not a holdings export",
        HOLDINGS.replace("TWO,Two,2,1000,20,18,11.11\n", ""),
        HOLDINGS.replace(",Totals,,,30,27,", ",Totals,,,31,27,"),
        HOLDINGS.replace("Number of holdings:,2", "Number of holdings:,3"),
        HOLDINGS + "THREE,Three,1,1000,10,9,11\n",
        HOLDINGS.replace(",Totals,,,30,27,\n", ""),
        HOLDINGS.replace(",Totals,,,30,27,", ",Totals,,,30,27,NaN"),
        HOLDINGS.replace("TWO,Two", "ONE,Two"),
    ],
)
def test_holdings_rejects_any_corrupt_or_incomplete_row(data):
    with pytest.raises(ValueError, match="HL"):
        parse_hl_holdings_csv_bytes(data.encode())


@pytest.mark.parametrize(
    "data",
    [
        ACTIVITY.replace("B1", "UNKNOWN"),
        ACTIVITY.replace("1000,1,-10", "1000,1"),
        ACTIVITY.replace("1000,1,-10", "NaN,1,-10"),
        ACTIVITY.replace("1000,1,-10", "1000,inf,-10"),
        ACTIVITY.replace("01/09/2026", "bad date"),
        ACTIVITY.replace("One 1 @ 1000", ""),
        ACTIVITY.replace("1000,1,-10", "1000,-1,-10"),
        ACTIVITY.replace("Reference", "Unknown header"),
        "not an activity export",
    ],
)
def test_activity_rejects_unrepresented_nonempty_rows(data):
    with pytest.raises(ValueError, match="HL"):
        parse_hl_activity_csv_bytes(data.encode())


@pytest.mark.parametrize(
    "data",
    [
        HOLDINGS_HEADER.replace("Cost (£)", "Value (£)") + "ONE,One,1,1000,10,9,0\n",
        HOLDINGS.replace("29-09-2026 10:00", "bad date"),
        HOLDINGS.replace("Stock value:,30", "Stock value:,31"),
        HOLDINGS.replace("Gain/loss (%)", "Gain/loss (£),Gain/loss (%)")
        .replace("9,11.11", "9,NaN,11.11")
        .replace("18,11.11", "18,2,11.11")
        .replace("30,27,", "30,27,,"),
    ],
)
def test_holdings_rejects_corrupt_optional_columns_and_metadata(data):
    with pytest.raises(ValueError, match="HL"):
        parse_hl_holdings_csv_bytes(data.encode())


def test_colon_client_metadata_preserves_legacy_account_and_order_identity():
    holdings, _ = parse_hl_holdings_csv_bytes(
        ("Client Name:,Synthetic Person\n" + HOLDINGS).encode()
    )
    orders = parse_hl_activity_csv_bytes(("Client Name:,Synthetic Person\n" + ACTIVITY).encode())
    assert holdings[0].account_name == "HL Fund & Share Account"
    assert orders[0].account_name == "HL Fund & Share Account"


def test_valid_exports_reconcile_and_known_cash_events_are_explicitly_excluded():
    holdings, _ = parse_hl_holdings_csv_bytes(HOLDINGS.encode())
    orders = parse_hl_activity_csv_bytes((ACTIVITY + "02/09/2026,C1,Cash deposit,,,50\n").encode())
    assert len(holdings) == 2
    assert len(orders) == 1
    assert orders[0].security_name == "One"
