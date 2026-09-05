import datetime as dt

import pytest

from app.services.drawdown_service import build_drawdown_episodes
from app.services.performance_service import max_flow_adjusted_drawdown


def curve(values):
    return [{"date": dt.date(2026, 1, 1) + dt.timedelta(days=day * 3), "index": value} for day, value in enumerate(values)]


def test_recovered_and_unrecovered_episodes_match_the_exact_index_depth():
    points = curve([100, 120, 90, 100, 120, 110, 80])
    episodes = build_drawdown_episodes(points)
    assert len(episodes) == 2
    first, last = episodes
    assert first["depth_pct"] == -25
    assert first["peak_date"] == points[1]["date"]
    assert first["trough_date"] == points[2]["date"]
    assert first["recovery_interval_start"] == points[3]["date"]
    assert first["recovery_date"] == points[4]["date"]
    assert first["days_to_trough"] == 3
    assert first["elapsed_days"] == 9
    assert first["observations"] == 4
    assert last["recovery_date"] is None
    assert last["end_date"] == points[-1]["date"]
    assert min(row["depth_pct"] for row in episodes) == max_flow_adjusted_drawdown(points)


def test_tied_peaks_use_latest_high_and_tied_troughs_use_first_observation():
    points = curve([100, 100, 90, 90, 100, 100, 80])
    first, last = build_drawdown_episodes(points)
    assert first["peak_date"] == points[1]["date"]
    assert first["trough_date"] == points[2]["date"]
    assert last["peak_date"] == points[5]["date"]


@pytest.mark.parametrize("values", [[], [100], [100, 100, 100], [100, 110, 120], [100, None, 80], [100, float("inf")], [0, 10], [100, -1]])
def test_flat_insufficient_or_invalid_chains_have_no_episodes(values):
    assert build_drawdown_episodes(curve(values)) == []


def test_total_loss_is_a_real_unrecovered_episode():
    episode = build_drawdown_episodes(curve([100, 0, 0]))[0]
    assert episode["depth_pct"] == -100
    assert episode["recovery_date"] is None
    assert episode["observations"] == 3


def test_duplicate_or_reversed_dates_do_not_publish_episodes():
    points = curve([100, 90, 100])
    points[1]["date"] = points[0]["date"]
    assert build_drawdown_episodes(points) == []
    assert build_drawdown_episodes(list(reversed(curve([100, 90, 100])))) == []
