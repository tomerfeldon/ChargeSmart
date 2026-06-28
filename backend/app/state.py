"""Application state (M4): the live, seeded in-memory store.

This is the running backend's data tier for now — a seeded `InMemoryRepository` with
one building, its chargers, and one user per role. It implements the `Repository`
interface, so a `SupabaseRepository` will replace it later with no change to the
service layer or the endpoints.
"""

from __future__ import annotations

from .db import InMemoryRepository
from .entities import ChargerStatus, UserRole
from .security import hash_password

DEFAULT_BUILDING_ID = 1

_repo: InMemoryRepository | None = None


def build_seeded_repo() -> InMemoryRepository:
    repo = InMemoryRepository()
    repo.seed_building(DEFAULT_BUILDING_ID, "1 Rothschild Blvd, Tel Aviv", max_building_power_kw=50.0)
    repo.seed_charger(1, DEFAULT_BUILDING_ID, max_power_output_kw=22.0)
    repo.seed_charger(2, DEFAULT_BUILDING_ID, max_power_output_kw=11.0)
    repo.seed_charger(3, DEFAULT_BUILDING_ID, max_power_output_kw=22.0, status=ChargerStatus.FAULTED)

    # One demo user per role. Passwords are dev defaults — change for any real deployment.
    repo.create_user(DEFAULT_BUILDING_ID, "resident@chargesmart.test", hash_password("resident123"), UserRole.RESIDENT, "Dana Resident")
    repo.create_user(DEFAULT_BUILDING_ID, "manager@chargesmart.test", hash_password("manager123"), UserRole.MANAGER, "Moshe Manager")
    repo.create_user(DEFAULT_BUILDING_ID, "tech@chargesmart.test", hash_password("tech123"), UserRole.TECHNICIAN, "Tomer Tech")
    return repo


def get_repo() -> InMemoryRepository:
    global _repo
    if _repo is None:
        _repo = build_seeded_repo()
    return _repo


def reset_state() -> None:
    """Rebuild the store from scratch (used by tests for isolation)."""
    global _repo
    _repo = build_seeded_repo()
