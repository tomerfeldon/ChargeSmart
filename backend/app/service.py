"""Application service layer (M4): maps HTTP requests to repository + scheduler calls.

The endpoints stay thin; this module owns the orchestration — create/update a session,
trigger a recompute (decision D3), and assemble the API response models. Every mutation
re-solves the allocation so the schedule the caller sees reflects the change.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import simulation
from .db import Repository
from .entities import ChargingSession, EventType
from .schemas import (
    BuildingRead,
    ChargerRead,
    DiagnosticsResponse,
    EventLogRead,
    ScheduleResponse,
    SessionCreate,
    SessionRead,
    SessionUpdate,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _projected_completion(repo: Repository, session: ChargingSession, now: datetime) -> datetime | None:
    """When the session reaches target at its current assigned rate (None if idle)."""
    if session.assigned_power_kw <= 0.0:
        return None
    vehicle = repo.get_vehicle(session.vehicle_id)
    energy_needed = max(0.0, (session.target_soc - session.current_soc) / 100.0 * vehicle.battery_capacity_kwh)
    if energy_needed <= 0.0:
        return now
    hours = energy_needed / session.assigned_power_kw
    return now + timedelta(hours=hours)


def _to_session_read(repo: Repository, session: ChargingSession, now: datetime) -> SessionRead:
    return SessionRead(
        session_id=session.session_id,
        vehicle_id=session.vehicle_id,
        charger_id=session.charger_id,
        start_soc=session.start_soc,
        current_soc=session.current_soc,
        target_soc=session.target_soc,
        departure_time=session.departure_time,
        assigned_power_kw=session.assigned_power_kw,
        status=session.status,
        projected_completion_time=_projected_completion(repo, session, now),
    )


def register_session(repo: Repository, user, payload: SessionCreate) -> SessionRead:
    vehicle = repo.get_or_create_vehicle(
        user_id=user.user_id,
        license_plate=payload.license_plate,
        battery_capacity_kwh=payload.battery_capacity_kwh,
        max_charge_rate_kw=payload.max_charge_rate_kw,
    )
    session = repo.create_session(
        vehicle_id=vehicle.vehicle_id, charger_id=payload.charger_id,
        start_soc=payload.current_soc, current_soc=payload.current_soc,
        target_soc=payload.target_soc, departure_time=payload.departure_time,
    )
    now = _now()
    repo.add_event(user.building_id, payload.charger_id, now, EventType.SESSION_STARTED,
                   f"Vehicle {payload.license_plate} connected on charger {payload.charger_id}.")
    simulation.recompute(repo, user.building_id, now)  # decision D3
    return _to_session_read(repo, repo.get_session(session.session_id), now)


def update_session(repo: Repository, user, session_id: int, payload: SessionUpdate) -> SessionRead:
    fields = payload.model_dump(exclude_none=True)
    repo.update_session(session_id, **fields)
    now = _now()
    repo.add_event(user.building_id, None, now, EventType.REOPTIMIZATION,
                   f"Session {session_id} updated; schedule recomputed.")
    simulation.recompute(repo, user.building_id, now)  # decision D3
    return _to_session_read(repo, repo.get_session(session_id), now)


def get_schedule(repo: Repository, building_id: int) -> ScheduleResponse:
    now = _now()
    snapshot = simulation.recompute(repo, building_id, now)
    sessions = repo.list_active_sessions(building_id)
    return ScheduleResponse(
        building_limit_kw=repo.get_building(building_id).max_building_power_kw,
        base_load_kw=snapshot.base_load_kw,
        available_budget_kw=snapshot.available_budget_kw,
        total_assigned_kw=snapshot.total_assigned_kw,
        as_of=now,
        sessions=[_to_session_read(repo, s, now) for s in sessions],
    )


def set_building_limit(repo: Repository, building_id: int, max_building_power_kw: float) -> BuildingRead:
    building = repo.update_building_limit(building_id, max_building_power_kw)
    now = _now()
    repo.add_event(building_id, None, now, EventType.LIMIT_CHANGED,
                   f"Building power limit set to {max_building_power_kw} kW.")
    simulation.recompute(repo, building_id, now)  # decision D3
    return BuildingRead(
        building_id=building.building_id,
        address=building.address,
        max_building_power_kw=building.max_building_power_kw,
    )


def get_diagnostics(repo: Repository, building_id: int) -> DiagnosticsResponse:
    return DiagnosticsResponse(
        chargers=[
            ChargerRead(charger_id=c.charger_id, building_id=c.building_id,
                        max_power_output_kw=c.max_power_output_kw, status=c.status)
            for c in repo.list_chargers(building_id)
        ],
        event_log=[
            EventLogRead(event_id=e.event_id, building_id=e.building_id, charger_id=e.charger_id,
                         timestamp=e.timestamp, event_type=e.event_type, description=e.description)
            for e in repo.list_events(building_id, limit=100)
        ],
    )
