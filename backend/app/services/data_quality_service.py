"""Scope-aware data facts and personal reminders; GETs never refresh or write."""
import datetime as dt
import hashlib
import json
from urllib.parse import urlencode

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order
from app.services.data_quality_market import cached_prerequisites
from app.services.performance_service import get_portfolio_performance
from app.services.portfolio_service import build_portfolio_summary, get_current_snapshots


async def get_data_confidence(
    session: AsyncSession, *, account_name: str | None = None, period: str = "ALL",
    stale_after_days: int = 14, today: dt.date | None = None,
) -> dict:
    if not 1 <= stale_after_days <= 365:
        raise ValueError("Freshness tolerance must be between 1 and 365 days.")
    today = today or dt.datetime.now(dt.UTC).date()
    summary = await build_portfolio_summary(session, account_name=account_name)
    snapshots = await get_current_snapshots(session, account_name=account_name)
    performance = await get_portfolio_performance(session, account_name=account_name, period=period)
    query = select(func.count(Order.id), func.min(Order.order_date), func.max(Order.order_date),
                   func.sum(case((Order.instrument_id.is_(None), 1), else_=0)),
                   func.sum(case((Order.match_status == "auto_review", 1), else_=0)))
    if account_name is not None:
        query = query.where(Order.account_name == account_name)
    count, first, last, unmatched, review = (await session.execute(query)).one()
    transactions = {"count": count, "first_date": first.date() if first else None,
                    "last_date": last.date() if last else None, "unmatched_count": unmatched or 0,
                    "review_count": review or 0, "completeness": "unknown"}
    freshness = [{**row, "age_days": max(0, (today - row["date"]).days)} for row in summary["scope"]["valuation_dates"]]
    holdings = [s for s in snapshots if not s.instrument.is_cash and (s.value_gbp or 0) > 0]
    total = sum(s.value_gbp or 0 for s in holdings)
    classification = {}
    for dimension in ("asset_class", "sector", "region"):
        classified = [s for s in holdings if (getattr(s.instrument, dimension) or "").strip()]
        classified_value = sum(s.value_gbp or 0 for s in classified)
        classification[dimension] = {
            "holding_count": len(holdings), "classified_count": len(classified),
            "classified_count_pct": len(classified) / len(holdings) * 100 if holdings else 0,
            "total_value_gbp": total, "classified_value_gbp": classified_value,
            "classified_value_pct": classified_value / total * 100 if total else 0,
        }
    reasons = {reason["code"]: reason for metric in performance["metrics"].values() for reason in metric["reasons"]}
    items = []

    def attention(code: str, title: str, evidence: list[str], target: str, *, severity: str = "warning", category: str = "fact") -> None:
        path, _, target_query = target.partition("?")
        params = {"account": account_name or "all", "period": period}
        href = path + "?" + urlencode(params) + ("&" + target_query if target_query else "")
        signature = json.dumps([code, account_name, period, evidence, stale_after_days], sort_keys=True)
        items.append({"id": code, "title": title, "category": category, "severity": severity,
                      "evidence": evidence, "evidence_key": hashlib.sha256(signature.encode()).hexdigest(),
                      "account_name": account_name, "period": period, "action_href": href,
                      "dismissible": severity != "critical"})

    chain = performance["metrics"]["total_return_pct"]
    if chain["status"] == "unavailable":
        attention("performance_unavailable", "Snapshot return needs attention",
                  [r["message"] for r in chain["reasons"]], "/portfolio?tab=performance", severity="critical")
    if not snapshots:
        attention("no_snapshots", "No current holdings in scope", ["Import a snapshot or select another account."], "/data?tab=import", severity="info")
    stale = [row for row in freshness if row["age_days"] > stale_after_days]
    if stale:
        attention("snapshot_freshness", "Snapshots exceed your freshness tolerance",
                  [f"{r['account_name']}: latest valuation {r['date'].isoformat()} (tolerance {stale_after_days} days)." for r in stale],
                  "/data?tab=import", category="rule")
    if unmatched or review:
        attention("order_matching", "Transactions need matching review",
                  [f"{unmatched or 0} unmatched and {review or 0} review-marked transactions in this account scope.",
                   "Matching opens the global queue; retain the account context when reviewing."], "/data?tab=matching")
    incomplete = [dimension for dimension, row in classification.items() if row["classified_count"] < row["holding_count"]]
    if incomplete:
        attention("classification", "Some holdings lack classification",
                  [f"{dimension.replace('_', ' ')}: {classification[dimension]['classified_value_pct']:.1f}% of positive non-cash value classified." for dimension in incomplete],
                  "/data?tab=classifications")
    if count == 0:
        attention("transaction_history", "No recorded transactions in scope", ["Absence of orders does not prove zero flows or zero income."], "/data?tab=import")
    if summary["scope"]["warnings"]:
        attention("snapshot_coverage", "Current-value coverage notes", summary["scope"]["warnings"], "/data?tab=import")
    return {"scope": performance["scope"], "evaluated_on": today, "stale_after_days": stale_after_days,
            "snapshots": freshness, "transactions": transactions, "classification": classification,
            "market_history": await cached_prerequisites(session, snapshots, summary["as_of_date"]),
            "metric_reasons": list(reasons.values()), "attention": items}
