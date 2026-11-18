"""Worker report contract. Only the provider result, DB session and unit state are fakes."""

import datetime as dt
import json
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app import sync_cli, trading212_cli
from app.routers import trading212 as router
from app.services import sync_control as control
from app.services import sync_runner as runner
from app.services.sync_freshness import verified_sections
from app.services.trading212 import Trading212DataError

SECTIONS = {"holdings", "cash", "orders", "transactions"}
BASELINE = "2026-01-15T12:00:00+00:00"
CHECK = "2026-01-16T12:00:00+00:00"
RECOVERY = "2026-01-18T12:00:00+00:00"


def complete(stamp):
    observed = dt.datetime.fromisoformat(stamp)
    return router.Trading212SyncResult(
        account_name="PRIVATE_ACCOUNT",
        snapshot="imported",
        orders="unchanged",
        cash_flows_imported=0,
        cash_flows_total=0,
        fetched_at=observed,
        valuation_at=observed.date(),
    )


def incident(code, endpoint, phase):
    error = Trading212DataError("PRIVATE_PROVIDER_BODY", code=code)
    vars(error).update(t212_endpoint=endpoint, t212_phase=phase)
    return error


def incomplete(*, history):
    # A single snapshot incident affects BOTH valuation sections. No fresh
    # portfolio/cash valuation, even if an independent history section verified.
    sections = {
        name: {
            "status": "needs_attention",
            "reason_code": "permission_denied",
            "action_code": "operator_review",
        }
        for name in ("holdings", "cash")
    }
    sections["transactions"] = {"status": "failed"}
    errors: list[Exception] = [
        incident("account_summary_forbidden", "account_summary", "fetch"),
        incident("invalid_cash_pagination", "transactions", "fetch"),
    ]
    if history:
        sections.update(
            verified_sections({"orders": "unchanged"}, CHECK, None, coverage={"orders": "complete"})
        )
    else:
        sections["orders"] = {"status": "failed"}
        errors.append(incident("invalid_order_pagination", "orders", "fetch"))
    return router.Trading212Incomplete(sections=sections, errors=errors)


def configure(monkeypatch, tmp_path, *, dedicated):
    inbox = tmp_path / "inbox"
    public = tmp_path / "public"
    private = inbox / "trading212" if dedicated else inbox
    status = public / "trading212" if dedicated else public
    monkeypatch.setattr(runner.settings, "sync_inbox", inbox)
    monkeypatch.setattr(runner.settings, "sync_status_dir", status)
    monkeypatch.setattr(runner, "_trading212_configured", lambda: True)
    monkeypatch.setattr(router, "get_trading212_client", object)
    monkeypatch.setattr(runner.logger, "disabled", False)
    worker = trading212_cli if dedicated else sync_cli
    session = AsyncMock()

    @asynccontextmanager
    async def sessions():
        yield session

    monkeypatch.setattr(worker, "SessionLocal", sessions)
    if not dedicated:
        monkeypatch.setattr(sync_cli, "init_db", AsyncMock())
        monkeypatch.setattr(sys, "argv", ["sync_cli", "--no-fetch", "--json"])
    return worker, session, private, status


@pytest.mark.parametrize("dedicated", [False, True], ids=["general", "dedicated"])
def test_complete_partial_failed_and_recovered_reports(
    tmp_path, monkeypatch, caplog, capsys, dedicated
):
    worker, session, private, status_dir = configure(monkeypatch, tmp_path, dedicated=dedicated)
    control_dir = tmp_path / "requests" / ("trading212" if dedicated else "general")
    monkeypatch.setattr(control, "service_snapshot", lambda **kw: ("inactive", None))

    def invoke(result, invocation, expected):
        caplog.clear()
        monkeypatch.setenv("INVOCATION_ID", invocation)
        control.atomic_json(
            control_dir / "sync-request.json",
            {
                "state": "accepted",
                "requested_at": 1,
                "request_id": "request-" + invocation,
                "target_invocation_id": invocation,
            },
        )

        async def sync(session, client):
            # The journal and publication must bind to the invocation at START.
            monkeypatch.setenv("INVOCATION_ID", "PRIVATE_LATE_INVOCATION")
            return result

        monkeypatch.setattr(router, "run_trading212_worker_sync", sync)
        with pytest.raises(SystemExit) as exit_status:
            worker.main()
        assert exit_status.value.code == (0 if expected == "complete" else 1)
        private_json = (private / "last-sync.json").read_text()
        public_json = (status_dir / "last-sync.json").read_text()
        output = capsys.readouterr().out
        persisted = json.loads(public_json)
        assert persisted["invocation_id"] == invocation
        request = control.service_sync_status(
            control_dir, status_dir=status_dir, trading212=dedicated
        )
        assert request["request_id"] == "request-" + invocation
        assert request["state"] == ("completed" if expected == "complete" else "failed")
        report = request["last_run"]
        assert report["outcome"] == expected and report["ok"] == (expected == "complete")
        step = report["steps"][-1]
        assert step["name"] == "Trading 212" and step["detail"] is None
        assert step["sections"] == report["freshness"]["Trading 212"]
        assert set(step["sections"]) == SECTIONS
        assert all(s["last_attempt_at"] == report["started_at"] for s in step["sections"].values())
        assert "PRIVATE_" not in public_json + private_json + output + caplog.text
        assert "errors" not in private_json + public_json + output
        assert "invalid_cash_pagination" not in private_json + public_json + output
        session.rollback.assert_not_awaited()
        return step

    unit_id = "d" if dedicated else "a"
    first = invoke(complete(BASELINE), unit_id + "1" * 31, "complete")
    partial_id = unit_id + "2" * 31
    partial = invoke(incomplete(history=True), partial_id, "partial")
    assert partial["status"] == "committed_with_attention"
    for name in ("holdings", "cash", "transactions"):
        actual = partial["sections"][name]
        previous = first["sections"][name]
        assert (actual["verified_at"], actual["valuation_at"], actual["coverage"]) == (
            previous["verified_at"],
            previous["valuation_at"],
            previous["coverage"],
        )
    assert partial["sections"]["cash"]["reason_code"] == "permission_denied"
    assert partial["sections"]["orders"]["status"] == "unchanged"
    assert partial["sections"]["orders"]["verified_at"] == CHECK
    records = [r for r in caplog.records if r.name == runner.__name__]
    assert len(records) == 2
    for record, diagnosis in zip(
        records,
        [
            "account_summary_forbidden endpoint=account_summary phase=fetch",
            "invalid_cash_pagination endpoint=transactions phase=fetch",
        ],
        strict=True,
    ):
        assert record.getMessage().startswith("Trading 212 section failed ")
        assert f"code={diagnosis} invocation_id={partial_id} " in record.getMessage()
        assert record.exc_info is None
    failed = invoke(incomplete(history=False), unit_id + "3" * 31, "failed")
    assert failed["status"] == "failed"
    assert failed["sections"]["orders"]["verified_at"] == CHECK
    assert failed["sections"]["holdings"]["valuation_at"] == "2026-01-15"
    assert len([r for r in caplog.records if r.name == runner.__name__]) == 3
    recovered = invoke(complete(RECOVERY), unit_id + "4" * 31, "complete")
    assert recovered["status"] == "ok"
    assert {s["verified_at"] for s in recovered["sections"].values()} == {RECOVERY}
    assert recovered["sections"]["cash"]["valuation_at"] == "2026-01-18"
    assert {s["action_code"] for s in recovered["sections"].values()} == {"none"}


@pytest.mark.parametrize("public", [True, False], ids=["configured-public", "private-only"])
async def test_dedicated_carries_only_scrubbed_scoped_evidence_before_fetch(
    tmp_path, monkeypatch, public
):
    _, _, private, status_dir = configure(monkeypatch, tmp_path, dedicated=True)
    if not public:
        monkeypatch.setattr(runner.settings, "sync_status_dir", None)
        status_dir = private
    previous = {
        "schema_version": 2,
        "started_at": BASELINE,
        "finished_at": BASELINE,
        "freshness": {
            "Trading 212": {
                "cash": {
                    "verified_at": BASELINE,
                    "valuation_at": "2026-01-15",
                    "coverage": "complete",
                    "private_field": "PRIVATE_BODY",
                    "coverage_start": "PRIVATE_DATE",
                }
            }
        },
    }
    control.atomic_json(status_dir / "last-sync.json", previous)
    previous["freshness"]["Trading 212"]["cash"]["verified_at"] = RECOVERY
    unrelated = status_dir.parent / "last-sync.json"
    control.atomic_json(unrelated, previous)
    unrelated_bytes = unrelated.read_bytes()

    initial = {}

    async def sync(session, client):
        initial.update(json.loads((private / "last-sync.json").read_text()))
        return incomplete(history=False)

    monkeypatch.setattr(router, "run_trading212_worker_sync", sync)
    assert await trading212_cli.run() == 1
    for report in (initial, json.loads((status_dir / "last-sync.json").read_text())):
        assert "PRIVATE_" not in json.dumps(report)
        cash = report["freshness"]["Trading 212"]["cash"]
        assert cash["last_attempt_at"] == report["started_at"]
        assert cash["verified_at"] == BASELINE and cash["valuation_at"] == "2026-01-15"
        assert cash["coverage"] == "complete" and cash["coverage_start"] is None
    assert (
        initial["finished_at"] is None
        and initial["freshness"]["Trading 212"]["cash"]["status"] == "running"
    )
    assert unrelated.read_bytes() == unrelated_bytes
