"""Target-set contracts use synthetic in-memory databases only."""


import pytest

from app.models import (
    HoldingSnapshot,
    InstrumentGroup,
    InstrumentGroupMember,
)


@pytest.mark.parametrize(
    "defect",
    ["overlap", "unassigned", "missing target", "target sum", "negative target", "missing value"],
)
async def test_invalid_target_sets_keep_tags_but_suppress_actionable_gaps(target_db, defect):
    db, client = target_db
    if defect == "overlap":
        db.add(InstrumentGroupMember(group_id=2, instrument_id=1))
    elif defect == "unassigned":
        member = await db.get(InstrumentGroupMember, 3)
        await db.delete(member)
    elif defect == "missing value":
        (await db.get(HoldingSnapshot, 1)).value_gbp = None
    else:
        (await db.get(InstrumentGroup, 1)).target_allocation_pct = {
            "missing target": None,
            "target sum": 40,
            "negative target": -5,
        }[defect]
    await db.commit()
    data = (await client.get("/api/portfolio/allocation-targets?account_name=ISA")).json()
    assert data["status"] == "unavailable"
    assert data["reasons"]
    assert all(
        r["gap_gbp"] is None and r["drift_pp"] is None and r["within_tolerance"] is None
        for r in data["groups"]
    )
    assert len(data["groups"]) == 2


async def test_exclusive_targets_use_scoped_cash_excluded_denominator(target_db):
    _, client = target_db
    response = await client.get(
        "/api/portfolio/allocation-targets?account_name=ISA&tolerance_pp=12"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "available"
    assert data["invested_value_gbp"] == 100
    assert data["excluded_cash_gbp"] == 25
    core = data["groups"][0]
    assert (
        core["actual_weight_pct"],
        core["target_weight_pct"],
        core["drift_pp"],
        core["gap_gbp"],
    ) == (60, 50, 10, -10)
    assert core["within_tolerance"] is True
    assert sum(row["gap_gbp"] for row in data["groups"]) == 0
    combined = (await client.get("/api/portfolio/allocation-targets")).json()
    assert combined["invested_value_gbp"] == 200
    assert combined["groups"][0]["actual_weight_pct"] == 80


async def test_group_analysis_and_drilldown_members_share_account_scope(target_db):
    _, client = target_db
    data = (await client.get("/api/groups/performance?account_name=ISA")).json()
    core = next(g for g in data if g["group_id"] == 1)
    assert core["total_current_value_gbp"] == 60
    assert {m["instrument_id"] for m in core["members"]} == {1}


@pytest.mark.parametrize("cash", [None, float("inf"), float("-inf")])
async def test_unknown_cash_is_disclosed_and_cannot_feed_a_scenario(target_db,cash):
    db,client=target_db
    (await db.get(HoldingSnapshot,4)).value_gbp=cash
    await db.commit()
    data=(await client.get("/api/portfolio/allocation-targets?account_name=ISA")).json()
    assert data["status"]=="unavailable"
    assert data["excluded_cash_gbp"] is None
    assert any("cash" in r.lower() for r in data["reasons"])
