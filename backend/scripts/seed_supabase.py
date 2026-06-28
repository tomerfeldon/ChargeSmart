"""Seed the Supabase/PostgreSQL database with the building, chargers, and demo users.

Run ONCE after creating the tables (db/migrations/001_initial_schema.sql), from backend/:
    py scripts/seed_supabase.py

Reads DATABASE_URL from backend/.env. Idempotent — re-running updates the seed rows
rather than duplicating them. Also serves as a connection smoke-test.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from app.entities import ChargerStatus, UserRole
from app.security import hash_password

load_dotenv()

DEMO_USERS = [
    ("resident@chargesmart.test", "resident123", UserRole.RESIDENT, "Dana Resident"),
    ("manager@chargesmart.test", "manager123", UserRole.MANAGER, "Moshe Manager"),
    ("tech@chargesmart.test", "tech123", UserRole.TECHNICIAN, "Tomer Tech"),
]


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set. Create backend/.env with your Supabase connection string.")
        raise SystemExit(1)

    from app.repository_pg import SupabaseRepository  # imported here so unit tests never load psycopg

    print("Connecting to the database...")
    repo = SupabaseRepository(database_url)
    print("Connected.")

    repo.seed_building(1, "1 Rothschild Blvd, Tel Aviv", max_building_power_kw=50.0)
    repo.seed_charger(1, 1, max_power_output_kw=22.0)
    repo.seed_charger(2, 1, max_power_output_kw=11.0)
    repo.seed_charger(3, 1, max_power_output_kw=22.0, status=ChargerStatus.FAULTED)
    for email, password, role, name in DEMO_USERS:
        repo.create_user(1, email, hash_password(password), role, name)

    building = repo.get_building(1)
    chargers = repo.list_chargers(1)
    print(f"Seeded building '{building.address}' (limit {building.max_building_power_kw:.0f} kW)")
    print(f"Seeded {len(chargers)} chargers and {len(DEMO_USERS)} demo users.")
    print("Done. You can now run the API against Supabase: py -m uvicorn app.main:app --reload")
    repo.close()


if __name__ == "__main__":
    main()
