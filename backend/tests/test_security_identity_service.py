"""Listing identity boundaries: never substitute economic exposure for identity."""

import pytest

from app.models import Instrument
from app.services.security_identity_service import security_identity


def instrument(id, ticker=None, identifier="broker-id", name="Same display name"):
    return Instrument(
        id=id,
        account_name=f"account-{id}",
        ticker=ticker,
        identifier=identifier,
        security_name=name,
    )


def test_documented_identifier_and_listing_preserve_original_identifiers():
    a = instrument(1, "EQQQ.L", "EQQQ", "Invesco")
    b = instrument(2, "EQQQ.L", "IE0032077012", "EQQQ")
    assert security_identity(a, "GBP") == security_identity(b, "GBP")
    assert a.identifier == "EQQQ"
    assert b.identifier == "IE0032077012"
    assert (
        security_identity(a, "GBP")["security_key"]
        == "listing:isin:IE0032077012:XLON:EQQQ:currency:GBP"
    )


@pytest.mark.parametrize(
    "ticker,currency",
    [
        ("EQQQ.DE", "GBP"),  # distinct listing
        ("EQAC.L", "GBP"),  # accumulating share class
        ("EQQQ.L", "USD"),  # distinct source currency
        (None, "GBP"),
        ("EQQQ", "GBP"),
        (" EQQQ.L", "GBP"),
        ("EQQQ.L", None),
        ("EQQQ.L", ""),
    ],
)
def test_distinct_or_unverified_identities_stay_separate(ticker, currency):
    a = security_identity(instrument(1, "EQQQ.L"), "GBP")
    b = security_identity(instrument(2, ticker), currency)
    assert a["security_key"] != b["security_key"]
    assert b["aggregation_reasons"]


def test_name_and_broker_identifier_collisions_are_not_identity():
    a = security_identity(instrument(1), "GBP")
    b = security_identity(instrument(2), "GBP")
    assert a["security_key"] == "position:1"
    assert b["security_key"] == "position:2"
    assert a["aggregation_confidence"] == b["aggregation_confidence"] == "unverified"


@pytest.mark.parametrize(
    "identifier,ticker",
    [("broker-id", "MADEUP.FAKE"), ("IE00B53SZB19", "EQQQ.L"), ("missing", "EQQQ.L")],
)
def test_arbitrary_or_conflicting_mapping_is_unverified(identifier, ticker):
    a = security_identity(instrument(1, ticker, identifier), "GBP")
    b = security_identity(instrument(2, ticker, identifier), "GBP")
    assert a["aggregation_confidence"] == "unverified"
    assert a["security_key"] != b["security_key"]
