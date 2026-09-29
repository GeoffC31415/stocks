"""Reserved enrollment is offline-only; all HTTP/database data is synthetic."""

import datetime as dt
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_gate_a_hl_pair import ACTIVITY, HOLDINGS, enroll_synthetic_hl_owner

from app.database import get_session
from app.models import AccountAlias, Base
from app.routers.matching import router as matching_router
from app.services.hl_parser import HLParseError, hl_client_identity_key
from app.services.hl_sync_service import import_pair

ALIASES = "/api/matching/account-aliases"
RESERVED = "hl-client-identity"
CANONICAL = "HL Fund & Share Account"


@asynccontextmanager
async def synthetic_api(tmp_path):
    # Own the app as well as its database. The global app's optional frontend
    # mount fully matches unsupported API methods before the router can emit
    # 405, then rejects the API namespace with 404. Test the real matching
    # router without that unrelated deployment-dependent fallback/shared state.
    app = FastAPI()
    app.include_router(matching_router)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'synthetic-aliases.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def isolated_session():
        async with factory() as session:
            yield session

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        app.dependency_overrides[get_session] = isolated_session
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://synthetic"
        ) as client:
            yield factory, client
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def database_state(factory):
    """Read every persisted row in a new session, not an ORM identity cache."""
    async with factory() as reader:
        return {
            table.name: (await reader.execute(select(table).order_by(*table.primary_key))).all()
            for table in Base.metadata.sorted_tables
        }


def reserved_payload():
    return {
        "source": RESERVED,
        "source_account_name": hl_client_identity_key("Different Person", "OTHER-001"),
        "canonical_account_name": CANONICAL,
        "notes": "Synthetic attempted web enrollment",
    }


async def test_generic_api_cannot_enroll_reserved_hl_owner(tmp_path):
    async with synthetic_api(tmp_path) as (factory, client):
        before = await database_state(factory)
        response = await client.post(ALIASES, json=reserved_payload())
        assert response.status_code == 403
        assert await database_state(factory) == before


@pytest.mark.parametrize("misleading_fields", [False, True])
async def test_generic_api_cannot_delete_reenroll_then_import_changed_hl_owner(
    tmp_path, misleading_fields
):
    async with synthetic_api(tmp_path) as (factory, client):
        # Trusted, direct ORM enrollment remains supported, and a real import
        # establishes holdings/orders that a smaller impostor pair would change.
        async with factory() as operator:
            await enroll_synthetic_hl_owner(operator)
            imported = await import_pair(
                operator, HOLDINGS.encode(), ACTIVITY.encode(), as_of=dt.date(2026, 9, 29)
            )
            assert imported["snapshot"] == imported["orders"] == "imported"
        async with factory() as reader:
            pin_id = await reader.scalar(select(AccountAlias.id))
        before = await database_state(factory)
        deletion = await client.request(
            "DELETE",
            f"{ALIASES}/{pin_id}",
            params={"source": "holdings"} if misleading_fields else None,
            json={"source": "holdings", "canonical_account_name": "Other alias"}
            if misleading_fields
            else None,
        )
        after_delete = await database_state(factory)
        recreation = await client.post(ALIASES, json=reserved_payload())
        after_recreate = await database_state(factory)
        holdings = (
            HOLDINGS.replace("TWO,Two,2,1000,20,18,11.11\n", "")
            .replace("Stock value:,30", "Stock value:,10")
            .replace("Number of holdings:,2", "Number of holdings:,1")
            .replace(",Totals,,,30,27,", ",Totals,,,10,9,")
        )
        activity = ACTIVITY
        for old, new in [("Synthetic Person", "Different Person"), ("SYNTHETIC-001", "OTHER-001")]:
            holdings, activity = holdings.replace(old, new), activity.replace(old, new)
        rejected = False
        async with factory() as importer:
            try:
                await import_pair(
                    importer, holdings.encode(), activity.encode(), as_of=dt.date(2026, 9, 29)
                )
            except HLParseError as error:
                assert "owner identity" in str(error)
                rejected = True
            await importer.commit()  # Catching an error must not leak any writes.
        assert rejected, "HTTP delete/re-enrollment allowed an actual changed-owner import"
        assert deletion.status_code == recreation.status_code == 403
        assert after_delete == after_recreate == await database_state(factory) == before


async def test_generic_alias_list_hides_private_hl_enrollment(tmp_path):
    async with synthetic_api(tmp_path) as (factory, client):
        async with factory() as operator:
            await enroll_synthetic_hl_owner(operator)
            pin = await operator.scalar(select(AccountAlias))
            pin.notes = "PRIVATE synthetic enrollment evidence"
            await operator.commit()
        created = await client.post(
            ALIASES,
            json={
                "source": "holdings",
                "source_account_name": "Synthetic HL alias",
                "canonical_account_name": CANONICAL,
            },
        )
        assert created.status_code == 201
        before = await database_state(factory)
        listed = await client.get(ALIASES)
        assert listed.status_code == 200
        assert listed.json() == [created.json()]
        assert await database_state(factory) == before


@pytest.mark.parametrize("source", ["holdings", "barclays_orders", "hl-client-identity-other"])
async def test_ordinary_alias_crud_is_not_classified_by_private_looking_fields(tmp_path, source):
    async with synthetic_api(tmp_path) as (factory, client):
        payload = reserved_payload() | {"source": source}
        created = await client.post(ALIASES, json=payload)
        assert created.status_code == 201
        alias_id = created.json()["id"]
        async with factory() as reader:
            alias = await reader.get(AccountAlias, alias_id)
            assert alias.source == source
            assert alias.source_account_name == payload["source_account_name"]
        listed = await client.get(ALIASES)
        assert listed.json() == [created.json()]
        deleted = await client.delete(f"{ALIASES}/{alias_id}")
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True}
        async with factory() as reader:
            assert await reader.get(AccountAlias, alias_id) is None
        missing = await client.delete(f"{ALIASES}/{alias_id}")
        assert missing.status_code == 404


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
async def test_no_generic_update_or_upsert_can_rewrite_reserved_pin(tmp_path, method):
    async with synthetic_api(tmp_path) as (factory, client):
        async with factory() as operator:
            await enroll_synthetic_hl_owner(operator)
        async with factory() as reader:
            pin_id = await reader.scalar(select(AccountAlias.id))
        before = await database_state(factory)
        for path in [ALIASES, f"{ALIASES}/{pin_id}"]:
            response = await client.request(method, path, json=reserved_payload())
            assert response.status_code == 405
            assert response.json() == {"detail": "Method Not Allowed"}
            assert method not in response.headers["allow"].split(", ")
            assert await database_state(factory) == before
