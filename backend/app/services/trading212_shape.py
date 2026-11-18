"""Known JSON object shapes for the four Trading 212 reads (public OpenAPI v0).

This is not an input validator. Financial mapping sees the original values. Only
keys outside the documented objects are irrelevant to the v1 comparison, and
only source-owned schema labels (never unknown keys or values) enter the journal.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

logger = logging.getLogger(__name__)


def _fields(**groups: str) -> dict[str, str]:
    return {field: kind for kind, fields in groups.items() for field in fields.split()}


# A child kind denotes an object; a 'many_' prefix denotes a list of such objects.
_SCHEMA = {
    "position": _fields(
        number="averagePricePaid currentPrice quantity quantityAvailableForTrading quantityInPies",
        string="createdAt",
        instrument="instrument",
        position_wallet="walletImpact",
    ),
    "instrument": _fields(string="currency isin name ticker"),
    "position_wallet": _fields(
        string="currency", number="currentValue fxImpact totalCost unrealizedProfitLoss"
    ),
    "account": _fields(
        cash="cash", string="currency", integer="id", investments="investments", number="totalValue"
    ),
    "cash": _fields(number="availableToTrade inPies reservedForOrders"),
    "investments": _fields(number="currentValue realizedProfitLoss totalCost unrealizedProfitLoss"),
    "orders_page": _fields(many_historical_order="items", string="nextPagePath"),
    "transactions_page": _fields(many_transaction="items", string="nextPagePath"),
    "historical_order": _fields(fill="fill", order="order"),
    "fill": _fields(
        string="filledAt tradingMethod type",
        integer="id",
        number="price quantity",
        fill_wallet="walletImpact",
    ),
    "order": _fields(
        string="createdAt currency initiatedFrom side status strategy ticker timeInForce type",
        boolean="extendedHours",
        number="filledQuantity filledValue limitPrice quantity stopPrice value",
        integer="id",
        instrument="instrument",
    ),
    "fill_wallet": _fields(
        string="currency", number="fxRate netValue realisedProfitLoss", many_tax="taxes"
    ),
    "tax": _fields(string="chargedAt currency name", number="quantity"),
    "transaction": _fields(number="amount", string="currency dateTime reference type"),
}
_ENDPOINTS = {
    "position": "positions",
    "account": "account_summary",
    "orders_page": "orders",
    "transactions_page": "transactions",
}
_SCALARS = {"number": (float, int), "integer": (int,), "string": (str,), "boolean": (bool,)}


def _project_child(kind: str, value: Any) -> Any:
    if kind in _SCHEMA and isinstance(value, Mapping):
        return project_record(kind, value)
    if kind.startswith("many_") and isinstance(value, list):
        return [_project_child(kind[5:], item) for item in value]
    # Preserve nulls and malformed *known* fields, rather than treating them as absent.
    return value


def project_record(kind: str, record: Mapping[str, Any]) -> dict[str, Any]:
    """Projection for duplicate comparison only. No coercion, defaults or mutation."""
    return {
        key: _project_child(child, record[key])
        for key, child in _SCHEMA[kind].items()
        if key in record
    }


class ShapeJournal:
    """One warning per reviewed location/field/reason per client, even across pages."""

    def __init__(self) -> None:
        self._reported: set[tuple[str, str, str, str]] = set()

    def observe(self, root: str, data: Any) -> None:
        # An observer or log handler failure must not reject otherwise usable data.
        with suppress(Exception):
            endpoint = _ENDPOINTS[root]
            if root == "position":
                for item in data:
                    self._inspect(endpoint, root, item)
            else:
                self._inspect(endpoint, root, data)

    def _inspect(self, endpoint: str, kind: str, obj: Any) -> None:
        if not isinstance(obj, Mapping):
            return
        fields = _SCHEMA[kind]
        if any(key not in fields for key in obj):
            self._warn(endpoint, kind, "extra", "additional_field")
        for key, child in fields.items():
            value = obj.get(key)
            if value is None:
                continue  # Many fields are optional; financial validators enforce required ones.
            if child in _SCALARS:
                if type(value) not in _SCALARS[child]:
                    self._warn(endpoint, kind, key, "unexpected_type")
            elif child.startswith("many_") and isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping):
                        self._inspect(endpoint, child[5:], item)
                    else:
                        self._warn(endpoint, kind, key, "unexpected_type")
            elif child in _SCHEMA and isinstance(value, Mapping):
                self._inspect(endpoint, child, value)
            else:
                self._warn(endpoint, kind, key, "unexpected_type")

    def _warn(self, endpoint: str, kind: str, field: str, code: str) -> None:
        # Only the fixed root/field registry above supplies these arguments.
        tag = (endpoint, kind, field, code)
        if tag not in self._reported:
            self._reported.add(tag)
            logger.disabled = (
                False  # Alembic can disable pre-existing loggers in the general worker.
            )
            logger.warning(
                "Trading 212 response drift endpoint=%s location=%s field=%s code=%s", *tag
            )
