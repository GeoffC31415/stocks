"""Observed drawdown episodes from the exact valid snapshot-adjusted index."""
import datetime as dt
import math


def build_drawdown_episodes(curve: list[dict]) -> list[dict]:
    if len(curve) < 2:
        return []
    if any(type(point.get("date")) is not dt.date or not isinstance(point.get("index"), (int, float))
           or not math.isfinite(point["index"]) or point["index"] < 0 for point in curve):
        return []
    if curve[0]["index"] <= 0 or any(right["date"] <= left["date"] for left, right in zip(curve, curve[1:], strict=False)):
        return []
    episodes = []
    peak = 0
    trough: int | None = None

    def emit(end: int, recovered: bool) -> None:
        if trough is None:
            return
        peak_date, trough_date, end_date = curve[peak]["date"], curve[trough]["date"], curve[end]["date"]
        episodes.append({
            "id": f"{peak_date.isoformat()}:{trough_date.isoformat()}",
            "peak_date": peak_date, "trough_date": trough_date, "end_date": end_date,
            "depth_pct": round((curve[trough]["index"] - curve[peak]["index"]) / curve[peak]["index"] * 100, 4),
            "recovery_date": end_date if recovered else None,
            "recovery_interval_start": curve[end - 1]["date"] if recovered else None,
            "days_to_trough": (trough_date - peak_date).days,
            "elapsed_days": (end_date - peak_date).days,
            "observations": end - peak + 1,
        })

    for index in range(1, len(curve)):
        if curve[index]["index"] >= curve[peak]["index"]:
            emit(index, True)
            peak, trough = index, None  # Latest tied high anchors the next episode.
        elif trough is None or curve[index]["index"] < curve[trough]["index"]:
            trough = index  # First tied trough is retained, never an invented recovery.
    emit(len(curve) - 1, False)
    return episodes
