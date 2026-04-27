from __future__ import annotations

import datetime as dt
import hashlib
import json


def _normalise_datetime(value: dt.datetime | str) -> str:
    if isinstance(value, str):
        parsed = dt.datetime.fromisoformat(value)
    else:
        parsed = value

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(dt.UTC).replace(tzinfo=None)

    return parsed.isoformat(sep=" ", timespec="microseconds")


def _normalise_float(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{float(value):.8f}"


def _normalise_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalised = value.strip().casefold()
    return normalised or None


def order_fingerprint(
    *,
    security_name: str,
    order_date: dt.datetime | str,
    order_status: str,
    account_name: str,
    side: str,
    quantity: float | None,
    cost_proceeds_gbp: float | None,
    country: str | None,
) -> str:
    payload = {
        "account_name": _normalise_text(account_name),
        "cost_proceeds_gbp": _normalise_float(cost_proceeds_gbp),
        "country": _normalise_text(country),
        "order_date": _normalise_datetime(order_date),
        "order_status": _normalise_text(order_status),
        "quantity": _normalise_float(quantity),
        "security_name": _normalise_text(security_name),
        "side": _normalise_text(side),
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
