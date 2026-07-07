"""Application state (M4): the live, seeded in-memory store.

This is the running backend's data tier for now - a seeded `InMemoryRepository` with
one building, its chargers, and one user per role. It implements the `Repository`
interface, so a `SupabaseRepository` will replace it later with no change to the
service layer or the endpoints.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .db import InMemoryRepository, Repository
from .entities import ChargerStatus, UserRole
from .security import hash_password

# Load backend/.env (DATABASE_URL, ANTHROPIC_API_KEY, ...) if present.
load_dotenv()

DEFAULT_BUILDING_ID = 1

_repo: Repository | None = None


def build_seeded_repo() -> InMemoryRepository:
    repo = InMemoryRepository()
    repo.seed_building(DEFAULT_BUILDING_ID, "1 Rothschild Blvd, Tel Aviv", max_building_power_kw=50.0)
    repo.seed_charger(1, DEFAULT_BUILDING_ID, max_power_output_kw=22.0)
    repo.seed_charger(2, DEFAULT_BUILDING_ID, max_power_output_kw=11.0)
    repo.seed_charger(3, DEFAULT_BUILDING_ID, max_power_output_kw=22.0, status=ChargerStatus.FAULTED)

    # One demo user per role. Passwords are dev defaults - change for any real deployment.
    repo.create_user(DEFAULT_BUILDING_ID, "resident@chargesmart.test", hash_password("resident123"), UserRole.RESIDENT, "Dana Resident")
    repo.create_user(DEFAULT_BUILDING_ID, "manager@chargesmart.test", hash_password("manager123"), UserRole.MANAGER, "Moshe Manager")
    repo.create_user(DEFAULT_BUILDING_ID, "tech@chargesmart.test", hash_password("tech123"), UserRole.TECHNICIAN, "Tomer Tech")
    return repo


def get_repo() -> Repository:
    """Return the live repository.

    If DATABASE_URL is set, use the Supabase/PostgreSQL store (seeded once via
    scripts/seed_supabase.py); otherwise fall back to a freshly seeded in-memory store.
    """
    global _repo
    if _repo is None:
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            from .repository_pg import SupabaseRepository

            _repo = SupabaseRepository(database_url)
        else:
            _repo = build_seeded_repo()
    return _repo


def reset_state() -> None:
    """Rebuild the store from scratch (used by tests for isolation)."""
    global _repo
    _repo = build_seeded_repo()
