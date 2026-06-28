"""Unit tests for the repository layer (M2), against the in-memory implementation.

The repository (Book §3.7.3) is the single seam through which the scheduler, the
replay engine, and the API read and write shared data. Building an in-memory
implementation first lets M3's simulation run immediately; the Supabase-backed
implementation drops in later behind the same interface.

Written test-first: these tests define the data-access contract.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.entities import ChargingSession, SessionStatus, ChargerStatus, EventType
from app.db import InMemoryRepository

NOW = datetime(2025, 1, 15, 22, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo() -> InMemoryRepository:
    # A seeded building with two chargers and a base-load trace.
    r = InMemoryRepository()
    r.seed_building(building_id=1, address="1 Rothschild Blvd", max_building_power_kw=50.0)
    r.seed_charger(charger_id=1, building_id=1, max_power_output_kw=22.0)
    r.seed_charger(charger_id=2, building_id=1, max_power_output_kw=11.0)
    r.add_base_load(building_id=1, timestamp=NOW, base_load_kw=8.0)
    r.add_base_load(building_id=1, timestamp=NOW + timedelta(minutes=30), base_load_kw=15.0)
    return r


def _new_session(repo, charger_id=1, current_soc=40.0, target_soc=80.0, hours=5.0, plate="12-345-67"):
    vehicle = repo.get_or_create_vehicle(
        user_id=1, license_plate=plate, battery_capacity_kwh=60.0, max_charge_rate_kw=11.0
    )
    return repo.create_session(
        vehicle_id=vehicle.vehicle_id,
        charger_id=charger_id,
        start_soc=current_soc,
        current_soc=current_soc,
        target_soc=target_soc,
        departure_time=NOW + timedelta(hours=hours),
    )


# --- Building ---------------------------------------------------------------- #
def test_get_building_returns_configured_limit(repo):
    assert repo.get_building(1).max_building_power_kw == 50.0


def test_update_building_limit(repo):
    updated = repo.update_building_limit(1, 75.0)
    assert updated.max_building_power_kw == 75.0
    assert repo.get_building(1).max_building_power_kw == 75.0


# --- Chargers ---------------------------------------------------------------- #
def test_list_chargers_for_building(repo):
    chargers = repo.list_chargers(1)
    assert {c.charger_id for c in chargers} == {1, 2}


def test_update_charger_status(repo):
    repo.update_charger_status(2, ChargerStatus.FAULTED)
    faulted = [c for c in repo.list_chargers(1) if c.status == ChargerStatus.FAULTED]
    assert [c.charger_id for c in faulted] == [2]


# --- Vehicles ---------------------------------------------------------------- #
def test_get_or_create_vehicle_is_idempotent_by_plate(repo):
    v1 = repo.get_or_create_vehicle(user_id=1, license_plate="AAA", battery_capacity_kwh=60.0, max_charge_rate_kw=11.0)
    v2 = repo.get_or_create_vehicle(user_id=1, license_plate="AAA", battery_capacity_kwh=60.0, max_charge_rate_kw=11.0)
    assert v1.vehicle_id == v2.vehicle_id


# --- Sessions: the "active" predicate (Book §3.5) --------------------------- #
def test_created_session_is_active(repo):
    s = _new_session(repo)
    active_ids = [a.session_id for a in repo.list_active_sessions(1)]
    assert s.session_id in active_ids


def test_session_at_target_is_not_active(repo):
    s = _new_session(repo, current_soc=80.0, target_soc=80.0)
    active_ids = [a.session_id for a in repo.list_active_sessions(1)]
    assert s.session_id not in active_ids


def test_canceled_session_is_not_active(repo):
    s = _new_session(repo)
    repo.update_session(s.session_id, status=SessionStatus.CANCELED)
    active_ids = [a.session_id for a in repo.list_active_sessions(1)]
    assert s.session_id not in active_ids


def test_update_session_changes_fields(repo):
    s = _new_session(repo)
    repo.update_session(s.session_id, current_soc=55.0, assigned_power_kw=7.4)
    reloaded = repo.get_session(s.session_id)
    assert reloaded.current_soc == 55.0
    assert reloaded.assigned_power_kw == 7.4


# --- Base load: step-function lookup over the trace (Book §4.6.2) ----------- #
def test_base_load_returns_value_at_exact_timestamp(repo):
    assert repo.get_base_load_at(1, NOW) == 8.0


def test_base_load_uses_most_recent_point_at_or_before(repo):
    # 10 minutes after NOW, the trace still reads the NOW point (8.0) until the 30-min point.
    assert repo.get_base_load_at(1, NOW + timedelta(minutes=10)) == 8.0
    assert repo.get_base_load_at(1, NOW + timedelta(minutes=45)) == 15.0


def test_base_load_defaults_to_zero_before_first_point(repo):
    assert repo.get_base_load_at(1, NOW - timedelta(hours=1)) == 0.0


# --- Event log (Book §3.2 SystemEventLog) ----------------------------------- #
def test_add_and_list_events_newest_first(repo):
    repo.add_event(building_id=1, charger_id=None, timestamp=NOW, event_type=EventType.REOPTIMIZATION, description="recompute")
    repo.add_event(building_id=1, charger_id=2, timestamp=NOW + timedelta(minutes=1), event_type=EventType.CHARGER_FAULT, description="fault")
    events = repo.list_events(1, limit=10)
    assert len(events) == 2
    assert events[0].event_type == EventType.CHARGER_FAULT  # newest first
