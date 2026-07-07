"""Tests for the statistical analysis module (M7).

These encode Book §5.4 / Table 15: the measures that characterise a simulated charging
night, plus the headline managed-vs-uncontrolled comparison - the uncontrolled baseline
crosses the building limit while the managed regime never does.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.analysis import NightStatistics, summarize, unmanaged_load_series
from app.db import InMemoryRepository
from app.simulation import Arrival, run_simulation

NOW = datetime(2025, 1, 15, 22, 0, 0, tzinfo=timezone.utc)


def make_repo(limit_kw=50.0, base_load_kw=0.0, n_chargers=8, charger_cap=22.0):
    r = InMemoryRepository()
    r.seed_building(1, "Test Bldg", limit_kw)
    for cid in range(1, n_chargers + 1):
        r.seed_charger(cid, 1, charger_cap)
    if base_load_kw:
        r.add_base_load(1, NOW, base_load_kw)
    return r


def arr(plate, charger_id, start_soc=20.0, target_soc=80.0, battery=60.0, max_rate=11.0, conn_h=0.0, depart_h=4.0):
    return Arrival(
        connection_time=NOW + timedelta(hours=conn_h), charger_id=charger_id, license_plate=plate,
        battery_capacity_kwh=battery, max_charge_rate_kw=max_rate, start_soc=start_soc,
        target_soc=target_soc, departure_time=NOW + timedelta(hours=depart_h),
    )


# --- Table 15 metrics -------------------------------------------------------- #
def test_feasible_night_is_100_percent_on_time():
    repo = make_repo(limit_kw=50.0)
    # Both genuinely feasible: required rate stays under the 11 kW vehicle max.
    # A: 30 kWh over 3 h = 10 kW.  B: 36 kWh over 4 h = 9 kW.
    arrivals = [arr("A", 1, target_soc=70.0, depart_h=3.0), arr("B", 2, depart_h=4.0)]
    result = run_simulation(repo, 1, NOW, NOW + timedelta(hours=4), arrivals=arrivals)
    stats = summarize(result)
    assert isinstance(stats, NightStatistics)
    assert stats.on_time_completion_rate == pytest.approx(1.0)


def test_peak_utilization_never_exceeds_one():
    repo = make_repo(limit_kw=20.0)  # tight limit -> oversubscribed
    arrivals = [arr(f"V{i}", 1 + i % 8, start_soc=0, target_soc=100, battery=80, max_rate=22, depart_h=1.0) for i in range(8)]
    result = run_simulation(repo, 1, NOW, NOW + timedelta(hours=1), arrivals=arrivals)
    stats = summarize(result)
    assert stats.peak_utilization <= 1.0 + 1e-9


def test_mean_building_load_includes_base_load():
    repo = make_repo(limit_kw=50.0, base_load_kw=10.0)
    result = run_simulation(repo, 1, NOW, NOW + timedelta(hours=2), arrivals=[arr("A", 1, depart_h=2.0)])
    stats = summarize(result)
    # Mean aggregate load must account for the 10 kW base load floor.
    assert stats.mean_building_load_kw >= 10.0


def test_congested_night_has_positive_waiting_time():
    repo = make_repo(limit_kw=11.0, n_chargers=4)  # only ~1 vehicle worth of power
    arrivals = [arr(f"W{i}", 1 + i % 4, start_soc=0, target_soc=100, battery=80, max_rate=11, depart_h=3.0) for i in range(4)]
    result = run_simulation(repo, 1, NOW, NOW + timedelta(hours=3), arrivals=arrivals)
    stats = summarize(result)
    assert stats.mean_waiting_minutes > 0.0
    assert stats.std_waiting_minutes >= 0.0


# --- Managed vs. uncontrolled baseline (Book §5.4) -------------------------- #
def test_uncontrolled_baseline_exceeds_limit_while_managed_does_not():
    limit = 50.0
    repo = make_repo(limit_kw=limit, n_chargers=8)
    arrivals = [arr(f"U{i}", 1 + i, start_soc=0, target_soc=100, battery=80, max_rate=11, depart_h=2.0) for i in range(8)]
    result = run_simulation(repo, 1, NOW, NOW + timedelta(hours=2), arrivals=arrivals)
    managed = summarize(result)

    unmanaged = unmanaged_load_series(repo, 1, arrivals, NOW, NOW + timedelta(hours=2))
    unmanaged_peak = max(load for _, load in unmanaged)

    # 8 vehicles * 11 kW = 88 kW uncontrolled - well over the 50 kW limit.
    assert unmanaged_peak > limit
    assert managed.peak_load_kw <= limit + 1e-9
