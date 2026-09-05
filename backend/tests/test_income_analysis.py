"""Income is an analysis of stored reinvestment classifications, not dividends."""

import datetime as dt

from app.models import Instrument, Order, OrderImportBatch


async def seed_income(db):
    db.add(OrderImportBatch(id=1, file_sha256="i" * 64, row_count=7))
    (await db.get(Instrument, 2)).closed_at = dt.datetime(2026, 1, 2)
    rows = [
        (1, 1, "ISA", "2025-01-02", 20, True),
        (2, 1, "ISA", "2026-01-02", 30, True),
        (3, 2, "ISA", "2025-02-28", 10, True),
        (4, 2, "ISA", "2026-02-28", 15, True),
        (5, 1, "ISA", "2026-02-28", 5, False),
        (6, 3, "SIPP", "2026-02-28", 100, True),
        (7, 1, "ISA", "2025-03-01", 999, True),
    ]
    for ident, inst, account, date, value, drip in rows:
        db.add(
            Order(
                id=ident,
                order_import_batch_id=1,
                instrument_id=inst,
                security_name="Same name",
                order_date=dt.datetime.fromisoformat(date),
                order_status="Completed",
                account_name=account,
                side="Buy",
                cost_proceeds_gbp=value,
                is_drip=drip,
                order_fingerprint=str(ident).zfill(64),
            )
        )
    await db.commit()


async def test_income_compares_matching_calendar_periods_and_reconciles_drivers(target_db):
    db, client = target_db
    await seed_income(db)
    response = await client.get("/api/orders/income?account_name=ISA&as_of=2026-02-28")
    assert response.status_code == 200
    data = response.json()
    assert data["basis"] == "stored_import_classification"
    assert (data["current_recorded_gbp"], data["prior_recorded_gbp"], data["change_gbp"]) == (
        45,
        30,
        15,
    )
    assert data["prior_end"] == "2025-02-28"
    assert sum(x["change_gbp"] for x in data["drivers"]) == 15
    assert {x["holding_status"] for x in data["drivers"]} == {"current", "closed"}
    assert data["latest_transaction_date"] == "2026-02-28"
    assert data["completeness"] == "unknown"
    assert data["months"][1]["current_recorded_gbp"] == 15
    assert data["warnings"]


async def test_detail_orders_respect_explicit_non_drip_classification(target_db):
    db, client = target_db
    await seed_income(db)
    data = (await client.get("/api/instruments/1/orders?drip_threshold=10000")).json()
    assert next(x for x in data if x["id"] == 5)["is_drip"] is False


async def test_missing_amounts_and_empty_months_are_not_income_zero(target_db):
    db, client = target_db
    await seed_income(db)
    (await db.get(Order, 2)).cost_proceeds_gbp = None
    await db.commit()
    data = (await client.get("/api/orders/income?account_name=ISA&as_of=2026-03-31")).json()
    assert data["current_recorded_gbp"] is None and data["change_gbp"] is None
    assert data["months"][2]["current_recorded_gbp"] is None


async def test_leap_day_comparison_clamps_prior_year_and_filters_future(target_db):
    db, client = target_db
    await seed_income(db)
    data = (await client.get("/api/orders/income?account_name=ISA&as_of=2024-02-29")).json()
    assert data["prior_end"] == "2023-02-28"
    assert data["current_count"] == 0
    assert data["latest_transaction_date"] is None
    assert data["drivers"] == []


async def test_unvalidated_all_history_denominator_cannot_publish_trailing_yield(target_db):
    db, client = target_db
    await seed_income(db)
    data = (await client.get("/api/orders/positions?account_name=ISA")).json()
    assert all(x["trailing_drip_yield_pct"] is None for x in data)
    assert all(x["trailing_drip_yield_reason"] for x in data)


async def test_legacy_list_preserves_stored_classification_at_every_threshold(target_db):
    db, client = target_db
    await seed_income(db)
    for threshold in (1, 10000):
        data = (await client.get(f"/api/orders?account_name=ISA&drip_threshold={threshold}")).json()
        assert next(x for x in data if x["id"] == 5)["is_drip"] is False
        assert next(x for x in data if x["id"] == 2)["is_drip"] is True


async def test_linked_order_source_account_kept_but_navigation_uses_verified_instrument_account(target_db):
    db,client=target_db
    await seed_income(db)
    (await db.get(Order,2)).account_name="Broker source alias"
    await db.commit()
    data=(await client.get("/api/orders/income?account_name=ISA&as_of=2026-02-28")).json()
    assert data["current_recorded_gbp"]==45
    assert all(d["navigation_account"]=="ISA" for d in data["drivers"])
    page=(await client.get("/api/orders/page?account_name=ISA&instrument_ids=1&kind=drip")).json()
    assert 2 in {x["id"] for x in page["items"]}
    assert next(x for x in page["items"] if x["id"]==2)["account_name"]=="Broker source alias"


async def test_source_account_alias_does_not_erase_contributor_drilldown(target_db):
    from app.models import HoldingSnapshot, ImportBatch
    db,client=target_db
    await seed_income(db)
    for ident in (1,2,3,4,5,7):
        (await db.get(Order,ident)).account_name="Broker source alias"
    db.add(ImportBatch(id=2,as_of_date=dt.date(2026,2,28),file_sha256="b"*64))
    for ident,value in ((1,120),(2,50),(4,25)):
        db.add(HoldingSnapshot(import_batch_id=2,instrument_id=ident,investment_label=str(ident),value_gbp=value,value_ccy="GBP"))
    await db.commit()
    data=(await client.get("/api/portfolio/attribution?account_name=ISA&from_batch_id=1&to_batch_id=2")).json()
    assert data["movements"]
    assert not any("No imported order history" in n for n in data["notes"])
