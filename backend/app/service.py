"""Application service layer (M4): maps HTTP requests to repository + scheduler calls.

The endpoints stay thin; this module owns the orchestration - create/update a session,
trigger a recompute (decision D3), and assemble the API response models. Every mutation
re-solves the allocation so the schedule the caller sees reflects the change.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import analysis, dataset, simulation
from .db import InMemoryRepository, Repository
from .entities import ChargingSession, EventType
from .schemas import (
    AnalysisPoint,
    AnalysisResponse,
    AnalysisStats,
    BuildingRead,
    ChargerRead,
    DiagnosticsResponse,
    EventLogRead,
    ScheduleResponse,
    SessionCreate,
    SessionRead,
    SessionUpdate,
)

# The fixed evaluation scenario (Book §5.3, §5.4): a 30-vehicle overnight benchmark at a
# realistically-sized ceiling, reproducible (seeded, not wall-clock). This mirrors the
# Book's feasible Table 15 run, independent of the live (manager-configurable) limit.
_ANALYSIS_START = datetime(2025, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
_ANALYSIS_VEHICLES = 30
_ANALYSIS_SEED = 42
_ANALYSIS_LIMIT_KW = 80.0


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
    """Read the current schedule - fast and READ-ONLY.

    Allocations are (re)computed on events (session create/update via decision D3, and
    limit changes), so a GET is just a snapshot of the stored state. Recomputing (and
    writing) on every poll would hammer the single DB connection and stall the server.
    """
    now = _now()
    building = repo.get_building(building_id)
    base_load = repo.get_base_load_at(building_id, now)
    budget = max(0.0, building.max_building_power_kw - base_load)
    sessions = repo.list_active_sessions(building_id)
    total_assigned = sum(s.assigned_power_kw for s in sessions)
    return ScheduleResponse(
        building_limit_kw=building.max_building_power_kw,
        base_load_kw=base_load,
        available_budget_kw=budget,
        total_assigned_kw=total_assigned,
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


def build_analysis(repo: Repository, building_id: int) -> AnalysisResponse:
    """Trace-driven evaluation report (Book §5.4, Table 15).

    Runs the deterministic overnight benchmark over the synthetic dataset in a throwaway
    in-memory repo (so it never touches the live store) at a fixed, realistically-sized
    ceiling. Returns the Table 15 statistics and the managed-vs-uncontrolled load curves.
    """
    limit_kw = _ANALYSIS_LIMIT_KW

    sessions = dataset.generate_sessions(count=_ANALYSIS_VEHICLES, seed=_ANALYSIS_SEED)
    base_load = dataset.generate_base_load(horizon_min=14 * 60, step_min=5, seed=_ANALYSIS_SEED)

    sandbox = InMemoryRepository()
    sandbox.seed_building(1, "analysis", max_building_power_kw=limit_kw)
    for r in sessions:
        sandbox.seed_charger(r.charger_id, 1, max_power_output_kw=r.max_charge_rate_kw)
    dataset.load_base_load(sandbox, 1, base_load, _ANALYSIS_START)
    arrivals = dataset.to_arrivals(sessions, _ANALYSIS_START)

    end = _ANALYSIS_START + timedelta(minutes=max(r.departure_offset_min for r in sessions) + 5)
    result = simulation.run_simulation(sandbox, 1, _ANALYSIS_START, end, step_minutes=5.0, arrivals=arrivals)
    stats = analysis.summarize(result)
    unmanaged = analysis.unmanaged_load_series(sandbox, 1, arrivals, _ANALYSIS_START, end, step_minutes=5.0)

    # Align the two curves on the shared 5-minute grid.
    series = [
        AnalysisPoint(
            t=snap.timestamp.strftime("%H:%M"),
            managed=round(snap.base_load_kw + snap.total_assigned_kw, 2),
            unmanaged=round(unmanaged[i][1], 2),
        )
        for i, snap in enumerate(result.snapshots)
    ]

    return AnalysisResponse(
        building_limit_kw=limit_kw,
        unmanaged_peak_kw=max(load for _, load in unmanaged),
        stats=AnalysisStats(
            vehicle_count=stats.vehicle_count,
            mean_building_load_kw=round(stats.mean_building_load_kw, 2),
            peak_load_kw=round(stats.peak_load_kw, 2),
            peak_utilization=round(stats.peak_utilization, 4),
            on_time_completion_rate=round(stats.on_time_completion_rate, 4),
            mean_waiting_minutes=round(stats.mean_waiting_minutes, 1),
            std_waiting_minutes=round(stats.std_waiting_minutes, 1),
        ),
        series=series,
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
