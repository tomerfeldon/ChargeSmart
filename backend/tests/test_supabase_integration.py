"""Integration tests for SupabaseRepository against a live database (M2 live wiring).

These run ONLY when DATABASE_URL is configured (in backend/.env or the environment) AND
the database has been seeded via scripts/seed_supabase.py. Without it, they skip - so the
default test run stays at 69 fast, hermetic unit tests.

The test creates a throwaway vehicle/session and leaves it canceled, so it doesn't
pollute the active schedule.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; Supabase integration tests skipped"
)


@pytest.fixture
def repo():
    from app.repository_pg import SupabaseRepository

    r = SupabaseRepository(DATABASE_URL)
    yield r
    r.close()


def test_seeded_building_and_chargers_present(repo):
    # Requires scripts/seed_supabase.py to have run.
    assert repo.get_building(1).max_building_power_kw > 0
    assert len(repo.list_chargers(1)) >= 1


def test_login_user_seeded(repo):
    assert repo.get_user_by_email("manager@chargesmart.test") is not None


def test_session_lifecycle_round_trip(repo):
    from app.entities import SessionStatus

    vehicle = repo.get_or_create_vehicle(1, "IT-TEST-1", battery_capacity_kwh=60.0, max_charge_rate_kw=11.0)
    session = repo.create_session(
        vehicle.vehicle_id, charger_id=1, start_soc=40.0, current_soc=40.0, target_soc=80.0,
        departure_time=datetime.now(timezone.utc) + timedelta(hours=5),
    )
    try:
        active_ids = [s.session_id for s in repo.list_active_sessions(1)]
        assert session.session_id in active_ids

        repo.update_session(session.session_id, current_soc=55.0, assigned_power_kw=7.4, status=SessionStatus.CHARGING)
        reloaded = repo.get_session(session.session_id)
        assert reloaded.current_soc == 55.0
        assert reloaded.assigned_power_kw == 7.4
    finally:
        # Leave it canceled so it drops out of the active schedule.
        from app.entities import SessionStatus as S
        repo.update_session(session.session_id, status=S.CANCELED)


def test_base_load_step_lookup(repo):
    now = datetime.now(timezone.utc)
    repo.add_base_load(1, now, 9.0)
    assert repo.get_base_load_at(1, now + timedelta(minutes=1)) == 9.0
