"""ChargeSmart API contract (M0).

This module is the *frozen contract* between the React frontend and the FastAPI
backend (Book §4.2). Frontend and backend are developed in parallel against these
models: the mock server (``app.main``) returns them today; the real endpoints (M4)
will return the identical shapes, so the frontend never has to change.

Naming mirrors the seven ERD entities (Book §3.2) exactly, so the contract and the
data model stay in lockstep.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# Enums are defined once in the domain layer (entities) and re-exported here so the
# API contract and the data model share a single source of truth.
from .entities import ChargerStatus, EventType, SessionStatus, UserRole

__all__ = [
    "ChargerStatus", "EventType", "SessionStatus", "UserRole",
    "BuildingRead", "ChargerRead", "SessionRead", "BaseLoadPoint", "EventLogRead",
    "SessionCreate", "SessionUpdate", "ScheduleResponse", "BuildingLimitUpdate",
    "DiagnosticsResponse", "AssistantQuery", "AssistantResponse",
    "LoginRequest", "TokenResponse",
]


# --------------------------------------------------------------------------- #
# POST /auth/login  — authenticate and receive a JWT (Book §4.5 Login screen)
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: "UserRole"


# --------------------------------------------------------------------------- #
# Entity read models (what the API returns)
# --------------------------------------------------------------------------- #
class BuildingRead(BaseModel):
    building_id: int
    address: str
    max_building_power_kw: float = Field(gt=0, description="Hard power ceiling for the building.")


class ChargerRead(BaseModel):
    charger_id: int
    building_id: int
    max_power_output_kw: float = Field(
        gt=0,
        description="Physical cap of this charging point. Used as the 4th allocation "
        "constraint in the scheduler (decision D1).",
    )
    status: ChargerStatus


class SessionRead(BaseModel):
    """A charging session — the dynamic entity the scheduler operates on (Book §3.2)."""

    session_id: int
    vehicle_id: int
    charger_id: int
    start_soc: float = Field(ge=0, le=100, description="SoC % at connection time.")
    current_soc: float = Field(ge=0, le=100, description="Live SoC %.")
    target_soc: float = Field(ge=0, le=100, description="SoC % the resident wants by departure.")
    departure_time: datetime
    assigned_power_kw: float = Field(ge=0, description="Power granted this cycle by the scheduler.")
    status: SessionStatus
    # Derived, returned for convenience (not stored): projected time to reach target_soc.
    projected_completion_time: datetime | None = Field(
        default=None,
        description="Estimated time the session reaches target_soc at the current rate; "
        "null if not charging or already complete.",
    )


class BaseLoadPoint(BaseModel):
    timestamp: datetime
    base_load_kw: float = Field(ge=0)


class EventLogRead(BaseModel):
    event_id: int
    building_id: int
    charger_id: int | None = None
    timestamp: datetime
    event_type: EventType
    description: str


# --------------------------------------------------------------------------- #
# POST /sessions  — register a charging session (UC-1)
# --------------------------------------------------------------------------- #
class SessionCreate(BaseModel):
    """Resident-supplied parameters when connecting a vehicle (Book §3.3.1).

    Carries both the static vehicle physics (battery capacity, max charge rate) and
    the per-event session values (SoCs, departure). The backend resolves/creates the
    Vehicle row and the ChargingSession row from this payload.
    """

    charger_id: int
    license_plate: str = Field(description="Identifies the vehicle; created if unknown.")
    battery_capacity_kwh: float = Field(gt=0)
    max_charge_rate_kw: float = Field(gt=0, description="Vehicle's own max AC/DC charge rate.")
    current_soc: float = Field(ge=0, le=100)
    target_soc: float = Field(ge=0, le=100)
    departure_time: datetime


# --------------------------------------------------------------------------- #
# PATCH /sessions/{id}  — update departure / parameters (UC-2)
# --------------------------------------------------------------------------- #
class SessionUpdate(BaseModel):
    """All fields optional — only the supplied ones change; triggers a recompute (D3)."""

    departure_time: datetime | None = None
    target_soc: float | None = Field(default=None, ge=0, le=100)
    current_soc: float | None = Field(default=None, ge=0, le=100)
    status: SessionStatus | None = None


# --------------------------------------------------------------------------- #
# GET /schedule  — current allocations across the building
# --------------------------------------------------------------------------- #
class ScheduleResponse(BaseModel):
    building_limit_kw: float
    base_load_kw: float = Field(description="Instantaneous non-EV load (Book §4.6.2).")
    available_budget_kw: float = Field(description="building_limit - base_load (clamped >= 0).")
    total_assigned_kw: float = Field(description="Sum of assigned power; never exceeds budget.")
    as_of: datetime
    sessions: list[SessionRead]


# --------------------------------------------------------------------------- #
# PUT /building/limit  — manager sets the power budget (UC-3)
# --------------------------------------------------------------------------- #
class BuildingLimitUpdate(BaseModel):
    max_building_power_kw: float = Field(gt=0)


# --------------------------------------------------------------------------- #
# GET /diagnostics  — technician view (UC-5)
# --------------------------------------------------------------------------- #
class DiagnosticsResponse(BaseModel):
    chargers: list[ChargerRead]
    event_log: list[EventLogRead]


# --------------------------------------------------------------------------- #
# POST /assistant  — read-only natural-language query (Book §4.6.6)
# --------------------------------------------------------------------------- #
class AssistantQuery(BaseModel):
    query: str = Field(min_length=1, description="Natural-language question about live state.")


class AssistantResponse(BaseModel):
    answer: str
    # The assistant is read-only; it never returns commands that mutate the schedule.
