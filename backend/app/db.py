"""Repository layer (M2) — the single data-access seam (Book §3.7.3).

`Repository` is the abstract interface every subsystem (scheduler caller, replay
engine, API) reads and writes through. `InMemoryRepository` is the implementation
used for unit tests and for the M3 simulation; a `SupabaseRepository` will implement
the same interface later, so swapping historical replay for live feeds (Book §6.6)
touches only this layer — never the scheduler.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from .entities import (
    Building,
    BuildingBaseLoad,
    Charger,
    ChargerStatus,
    ChargingSession,
    EventType,
    SessionStatus,
    SystemEventLog,
    User,
    UserRole,
    Vehicle,
)


class Repository(ABC):
    """Abstract data-access contract. All reads/writes go through these methods."""

    # --- Users --- #
    @abstractmethod
    def create_user(
        self, building_id: int, email: str, password_hash: str, role: UserRole, full_name: str
    ) -> User: ...
    @abstractmethod
    def get_user(self, user_id: int) -> User | None: ...
    @abstractmethod
    def get_user_by_email(self, email: str) -> User | None: ...

    # --- Building --- #
    @abstractmethod
    def get_building(self, building_id: int) -> Building: ...
    @abstractmethod
    def update_building_limit(self, building_id: int, max_building_power_kw: float) -> Building: ...

    # --- Chargers --- #
    @abstractmethod
    def list_chargers(self, building_id: int) -> list[Charger]: ...
    @abstractmethod
    def get_charger(self, charger_id: int) -> Charger: ...
    @abstractmethod
    def update_charger_status(self, charger_id: int, status: ChargerStatus) -> Charger: ...

    # --- Vehicles --- #
    @abstractmethod
    def get_or_create_vehicle(
        self, user_id: int, license_plate: str, battery_capacity_kwh: float, max_charge_rate_kw: float
    ) -> Vehicle: ...
    @abstractmethod
    def get_vehicle(self, vehicle_id: int) -> Vehicle: ...

    # --- Charging sessions --- #
    @abstractmethod
    def create_session(
        self, vehicle_id: int, charger_id: int, start_soc: float, current_soc: float,
        target_soc: float, departure_time: datetime,
    ) -> ChargingSession: ...
    @abstractmethod
    def get_session(self, session_id: int) -> ChargingSession: ...
    @abstractmethod
    def update_session(self, session_id: int, **fields) -> ChargingSession: ...
    @abstractmethod
    def list_active_sessions(self, building_id: int) -> list[ChargingSession]: ...

    # --- Base load --- #
    @abstractmethod
    def add_base_load(self, building_id: int, timestamp: datetime, base_load_kw: float) -> BuildingBaseLoad: ...
    @abstractmethod
    def get_base_load_at(self, building_id: int, timestamp: datetime) -> float: ...

    # --- Event log --- #
    @abstractmethod
    def add_event(
        self, building_id: int, charger_id: int | None, timestamp: datetime,
        event_type: EventType, description: str,
    ) -> SystemEventLog: ...
    @abstractmethod
    def list_events(self, building_id: int, limit: int = 100) -> list[SystemEventLog]: ...


class InMemoryRepository(Repository):
    """Dictionary-backed repository for tests and simulation.

    `charger_id` is recorded on each session so a session can be joined to its
    charger's `max_power_output_kw` (the 4th allocation constraint, decision D1).
    """

    def __init__(self) -> None:
        self._buildings: dict[int, Building] = {}
        self._users: dict[int, User] = {}
        self._email_index: dict[str, int] = {}
        self._chargers: dict[int, Charger] = {}
        self._vehicles: dict[int, Vehicle] = {}
        self._plate_index: dict[str, int] = {}
        self._sessions: dict[int, ChargingSession] = {}
        self._base_load: list[BuildingBaseLoad] = []
        self._events: list[SystemEventLog] = []
        self._next_id = {"user": 1, "vehicle": 1, "session": 1, "base_load": 1, "event": 1}

    def _alloc_id(self, kind: str) -> int:
        value = self._next_id[kind]
        self._next_id[kind] = value + 1
        return value

    # --- Seed helpers (test/sim fixtures; not part of the abstract interface) --- #
    def seed_building(self, building_id: int, address: str, max_building_power_kw: float) -> Building:
        b = Building(building_id, address, max_building_power_kw)
        self._buildings[building_id] = b
        return b

    def seed_charger(self, charger_id: int, building_id: int, max_power_output_kw: float,
                     status: ChargerStatus = ChargerStatus.ONLINE) -> Charger:
        c = Charger(charger_id, building_id, max_power_output_kw, status)
        self._chargers[charger_id] = c
        return c

    # --- Users --- #
    def create_user(self, building_id, email, password_hash, role, full_name) -> User:
        user_id = self._alloc_id("user")
        u = User(user_id, building_id, email, password_hash, role, full_name)
        self._users[user_id] = u
        self._email_index[email] = user_id
        return u

    def get_user(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    def get_user_by_email(self, email: str) -> User | None:
        uid = self._email_index.get(email)
        return self._users.get(uid) if uid is not None else None

    # --- Building --- #
    def get_building(self, building_id: int) -> Building:
        return self._buildings[building_id]

    def update_building_limit(self, building_id: int, max_building_power_kw: float) -> Building:
        b = self._buildings[building_id]
        b.max_building_power_kw = max_building_power_kw
        return b

    # --- Chargers --- #
    def list_chargers(self, building_id: int) -> list[Charger]:
        return [c for c in self._chargers.values() if c.building_id == building_id]

    def get_charger(self, charger_id: int) -> Charger:
        return self._chargers[charger_id]

    def update_charger_status(self, charger_id: int, status: ChargerStatus) -> Charger:
        c = self._chargers[charger_id]
        c.status = status
        return c

    # --- Vehicles --- #
    def get_or_create_vehicle(self, user_id, license_plate, battery_capacity_kwh, max_charge_rate_kw) -> Vehicle:
        if license_plate in self._plate_index:
            return self._vehicles[self._plate_index[license_plate]]
        vehicle_id = self._alloc_id("vehicle")
        v = Vehicle(vehicle_id, user_id, license_plate, battery_capacity_kwh, max_charge_rate_kw)
        self._vehicles[vehicle_id] = v
        self._plate_index[license_plate] = vehicle_id
        return v

    def get_vehicle(self, vehicle_id: int) -> Vehicle:
        return self._vehicles[vehicle_id]

    # --- Charging sessions --- #
    def create_session(self, vehicle_id, charger_id, start_soc, current_soc, target_soc, departure_time) -> ChargingSession:
        session_id = self._alloc_id("session")
        s = ChargingSession(
            session_id=session_id, vehicle_id=vehicle_id, charger_id=charger_id,
            start_soc=start_soc, current_soc=current_soc, target_soc=target_soc,
            departure_time=departure_time, assigned_power_kw=0.0, status=SessionStatus.WAITING,
        )
        self._sessions[session_id] = s
        return s

    def get_session(self, session_id: int) -> ChargingSession:
        return self._sessions[session_id]

    def update_session(self, session_id: int, **fields) -> ChargingSession:
        s = self._sessions[session_id]
        for key, value in fields.items():
            if not hasattr(s, key):
                raise AttributeError(f"ChargingSession has no field '{key}'")
            setattr(s, key, value)
        return s

    def list_active_sessions(self, building_id: int) -> list[ChargingSession]:
        """Active = connected (not completed/canceled) and not yet at target SoC (Book §3.5)."""
        chargers_here = {c.charger_id for c in self.list_chargers(building_id)}
        return [
            s for s in self._sessions.values()
            if s.charger_id in chargers_here
            and s.status not in (SessionStatus.COMPLETED, SessionStatus.CANCELED)
            and s.current_soc < s.target_soc
        ]

    # --- Base load --- #
    def add_base_load(self, building_id, timestamp, base_load_kw) -> BuildingBaseLoad:
        point = BuildingBaseLoad(self._alloc_id("base_load"), building_id, timestamp, base_load_kw)
        self._base_load.append(point)
        return point

    def get_base_load_at(self, building_id: int, timestamp: datetime) -> float:
        """Step-function lookup: the most recent point at or before `timestamp`, else 0.0."""
        candidates = [
            p for p in self._base_load
            if p.building_id == building_id and p.timestamp <= timestamp
        ]
        if not candidates:
            return 0.0
        return max(candidates, key=lambda p: p.timestamp).base_load_kw

    # --- Event log --- #
    def add_event(self, building_id, charger_id, timestamp, event_type, description) -> SystemEventLog:
        e = SystemEventLog(self._alloc_id("event"), building_id, charger_id, timestamp, event_type, description)
        self._events.append(e)
        return e

    def list_events(self, building_id: int, limit: int = 100) -> list[SystemEventLog]:
        events = [e for e in self._events if e.building_id == building_id]
        events.sort(key=lambda e: e.timestamp, reverse=True)  # newest first
        return events[:limit]
