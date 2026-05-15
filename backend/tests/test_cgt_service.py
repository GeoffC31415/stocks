"""Tests for the UK CGT matching engine."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Instrument, Order
from app.services.cgt_service import (
    Pool,
    SaleDetail,
    SaleMatch,
    calculate_cgt_for_instrument,
    get_cgt_summary,
    get_instrument_cgt,
    _group_by_tax_year,
    _tax_year_end,
)


def _order(
    *,
    id: int = 1,
    order_date: dt.datetime | None = None,
    side: str = "Buy",
    quantity: float = 100.0,
    cost_proceeds_gbp: float = 1000.0,
    instrument_id: int | None = None,
    security_name: str = "TestStock",
    account_name: str = "TestAccount",
) -> Order:
    return Order(
        id=id,
        security_name=security_name,
        order_date=order_date or dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        order_status="Dealing",
        account_name=account_name,
        side=side,
        quantity=quantity,
        cost_proceeds_gbp=cost_proceeds_gbp,
        instrument_id=instrument_id,
    )


class TestTaxYearEnd:
    """Test UK tax year boundary detection (6 Apr - 5 Apr)."""

    def test_mar_falls_in_previous_year(self) -> None:
        """31 Mar falls in tax year ending next year."""
        d = dt.datetime(2024, 3, 31, tzinfo=dt.UTC)
        assert _tax_year_end(d) == 2024  # tax year 2023-24

    def test_april_5th_end_of_year(self) -> None:
        """5 Apr is the last day of the tax year."""
        d = dt.datetime(2024, 4, 5, tzinfo=dt.UTC)
        assert _tax_year_end(d) == 2024  # tax year 2023-24

    def test_april_6th_new_year(self) -> None:
        """6 Apr starts the new tax year."""
        d = dt.datetime(2024, 4, 6, tzinfo=dt.UTC)
        assert _tax_year_end(d) == 2025  # tax year 2024-25

    def test_january_current_year(self) -> None:
        """Jan falls in the current tax year."""
        d = dt.datetime(2024, 1, 15, tzinfo=dt.UTC)
        assert _tax_year_end(d) == 2024


class TestSameDayRule:
    """Test the same-day matching rule."""

    def test_basic_same_day(self) -> None:
        """Buy and sell on the same day should match via same-day rule."""
        orders = [
            _order(id=1, order_date=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), side="Buy", quantity=100, cost_proceeds_gbp=1000),
            _order(id=2, order_date=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), side="Sell", quantity=50, cost_proceeds_gbp=600),
        ]
        sales = calculate_cgt_for_instrument(orders)

        assert len(sales) == 1
        sale = sales[0]
        assert len(sale.matches) == 1
        assert sale.matches[0].source == "same_day"
        assert sale.matches[0].quantity == 50.0
        assert sale.realised_gain == 100.0  # 600 - (1000/100)*50

    def test_same_day_partial(self) -> None:
        """Sell larger than same-day buy only matches up to buy qty."""
        orders = [
            _order(id=1, order_date=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), side="Buy", quantity=50, cost_proceeds_gbp=500),
            _order(id=2, order_date=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), side="Sell", quantity=100, cost_proceeds_gbp=1000),
        ]
        sales = calculate_cgt_for_instrument(orders)

        assert len(sales) == 1
        sd_match = [m for m in sales[0].matches if m.source == "same_day"]
        assert len(sd_match) == 1
        assert sd_match[0].quantity == 50.0


class TestBedAndBreakfastRule:
    """Test the 30-day bed & breakfasting rule."""

    def test_bf_within_30_days(self) -> None:
        """Buy within 30 days after a sell should match that sell."""
        orders = [
            _order(id=1, order_date=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), side="Sell", quantity=50, cost_proceeds_gbp=600),
            _order(id=2, order_date=dt.datetime(2024, 3, 15, tzinfo=dt.UTC), side="Buy", quantity=50, cost_proceeds_gbp=500),
        ]
        sales = calculate_cgt_for_instrument(orders)

        assert len(sales) == 1
        bf_match = [m for m in sales[0].matches if m.source == "b&f"]
        assert len(bf_match) == 1
        assert bf_match[0].quantity == 50.0
        assert sales[0].realised_gain == 100.0  # 600 - 500

    def test_bf_outside_30_days(self) -> None:
        """Buy after 30 days does not trigger B&F."""
        orders = [
            _order(id=1, order_date=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), side="Sell", quantity=50, cost_proceeds_gbp=600),
            _order(id=2, order_date=dt.datetime(2024, 4, 1, tzinfo=dt.UTC), side="Buy", quantity=50, cost_proceeds_gbp=500),
        ]
        sales = calculate_cgt_for_instrument(orders)

        # The buy on Apr 1 is 31 days after the sell on Mar 1, so no B&F match
        bf_match = [m for m in sales[0].matches if m.source == "b&f"]
        assert len(bf_match) == 0


class TestSection104Pool:
    """Test the Section 104 pool matching."""

    def test_pool_sale(self) -> None:
        """Sale from pool uses average cost."""
        orders = [
            _order(id=1, order_date=dt.datetime(2024, 1, 1, tzinfo=dt.UTC), side="Buy", quantity=100, cost_proceeds_gbp=1000),
            _order(id=2, order_date=dt.datetime(2024, 6, 1, tzinfo=dt.UTC), side="Buy", quantity=100, cost_proceeds_gbp=1200),
            _order(id=3, order_date=dt.datetime(2024, 9, 1, tzinfo=dt.UTC), side="Sell", quantity=100, cost_proceeds_gbp=1500),
        ]
        sales = calculate_cgt_for_instrument(orders)

        assert len(sales) == 1
        sale = sales[0]
        pool_match = [m for m in sale.matches if m.source == "pool"]
        assert len(pool_match) == 1
        assert pool_match[0].quantity == 100.0
        assert pool_match[0].cost == 1100.0  # avg cost (1000+1200)/200 * 100
        assert sale.realised_gain == 400.0  # 1500 - 1100

    def test_pool_consumes_remaining_after_same_day_bf(self) -> None:
        """Pool only covers quantity not matched by same-day or b&f."""
        orders = [
            _order(id=1, order_date=dt.datetime(2024, 1, 1, tzinfo=dt.UTC), side="Buy", quantity=100, cost_proceeds_gbp=1000),
            _order(id=2, order_date=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), side="Sell", quantity=150, cost_proceeds_gbp=1800),
            _order(id=3, order_date=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), side="Buy", quantity=100, cost_proceeds_gbp=1200),
            _order(id=4, order_date=dt.datetime(2024, 3, 20, tzinfo=dt.UTC), side="Buy", quantity=100, cost_proceeds_gbp=1200),
        ]
        sales = calculate_cgt_for_instrument(orders)

        assert len(sales) == 1
        sale = sales[0]
        # 150 sold: 100 same-day + 50 b&f (first 50 of 100)
        sd_match = [m for m in sale.matches if m.source == "same_day"]
        bf_match = [m for m in sale.matches if m.source == "b&f"]
        pool_match = [m for m in sale.matches if m.source == "pool"]

        assert len(sd_match) == 1
        assert sd_match[0].quantity == 100.0
        assert len(bf_match) == 1
        assert bf_match[0].quantity == 50.0
        assert len(pool_match) == 0  # all matched by same-day + b&f


class TestTaxYearGrouping:
    """Test tax year aggregation."""

    def test_single_year(self) -> None:
        """Sales in one tax year group correctly."""
        sale = SaleDetail(
            order_id=1,
            order_date=dt.datetime(2024, 3, 15, tzinfo=dt.UTC).isoformat(),
            security_name="Test",
            instrument_id=1,
            quantity=50,
            proceeds_gbp=600,
            total_proceeds=600,
            total_cost=500,
            realised_gain=100,
        )
        tax_years = _group_by_tax_year([sale])

        assert len(tax_years) == 1
        assert tax_years[0].tax_year == "2023-24"
        assert tax_years[0].total_gain == 100

    def test_cross_year(self) -> None:
        """Sales spanning two tax years split correctly."""
        sale1 = SaleDetail(
            order_id=1,
            order_date=dt.datetime(2024, 3, 31, tzinfo=dt.UTC).isoformat(),
            security_name="Test",
            instrument_id=1,
            quantity=50,
            proceeds_gbp=600,
            total_proceeds=600,
            total_cost=500,
            realised_gain=100,
        )

        sale2 = SaleDetail(
            order_id=2,
            order_date=dt.datetime(2024, 5, 1, tzinfo=dt.UTC).isoformat(),
            security_name="Test",
            instrument_id=1,
            quantity=50,
            proceeds_gbp=400,
            total_proceeds=400,
            total_cost=500,
            realised_gain=-100,
        )

        tax_years = _group_by_tax_year([sale1, sale2])

        assert len(tax_years) == 2
        assert tax_years[0].tax_year == "2023-24"
        assert tax_years[0].total_gain == 100
        assert tax_years[1].tax_year == "2024-25"
        assert tax_years[1].total_loss == 100


class TestNoSales:
    """Edge cases with no sell orders."""

    def test_only_buys(self) -> None:
        """Pure buy orders return empty."""
        orders = [
            _order(id=1, side="Buy", quantity=100, cost_proceeds_gbp=1000),
            _order(id=2, side="Buy", quantity=50, cost_proceeds_gbp=500),
        ]
        sales = calculate_cgt_for_instrument(orders)
        assert len(sales) == 0


class TestComplexScenarios:
    """Integration tests with mixed matching rules."""

    def test_complex_instrument(self) -> None:
        """Simulate a realistic portfolio with mixed matching rules."""
        orders = [
            # Jan 2023: Buy 500 shares (goes to pool)
            _order(id=1, order_date=dt.datetime(2023, 1, 15, tzinfo=dt.UTC), side="Buy", quantity=500, cost_proceeds_gbp=5000),
            # Jul 2023: Buy 200 shares (goes to pool)
            _order(id=2, order_date=dt.datetime(2023, 7, 1, tzinfo=dt.UTC), side="Buy", quantity=200, cost_proceeds_gbp=2400),
            # Jun 2024: Same-day buy
            _order(id=3, order_date=dt.datetime(2024, 6, 1, tzinfo=dt.UTC), side="Buy", quantity=50, cost_proceeds_gbp=600),
            # Jun 2024: Sell 100 shares
            _order(id=4, order_date=dt.datetime(2024, 6, 1, tzinfo=dt.UTC), side="Sell", quantity=100, cost_proceeds_gbp=1300),
            # Jun 2024: B&F buy (within 30 days of sell)
            _order(id=5, order_date=dt.datetime(2024, 6, 20, tzinfo=dt.UTC), side="Buy", quantity=50, cost_proceeds_gbp=650),
        ]
        sales = calculate_cgt_for_instrument(orders)

        assert len(sales) == 1
        sale = sales[0]

        # Should have same-day match (50 shares) and B&F match (50 shares)
        sd_match = [m for m in sale.matches if m.source == "same_day"]
        bf_match = [m for m in sale.matches if m.source == "b&f"]

        assert len(sd_match) == 1
        assert sd_match[0].quantity == 50.0
        assert len(bf_match) == 1
        assert bf_match[0].quantity == 50.0
        assert sale.realised_gain == 50.0  # 1300 - (600 + 650)

    def test_multiple_sells_same_year(self) -> None:
        """Multiple sells in the same tax year aggregate correctly."""
        orders = [
            _order(id=1, order_date=dt.datetime(2024, 1, 1, tzinfo=dt.UTC), side="Buy", quantity=200, cost_proceeds_gbp=2000),
            _order(id=2, order_date=dt.datetime(2024, 6, 1, tzinfo=dt.UTC), side="Sell", quantity=50, cost_proceeds_gbp=600),
            _order(id=3, order_date=dt.datetime(2024, 9, 1, tzinfo=dt.UTC), side="Sell", quantity=50, cost_proceeds_gbp=600),
        ]
        sales = calculate_cgt_for_instrument(orders)

        assert len(sales) == 2
        # Both sells from pool (avg cost 10.00 per share)
        for s in sales:
            pool_match = [m for m in s.matches if m.source == "pool"]
            assert len(pool_match) == 1
            assert pool_match[0].cost == 500.0  # 50 * 10
            assert s.realised_gain == 100.0


class TestAsyncAPI:
    """Test the async database API functions."""

    @pytest.mark.asyncio
    async def test_get_instrument_cgt_empty(self) -> None:
        """Empty session returns empty list."""
        class FakeResult:
            def scalars(self):
                r = MagicMock()
                r.all.return_value = []
                return r

        class FakeSession:
            async def execute(self, *args, **kwargs):
                return FakeResult()

        result = await get_instrument_cgt(FakeSession())
        assert result == []

    @pytest.mark.asyncio
    async def test_get_instrument_cgt_with_sales(self) -> None:
        """Instrument with buy and sell orders returns CGT data."""
        mock_inst = Instrument(
            id=1,
            security_name="TestStock",
            identifier="TEST1",
            account_name="TestAccount",
            is_cash=False,
        )
        mock_order_buy = Order(
            id=1,
            security_name="TestStock",
            order_date=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            side="Buy",
            quantity=100,
            cost_proceeds_gbp=1000,
            instrument_id=1,
        )
        mock_order_sell = Order(
            id=2,
            security_name="TestStock",
            order_date=dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
            side="Sell",
            quantity=50,
            cost_proceeds_gbp=600,
            instrument_id=1,
        )

        call_count = 0
        class FakeResult:
            def scalars(self):
                nonlocal call_count
                call_count += 1
                r = MagicMock()
                if call_count == 1:
                    r.all.return_value = [mock_inst]
                else:
                    r.all.return_value = [mock_order_buy, mock_order_sell]
                return r

        class FakeSession:
            async def execute(self, *args, **kwargs):
                return FakeResult()

        result = await get_instrument_cgt(FakeSession())
        assert len(result) == 1
        assert result[0]["instrument_id"] == 1
        assert result[0]["security_name"] == "TestStock"
        assert len(result[0]["sales"]) == 1
        assert result[0]["net_gain_gbp"] == 100.0  # 600 - (1000/100)*50

    @pytest.mark.asyncio
    async def test_get_cgt_summary_empty(self) -> None:
        """Empty instruments returns empty summary."""
        class FakeResult:
            def scalars(self):
                r = MagicMock()
                r.all.return_value = []
                return r

        class FakeSession:
            async def execute(self, *args, **kwargs):
                return FakeResult()

        result = await get_cgt_summary(FakeSession())
        assert result["instruments"] == []
        assert result["tax_year_totals"] == []
