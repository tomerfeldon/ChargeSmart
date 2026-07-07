"""Tests for the replay/simulation engine (M3).

The engine drives the fixed 5-minute cycle (Book §3.5, §4.6.5) over the repository:
detect new vehicles, read base load, compute budget, allocate, advance SoC, persist.
These tests validate the properties that only emerge over a whole run - most
importantly the end-to-end deadline guarantee and the hard limit under oversubscription
(Book Table 14).

Run against the in-memory repository with synthetic traces; the real ACN-Data dataset
plugs into the same engine later.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.db import InMemoryRepository
from app.entities import ChargerStatus, SessionStatus
from app.simulation import Arrival, run_simulation

NOW = datetime(2025, 1, 15, 22, 0, 0, tzinfo=timezone.utc)


def make_repo(limit_kw=50.0, base_load_kw=0.0, charger_cap=22.0):
    r = InMemoryRepository()
    r.seed_building(building_id=1, address="Test Bldg", max_building_power_kw=limit_kw)
    r.seed_charger(charger_id=1, building_id=1, max_power_output_kw=charger_cap)
    r.seed_charger(charger_id=2, building_id=1, max_power_output_kw=charger_cap)
    if base_load_kw:
        r.add_base_load(1, NOW, base_load_kw)
    return r


def arrival(plate, charger_id=1, start_soc=20.0, target_soc=80.0, battery=60.0,
            max_rate=11.0, conn_h=0.0, depart_h=4.0):
    return Arrival(
        connection_time=NOW + timedelta(hours=conn_h),
        charger_id=charger_id,
        license_plate=plate,
        battery_capacity_kwh=battery,
        max_charge_rate_kw=max_rate,
        start_soc=start_soc,
        target_soc=target_soc,
        departure_time=NOW + timedelta(hours=depart_h),
    )


# --- Per-cycle budget (Book §4.6.2) ----------------------------------------- #
def test_budget_is_limit_minus_base_load():
    repo = make_repo(limit_kw=50.0, base_load_kw=12.0)
    result = run_simulation(repo, 1, start=NOW, end=NOW, arrivals=[arrival("A")])
    assert result.snapshots[0].available_budget_kw == pytest.approx(38.0)


# --- Hard constraint holds at every snapshot (Book §2.1) -------------------- #
def test_limit_never_exceeded_across_run():
    repo = make_repo(limit_kw=50.0)
    arrivals = [arrival(f"V{i}", charger_id=1 + i % 2, depart_h=2.0) for i in range(10)]
    result = run_simulation(repo, 1, start=NOW, end=NOW + timedelta(hours=2), arrivals=arrivals)
    for snap in result.snapshots:
        assert snap.total_assigned_kw <= snap.available_budget_kw + 1e-9


# --- THE deadline guarantee, end to end (Book §4.6.4, Table 14) ------------- #
def test_feasible_night_meets_all_deadlines():
    # Two vehicles, ample capacity. Departures on 5-min boundaries so the discrete
    # constant-rate charge lands exactly on target.
    repo = make_repo(limit_kw=50.0)
    arrivals = [
        arrival("A", charger_id=1, start_soc=20.0, target_soc=80.0, battery=60.0, depart_h=3.0),
        arrival("B", charger_id=2, start_soc=30.0, target_soc=90.0, battery=40.0, depart_h=4.0),
    ]
    result = run_simulation(repo, 1, start=NOW, end=NOW + timedelta(hours=4), arrivals=arrivals)
    for s in [repo.get_session(1), repo.get_session(2)]:
        assert s.status == SessionStatus.COMPLETED
        assert s.current_soc >= s.target_soc - 0.01


# --- New-vehicle detection within one cycle (Book §4.6.5) ------------------- #
def test_new_vehicle_admitted_within_one_cycle():
    repo = make_repo()
    # Connects 7 minutes in - must be active by the next 5-min tick (t+10), i.e. <5 min.
    late = arrival("LATE", conn_h=7 / 60.0, depart_h=3.0)
    result = run_simulation(repo, 1, start=NOW, end=NOW + timedelta(minutes=20), arrivals=[late])
    by_time = {s.timestamp: s.active_count for s in result.snapshots}
    assert by_time[NOW] == 0                            # not connected yet
    assert by_time[NOW + timedelta(minutes=5)] == 0     # still before 7-min mark
    assert by_time[NOW + timedelta(minutes=10)] == 1    # admitted within one cycle


# --- Completion is marked and excluded thereafter --------------------------- #
def test_completed_vehicle_marked_and_excluded():
    repo = make_repo(limit_kw=50.0)
    quick = arrival("Q", start_soc=70.0, target_soc=80.0, battery=20.0, max_rate=22.0, depart_h=1.0)
    result = run_simulation(repo, 1, start=NOW, end=NOW + timedelta(hours=1), arrivals=[quick])
    s = repo.get_session(1)
    assert s.status == SessionStatus.COMPLETED
    # After completion the vehicle drops out of the active set.
    assert result.snapshots[-1].active_count == 0


# --- Decision D1 end-to-end: charger cap binds in the simulation ------------ #
def test_charger_cap_applied_in_simulation():
    repo = make_repo(limit_kw=100.0, charger_cap=7.4)
    # Needs far more than 7.4 kW worth of rate, ample budget, but charger caps it.
    hungry = arrival("H", start_soc=0.0, target_soc=100.0, battery=100.0, max_rate=22.0, depart_h=0.5)
    result = run_simulation(repo, 1, start=NOW, end=NOW + timedelta(minutes=10), arrivals=[hungry])
    assert all(snap.total_assigned_kw <= 7.4 + 1e-9 for snap in result.snapshots)


# --- Oversubscription: limit preserved even when deadlines can't all be met -- #
def test_oversubscribed_preserves_limit():
    repo = make_repo(limit_kw=20.0, charger_cap=22.0)
    arrivals = [arrival(f"O{i}", charger_id=1 + i % 2, start_soc=0.0, target_soc=100.0,
                        battery=100.0, max_rate=22.0, depart_h=1.0) for i in range(8)]
    result = run_simulation(repo, 1, start=NOW, end=NOW + timedelta(hours=1), arrivals=arrivals)
    for snap in result.snapshots:
        assert snap.total_assigned_kw <= 20.0 + 1e-9


# --- Faulted charger excludes its vehicle from allocation (Book Table 12) --- #
def test_faulted_charger_vehicle_gets_no_power():
    repo = make_repo(limit_kw=50.0)
    repo.update_charger_status(1, ChargerStatus.FAULTED)
    result = run_simulation(repo, 1, start=NOW, end=NOW, arrivals=[arrival("F", charger_id=1)])
    assert result.snapshots[0].total_assigned_kw == 0.0
