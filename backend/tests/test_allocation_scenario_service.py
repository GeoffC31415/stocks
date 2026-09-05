"""Contribution scenarios calculate only: no writes and no trade suggestions."""

import json

import pytest

from app.models import InstrumentGroupMember


async def test_scenario_conserves_values_and_does_not_write(target_db):
    db, client = target_db
    payload = {
        "contribution_gbp": 50,
        "allocations": [{"group_id": 1, "amount_gbp": 0}, {"group_id": 2, "amount_gbp": 50}],
        "cash_policy": "excluded",
    }
    response = await client.get(
        "/api/portfolio/allocation-scenario",
        params={"account_name": "ISA", "scenario": json.dumps(payload)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["before"]["invested_value_gbp"] == 100
    assert data["after"]["invested_value_gbp"] == 150
    assert data["after"]["excluded_cash_gbp"] == 25
    assert [g["actual_value_gbp"] for g in data["after"]["groups"]] == [60, 90]
    assert [g["drift_pp"] for g in data["after"]["groups"]] == [-10, 10]
    assert not db.new and not db.dirty and not db.deleted
    actual = (await client.get("/api/portfolio/allocation-targets?account_name=ISA")).json()
    assert actual["invested_value_gbp"] == 100


@pytest.mark.parametrize(
    "defect", ["sum", "unknown", "duplicate", "overlap", "negative", "infinite", "cash policy"]
)
async def test_scenario_rejects_invalid_inputs_and_target_sets(target_db, defect):
    db, client = target_db
    body = {
        "contribution_gbp": 50,
        "allocations": [{"group_id": 1, "amount_gbp": 50}],
        "cash_policy": "excluded",
    }
    if defect == "sum":
        body["contribution_gbp"] = 60
    elif defect == "unknown":
        body["allocations"][0]["group_id"] = 999
    elif defect == "duplicate":
        body["allocations"] = [{"group_id": 1, "amount_gbp": 25}] * 2
    elif defect == "overlap":
        db.add(InstrumentGroupMember(group_id=2, instrument_id=1))
        await db.commit()
    elif defect == "negative":
        body["contribution_gbp"] = -1
    elif defect == "infinite":
        body["contribution_gbp"] = float("inf")
    else:
        body["cash_policy"] = "spend real cash"
    response = await client.get(
        "/api/portfolio/allocation-scenario", params={"scenario": json.dumps(body)}
    )
    assert response.status_code == 422


async def test_zero_contribution_preserves_all_values(target_db):
    _, client = target_db
    body = {"contribution_gbp": 0, "allocations": [], "cash_policy": "excluded"}
    data = (
        await client.get(
            "/api/portfolio/allocation-scenario", params={"scenario": json.dumps(body)}
        )
    ).json()
    assert data["before"] == data["after"]


async def test_large_penny_allocations_sum_with_decimal_currency_precision(target_db):
    from app.allocation_scenario_schemas import ContributionScenario
    from app.allocation_target_schemas import AllocationTargets, TargetGroup
    from app.services.allocation_scenario_service import calculate_scenario
    groups=[TargetGroup(group_id=i,name=str(i),instrument_ids=[i],actual_value_gbp=100,actual_weight_pct=100/3,target_weight_pct=100/3,drift_pp=0,gap_gbp=0,within_tolerance=True) for i in (1,2,3)]
    before=AllocationTargets(status="available",account_name=None,invested_value_gbp=300,excluded_cash_gbp=0,tolerance_pp=2,reasons=[],groups=groups)
    amounts=[648607504733.08,291292048617.66,60100446649.26]
    body=ContributionScenario(contribution_gbp=1e12,cash_policy="excluded",allocations=[{"group_id":i,"amount_gbp":a} for i,a in enumerate(amounts,1)])
    assert calculate_scenario(before,body).after.invested_value_gbp==1e12+300
