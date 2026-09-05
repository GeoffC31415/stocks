"""Conservative, evidence-backed listing identity; never a risk-factor key.

The small reviewed registry is documented in docs/security-identity.md. Unknown
mappings stay separate, even when an editable ticker happens to match.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Instrument

# Exact source identifiers and stored listing; never normalise broker tokens.
_VERIFIED_LISTINGS = {
    "EQQQ.L": ({"EQQQ", "IE0032077012", "B0GL4T3"}, "IE0032077012", "XLON", "EQQQ"),
}


def security_identity(instrument: Instrument, currency: str | None) -> dict:
    listing = _VERIFIED_LISTINGS.get(instrument.ticker or "")
    if listing and instrument.identifier in listing[0] and currency in {"GBP", "GBX", "GBp"}:
        _, isin, mic, symbol = listing
        return {
            "security_key": f"listing:isin:{isin}:{mic}:{symbol}:currency:{currency}",
            "aggregation_confidence": "verified_listing",
            "aggregation_reasons": [
                "Exact identifier and listing match the reviewed LSE registry (2026-09-05); "
                "source currencies remain separate. Not fund look-through."
            ],
        }
    return {
        "security_key": f"position:{instrument.id}",
        "aggregation_confidence": "unverified",
        "aggregation_reasons": [
            "No reviewed identifier/listing/currency match, or conflicting source identifier; "
            "kept separate without guessing from names or editable tickers."
        ],
    }
