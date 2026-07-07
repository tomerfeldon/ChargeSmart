"""Domain entities (M2) - the seven ERD entities of Book §3.2.

These are the in-memory domain objects the repository stores and the rest of the
backend manipulates. They are mutable dataclasses because the repository updates
fields in place (e.g. a session's `current_soc` and `assigned_power_kw` each cycle).

The enums live here (the domain layer) and are re-exported by `app.schemas` so the
API contract and the data model share one definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    RESIDENT = "resident"
    MANAGER = "manager"
    TECHNICIAN = "technician"


class ChargerStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    FAULTED = "faulted"


class SessionStatus(str, Enum):
    WAITING = "waiting"
    CHARGING = "charging"
    COMPLETED = "completed"
    CANCELED = "canceled"


class EventType(str, Enum):
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"
    REOPTIMIZATION = "reoptimization"
    CHARGER_FAULT = "charger_fault"
    DISCONNECT = "disconnect"
    LIMIT_CHANGED = "limit_changed"
    FEASIBILITY_WARNING = "feasibility_warning"


@dataclass
class Building:
    building_id: int
    address: str
    max_building_power_kw: float


@dataclass
class User:
    user_id: int
    building_id: int
    email: str
    password_hash: str
    role: UserRole
    full_name: str


@dataclass
class Charger:
    charger_id: int
    building_id: int
    max_power_output_kw: float
    status: ChargerStatus = ChargerStatus.ONLINE


@dataclass
class Vehicle:
    vehicle_id: int
    user_id: int
    license_plate: str
    battery_capacity_kwh: float
    max_charge_rate_kw: float


@dataclass
class ChargingSession:
    session_id: int
    vehicle_id: int
    charger_id: int
    start_soc: float
    current_soc: float
    target_soc: float
    departure_time: datetime
    assigned_power_kw: float = 0.0
    status: SessionStatus = SessionStatus.WAITING


@dataclass
class BuildingBaseLoad:
    load_id: int
    building_id: int
    timestamp: datetime
    base_load_kw: float


@dataclass
class SystemEventLog:
    event_id: int
    building_id: int
    charger_id: int | None
    timestamp: datetime
    event_type: EventType
    description: str
