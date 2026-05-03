from app.models import Instrument
from app.services.instrument_matcher import match_order_to_instrument


def _instrument(
    *,
    instrument_id: int,
    account_name: str,
    security_name: str,
    is_cash: bool = False,
) -> Instrument:
    return Instrument(
        id=instrument_id,
        account_name=account_name,
        identifier=f"ID{instrument_id}",
        security_name=security_name,
        is_cash=is_cash,
    )


def test_match_order_prefers_same_account_exact_name() -> None:
    same_account = _instrument(
        instrument_id=1,
        account_name="ISA",
        security_name="Vanguard FTSE Global All Cap",
    )
    other_account = _instrument(
        instrument_id=2,
        account_name="GIA",
        security_name="Vanguard FTSE Global All Cap",
    )

    match = match_order_to_instrument(
        "vanguard ftse global all cap",
        "ISA",
        [other_account, same_account],
    )

    assert match == same_account


def test_match_order_ignores_cash_and_weak_single_token_matches() -> None:
    cash = _instrument(
        instrument_id=1,
        account_name="ISA",
        security_name="Cash",
        is_cash=True,
    )
    weak_candidate = _instrument(
        instrument_id=2,
        account_name="ISA",
        security_name="Global Holdings PLC",
    )

    match = match_order_to_instrument("Global Income", "ISA", [cash, weak_candidate])

    assert match is None
