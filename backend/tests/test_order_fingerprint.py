import datetime as dt

from app.services.order_fingerprint import order_fingerprint


def test_order_fingerprint_normalises_text_and_timezone() -> None:
    fingerprint_a = order_fingerprint(
        security_name="  Vanguard FTSE Global All Cap  ",
        order_date=dt.datetime(2025, 1, 2, 12, 30, tzinfo=dt.UTC),
        order_status=" Completed ",
        account_name=" ISA ",
        side=" Buy ",
        quantity=10,
        cost_proceeds_gbp=123.4,
        country=" GB ",
    )
    fingerprint_b = order_fingerprint(
        security_name="vanguard ftse global all cap",
        order_date="2025-01-02T12:30:00+00:00",
        order_status="completed",
        account_name="isa",
        side="buy",
        quantity=10.0,
        cost_proceeds_gbp=123.4,
        country="gb",
    )

    assert fingerprint_a == fingerprint_b


def test_order_fingerprint_changes_when_economic_identity_changes() -> None:
    base = {
        "security_name": "Acme PLC",
        "order_date": dt.datetime(2025, 1, 2, tzinfo=dt.UTC),
        "order_status": "Completed",
        "account_name": "ISA",
        "side": "Buy",
        "quantity": 10.0,
        "cost_proceeds_gbp": 100.0,
        "country": "GB",
    }

    assert order_fingerprint(**base) != order_fingerprint(**{**base, "cost_proceeds_gbp": 101.0})


def test_order_fingerprint_distinguishes_provider_event_ids() -> None:
    base = {
        "security_name": "Acme PLC",
        "order_date": dt.datetime(2025, 1, 2, tzinfo=dt.UTC),
        "order_status": "Completed",
        "account_name": "Trading 212",
        "side": "Buy",
        "quantity": 10.0,
        "cost_proceeds_gbp": 100.0,
        "country": None,
    }

    assert order_fingerprint(**base, source_event_id="fill-1") != order_fingerprint(
        **base, source_event_id="fill-2"
    )


def test_order_fingerprint_legacy_value_is_unchanged_without_provider_id() -> None:
    base = {
        "security_name": "Acme PLC",
        "order_date": dt.datetime(2025, 1, 2, tzinfo=dt.UTC),
        "order_status": "Completed",
        "account_name": "ISA",
        "side": "Buy",
        "quantity": 10.0,
        "cost_proceeds_gbp": 100.0,
        "country": "GB",
    }

    assert order_fingerprint(**base) == "1d6a51caef7d11488e13770f708dd71d62660e95744a7c644f9224ac89f06032"
