"""Offset pagination; totals always describe the complete filtered result."""

from typing import Literal

from pydantic import BaseModel

from app.schemas import OrderOut


class OrderPageTotals(BaseModel):
    buy_gbp: float | None
    sell_gbp: float | None
    drip_gbp: float | None


AmountReason = Literal["missing_amounts", "non_finite_amounts", "non_finite_total"]


class OrderPageTotalReasons(BaseModel):
    buy_gbp: AmountReason | None
    sell_gbp: AmountReason | None
    drip_gbp: AmountReason | None


class OrderPageItem(OrderOut):
    cost_proceeds_gbp_reason: AmountReason | None = None


class OrderPage(BaseModel):
    items: list[OrderPageItem]
    total_count: int
    offset: int
    limit: int
    has_more: bool
    totals: OrderPageTotals
    totals_reasons: OrderPageTotalReasons
    classification_basis: str = (
        "Stored import-time reinvestment proxy; Reinvestment proxy, not dividend ledger. "
        "Threshold changes do not retrospectively reclassify orders."
    )
