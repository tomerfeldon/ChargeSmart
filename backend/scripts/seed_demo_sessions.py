"""Inject an impressive live demo scenario into Supabase (for presentations).

Creates 8 active charging sessions with deliberately varied urgency, so the manager
dashboard shows the scheduler doing real work: the most urgent vehicles charge at high
power, mid-urgency ones are throttled, and the least urgent wait — all while the building
runs exactly at its limit, safely. Idempotent: clears prior sessions/base-load first.

Run from backend/:  py scripts/seed_demo_sessions.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from app import simulation
from app.entities import ChargerStatus

load_dotenv()

# (plate, charger_id, battery_kwh, max_rate_kw, start_soc, target_soc, hours_until_departure)
DEMO_VEHICLES = [
    ("DEMO-02", 2, 75.0, 11.0, 20.0, 80.0, 3.0),   # very urgent  -> full power
    ("DEMO-07", 8, 60.0, 11.0, 25.0, 80.0, 2.5),   # very urgent  -> full power
    ("DEMO-05", 6, 85.0, 22.0, 40.0, 100.0, 5.0),  # urgent       -> high power
    ("DEMO-03", 4, 40.0, 22.0, 50.0, 90.0, 2.0),   # urgent       -> high power
    ("DEMO-01", 1, 60.0, 11.0, 30.0, 80.0, 4.0),   # moderate     -> medium power
    ("DEMO-08", 9, 52.0, 11.0, 55.0, 80.0, 3.0),   # moderate     -> throttled
    ("DEMO-04", 5, 60.0, 11.0, 60.0, 80.0, 6.0),   # relaxed      -> waits
    ("DEMO-06", 7, 50.0, 7.4, 70.0, 90.0, 8.0),    # very relaxed -> waits
]

BUILDING_LIMIT_KW = 60.0
BASE_LOAD_KW = 8.0


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set (backend/.env).")
        raise SystemExit(1)

    from app.repository_pg import SupabaseRepository

    repo = SupabaseRepository(database_url)
    print("Connected. Resetting demo state...")
    repo._conn.execute("DELETE FROM charging_sessions")
    repo._conn.execute("DELETE FROM building_base_load WHERE building_id = 1")

    # A roomier, realistic ceiling + a base load so the gauge shows both components.
    repo.update_building_limit(1, BUILDING_LIMIT_KW)
    now = datetime.now(timezone.utc)
    repo.add_base_load(1, now - timedelta(minutes=5), BASE_LOAD_KW)

    # Ensure enough online chargers (keep charger 3 FAULTED for the diagnostics view).
    for cid in (4, 5, 6, 7, 8, 9):
        repo.seed_charger(cid, 1, max_power_output_kw=22.0, status=ChargerStatus.ONLINE)

    for plate, charger_id, battery, max_rate, start_soc, target_soc, hours in DEMO_VEHICLES:
        vehicle = repo.get_or_create_vehicle(1, plate, battery_capacity_kwh=battery, max_charge_rate_kw=max_rate)
        repo.create_session(
            vehicle_id=vehicle.vehicle_id, charger_id=charger_id,
            start_soc=start_soc, current_soc=start_soc, target_soc=target_soc,
            departure_time=now + timedelta(hours=hours),
        )

    # Run the scheduler once so allocations + statuses are set, just like a live event.
    snapshot = simulation.recompute(repo, 1, now)

    active = repo.list_active_sessions(1)
    charging = sum(1 for s in active if s.assigned_power_kw > 0)
    waiting = sum(1 for s in active if s.assigned_power_kw == 0)
    print(f"Seeded {len(active)} live sessions: {charging} charging, {waiting} waiting.")
    print(f"Building limit {BUILDING_LIMIT_KW:.0f} kW | base load {BASE_LOAD_KW:.0f} kW | "
          f"EV charging {snapshot.total_assigned_kw:.1f} kW | "
          f"utilization {((snapshot.total_assigned_kw + BASE_LOAD_KW) / BUILDING_LIMIT_KW) * 100:.0f}%")
    print("Refresh the manager dashboard to see them live.")
    repo.close()


if __name__ == "__main__":
    main()
