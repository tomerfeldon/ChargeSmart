"""Unit tests for the pure scheduling core (M1).

These are written test-first. They encode the Book's specification directly:
  - urgency formula and worked example (Book §4.6.1, Table 10)
  - greedy allocation with the hard power constraint (Book §2.1, §4.6)
  - the 4th constraint: charger.max_power_output_kw (decision D1)
  - edge cases and tie-breaking (Book Table 12, §4.6.4)
  - SoC advancement per 5-minute step (implied physics)

The scheduler is pure: it takes plain dataclasses and `now`, returns allocations.
No DB, no network, no FastAPI.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.scheduler import (
    Allocation,
    VehicleSession,
    advance_soc,
    allocate,
    compute_urgency,
    energy_required_kwh,
    time_until_departure_hours,
)

NOW = datetime(2025, 1, 15, 22, 0, 0, tzinfo=timezone.utc)


def make_session(
    session_id=1,
    current_soc=0.0,
    target_soc=50.0,
    battery_capacity_kwh=64.0,
    max_charge_rate_kw=100.0,
    charger_max_power_kw=100.0,
    hours_until_departure=8.0,
):
    return VehicleSession(
        session_id=session_id,
        current_soc=current_soc,
        target_soc=target_soc,
        battery_capacity_kwh=battery_capacity_kwh,
        max_charge_rate_kw=max_charge_rate_kw,
        charger_max_power_kw=charger_max_power_kw,
        departure_time=NOW + timedelta(hours=hours_until_departure),
    )


# --- Formulas (Book §4.6.1) ------------------------------------------------- #
def test_energy_required_is_soc_gap_times_capacity():
    # (50 - 0)/100 * 64 = 32 kWh
    assert energy_required_kwh(make_session(current_soc=0, target_soc=50, battery_capacity_kwh=64)) == pytest.approx(32.0)


def test_energy_required_never_negative_when_already_at_target():
    s = make_session(current_soc=90, target_soc=80)
    assert energy_required_kwh(s) == 0.0


def test_time_until_departure_in_hours():
    assert time_until_departure_hours(make_session(hours_until_departure=3.0), NOW) == pytest.approx(3.0)


def test_urgency_is_energy_over_time():
    # 32 kWh over 8 h -> 4.0 kW
    s = make_session(current_soc=0, target_soc=50, battery_capacity_kwh=64, hours_until_departure=8.0)
    assert compute_urgency(s, NOW) == pytest.approx(4.0)


def test_completed_vehicle_has_zero_urgency():
    assert compute_urgency(make_session(current_soc=80, target_soc=80), NOW) == 0.0


def test_past_deadline_vehicle_has_infinite_urgency():
    s = make_session(current_soc=0, target_soc=50, hours_until_departure=-1.0)
    assert math.isinf(compute_urgency(s, NOW))


# --- Worked example (Book Table 10) ----------------------------------------- #
def test_table10_more_urgent_vehicle_served_first():
    # A: 32 kWh / 8.0 h = 4.0 kW (lower).  B: 24 kWh / 3.0 h = 8.0 kW (higher).
    a = make_session(session_id=1, current_soc=0, target_soc=50, battery_capacity_kwh=64, hours_until_departure=8.0)
    b = make_session(session_id=2, current_soc=0, target_soc=50, battery_capacity_kwh=48, hours_until_departure=3.0)
    # Scarce capacity: only 8 kW available -> all goes to B, A waits.
    allocs = {al.session_id: al for al in allocate([a, b], available_budget_kw=8.0, now=NOW)}
    assert allocs[2].assigned_power_kw == pytest.approx(8.0)
    assert allocs[1].assigned_power_kw == pytest.approx(0.0)
    assert allocs[1].waiting is True


def test_table10_higher_urgency_gets_larger_share_when_scarce():
    a = make_session(session_id=1, current_soc=0, target_soc=50, battery_capacity_kwh=64, hours_until_departure=8.0)
    b = make_session(session_id=2, current_soc=0, target_soc=50, battery_capacity_kwh=48, hours_until_departure=3.0)
    allocs = {al.session_id: al for al in allocate([a, b], available_budget_kw=10.0, now=NOW)}
    # B (urgency 8) takes its 8 kW first; A gets the leftover 2 kW.
    assert allocs[2].assigned_power_kw == pytest.approx(8.0)
    assert allocs[1].assigned_power_kw == pytest.approx(2.0)
    assert allocs[2].assigned_power_kw > allocs[1].assigned_power_kw


# --- Allocation never exceeds what a vehicle needs (Book §4.6.4) ------------ #
def test_allocation_capped_by_required_rate():
    # Needs only 4 kW (32 kWh / 8 h); budget and max are huge -> gets exactly 4 kW.
    s = make_session(current_soc=0, target_soc=50, battery_capacity_kwh=64, hours_until_departure=8.0)
    al = allocate([s], available_budget_kw=1000.0, now=NOW)[0]
    assert al.assigned_power_kw == pytest.approx(4.0)


def test_allocation_capped_by_vehicle_max_rate():
    # Required rate is huge (lots of energy, little time) but vehicle max is 11 kW.
    s = make_session(current_soc=0, target_soc=100, battery_capacity_kwh=100, max_charge_rate_kw=11.0, hours_until_departure=0.5)
    al = allocate([s], available_budget_kw=1000.0, now=NOW)[0]
    assert al.assigned_power_kw == pytest.approx(11.0)


# --- Decision D1: charger power cap is the 4th constraint -------------------- #
def test_allocation_capped_by_charger_max_power():
    # Vehicle can take 11 kW and needs more, budget is huge, but the charger caps at 7.4 kW.
    s = make_session(current_soc=0, target_soc=100, battery_capacity_kwh=100,
                     max_charge_rate_kw=11.0, charger_max_power_kw=7.4, hours_until_departure=0.5)
    al = allocate([s], available_budget_kw=1000.0, now=NOW)[0]
    assert al.assigned_power_kw == pytest.approx(7.4)


# --- Hard power constraint (Book §2.1, §4.6) -------------------------------- #
def test_aggregate_allocation_never_exceeds_budget():
    sessions = [
        make_session(session_id=i, current_soc=0, target_soc=100, battery_capacity_kwh=100,
                     max_charge_rate_kw=22.0, hours_until_departure=1.0)
        for i in range(1, 11)  # 10 hungry vehicles
    ]
    budget = 50.0
    allocs = allocate(sessions, available_budget_kw=budget, now=NOW)
    total = sum(a.assigned_power_kw for a in allocs)
    assert total <= budget + 1e-9


def test_zero_budget_everyone_waits():
    sessions = [make_session(session_id=i, hours_until_departure=2.0) for i in range(1, 4)]
    allocs = allocate(sessions, available_budget_kw=0.0, now=NOW)
    assert all(a.assigned_power_kw == 0.0 for a in allocs)
    assert all(a.waiting for a in allocs)


# --- Budget recompute responds to base-load change (Book §3.9) -------------- #
def test_smaller_budget_throttles_lowest_priority():
    high = make_session(session_id=1, current_soc=0, target_soc=100, battery_capacity_kwh=100,
                        max_charge_rate_kw=22.0, hours_until_departure=1.0)   # very urgent
    low = make_session(session_id=2, current_soc=0, target_soc=100, battery_capacity_kwh=100,
                       max_charge_rate_kw=22.0, hours_until_departure=10.0)   # not urgent
    big = {a.session_id: a for a in allocate([high, low], available_budget_kw=44.0, now=NOW)}
    small = {a.session_id: a for a in allocate([high, low], available_budget_kw=22.0, now=NOW)}
    # When budget shrinks, the urgent vehicle is protected; the low-priority one is throttled.
    assert small[1].assigned_power_kw >= small[2].assigned_power_kw
    assert small[2].assigned_power_kw < big[2].assigned_power_kw


# --- Tie-breaking: equal departure -> larger energy deficit (Book Table 12) -- #
def test_equal_departure_breaks_tie_by_energy_deficit():
    # Same departure (same urgency-time); bigger battery gap should be served first.
    small_gap = make_session(session_id=1, current_soc=40, target_soc=50, battery_capacity_kwh=100, hours_until_departure=2.0)
    big_gap = make_session(session_id=2, current_soc=0, target_soc=50, battery_capacity_kwh=100, hours_until_departure=2.0)
    # Scarce budget that can't serve both fully.
    allocs = {a.session_id: a for a in allocate([small_gap, big_gap], available_budget_kw=20.0, now=NOW)}
    assert allocs[2].assigned_power_kw >= allocs[1].assigned_power_kw


# --- Disconnect mid-charge: capacity redistributes (Book Table 12) ---------- #
def test_disconnect_releases_capacity_to_others():
    a = make_session(session_id=1, current_soc=0, target_soc=100, battery_capacity_kwh=100, max_charge_rate_kw=22.0, hours_until_departure=2.0)
    b = make_session(session_id=2, current_soc=0, target_soc=100, battery_capacity_kwh=100, max_charge_rate_kw=22.0, hours_until_departure=2.0)
    with_both = {al.session_id: al for al in allocate([a, b], available_budget_kw=22.0, now=NOW)}
    without_b = {al.session_id: al for al in allocate([a], available_budget_kw=22.0, now=NOW)}
    # A gets at least as much once B is gone (no idle capacity).
    assert without_b[1].assigned_power_kw >= with_both[1].assigned_power_kw


# --- SoC advancement (implied physics) -------------------------------------- #
def test_advance_soc_adds_energy_over_step():
    s = make_session(current_soc=50.0, battery_capacity_kwh=60.0)
    # 12 kW for 5 minutes = 1 kWh -> 1/60 * 100 = 1.667 % SoC.
    new_soc = advance_soc(s, assigned_power_kw=12.0, minutes=5.0)
    assert new_soc == pytest.approx(50.0 + (1.0 / 60.0) * 100.0)


def test_advance_soc_never_exceeds_100():
    s = make_session(current_soc=99.0, battery_capacity_kwh=10.0)
    new_soc = advance_soc(s, assigned_power_kw=100.0, minutes=30.0)
    assert new_soc == 100.0
