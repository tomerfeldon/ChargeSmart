"""Replay / simulation engine (M3) — the fixed 5-minute scheduling cycle.

Drives trace-driven replay over the repository (Book §2.3, §3.5, §4.6.5). On each tick
it: (1) admits vehicles that have connected since the last cycle, (2) reads the building
base load, (3) computes the charging budget, (4) ranks and allocates via the pure
scheduler, (5) advances each vehicle's SoC and marks completions, (6) records a snapshot.

The engine talks only to the abstract `Repository`, so the same code runs over synthetic
traces (tests today) and the real ACN-Data dataset (once ingested) — and, later, over
live feeds (Book §6.6) without touching the scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .db import Repository
from .entities import ChargerStatus, ChargingSession, EventType, SessionStatus
from .scheduler import Allocation, VehicleSession, advance_soc, allocate

# A vehicle is "done" once within this SoC tolerance of target (floating-point slack).
_SOC_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Arrival:
    """A vehicle connecting at a known time during the replay (Book §3.3.1)."""

    connection_time: datetime
    charger_id: int
    license_plate: str
    battery_capacity_kwh: float
    max_charge_rate_kw: float
    start_soc: float
    target_soc: float
    departure_time: datetime
    user_id: int = 1


@dataclass(frozen=True)
class StepSnapshot:
    """The state pushed to the dashboard at one tick."""

    timestamp: datetime
    base_load_kw: float
    available_budget_kw: float
    total_assigned_kw: float
    active_count: int
    allocations: list[Allocation]


@dataclass(frozen=True)
class SimulationResult:
    building_id: int
    building_limit_kw: float
    snapshots: list[StepSnapshot]
    step_minutes: float = 5.0
    # Per-session bookkeeping for the statistical analysis (M7).
    session_ids: frozenset[int] = frozenset()
    deadlines: dict[int, datetime] = field(default_factory=dict)
    completions: dict[int, datetime] = field(default_factory=dict)  # first time SoC >= target


def to_vehicle_session(repo: Repository, session: ChargingSession) -> VehicleSession:
    """Join a stored session to its vehicle physics and charger cap (decision D1).

    A charger that is not ONLINE contributes a cap of 0 kW, so its vehicle receives no
    power and waits — the faulted-charger edge case of Book Table 12.
    """
    vehicle = repo.get_vehicle(session.vehicle_id)
    charger = repo.get_charger(session.charger_id)
    charger_cap = charger.max_power_output_kw if charger.status == ChargerStatus.ONLINE else 0.0
    return VehicleSession(
        session_id=session.session_id,
        current_soc=session.current_soc,
        target_soc=session.target_soc,
        battery_capacity_kwh=vehicle.battery_capacity_kwh,
        max_charge_rate_kw=vehicle.max_charge_rate_kw,
        charger_max_power_kw=charger_cap,
        departure_time=session.departure_time,
    )


def step(repo: Repository, building_id: int, now: datetime, step_minutes: float = 5.0) -> StepSnapshot:
    """Execute one scheduling cycle and persist the results."""
    base_load = repo.get_base_load_at(building_id, now)
    limit = repo.get_building(building_id).max_building_power_kw
    budget = max(0.0, limit - base_load)

    active = repo.list_active_sessions(building_id)
    vsessions = {s.session_id: to_vehicle_session(repo, s) for s in active}
    allocations = allocate(list(vsessions.values()), budget, now)
    by_id = {a.session_id: a for a in allocations}

    total_assigned = 0.0
    for session in active:
        alloc = by_id[session.session_id]
        new_soc = advance_soc(vsessions[session.session_id], alloc.assigned_power_kw, step_minutes)

        if new_soc >= session.target_soc - _SOC_TOLERANCE:
            status = SessionStatus.COMPLETED
        elif alloc.assigned_power_kw > 0.0:
            status = SessionStatus.CHARGING
        else:
            status = SessionStatus.WAITING

        repo.update_session(
            session.session_id,
            current_soc=new_soc,
            assigned_power_kw=alloc.assigned_power_kw,
            status=status,
        )
        total_assigned += alloc.assigned_power_kw

    return StepSnapshot(
        timestamp=now,
        base_load_kw=base_load,
        available_budget_kw=budget,
        total_assigned_kw=total_assigned,
        active_count=len(active),
        allocations=allocations,
    )


def recompute(repo: Repository, building_id: int, now: datetime) -> StepSnapshot:
    """Re-solve allocations for the current active set WITHOUT advancing SoC.

    This is the event-driven recompute (decision D3): triggered by a vehicle
    connecting, a departure/parameter edit, or a limit change. Unlike ``step`` it does
    not advance the simulated clock — it only re-distributes power under the current
    budget and persists each session's ``assigned_power_kw`` and waiting/charging state.
    """
    base_load = repo.get_base_load_at(building_id, now)
    limit = repo.get_building(building_id).max_building_power_kw
    budget = max(0.0, limit - base_load)

    active = repo.list_active_sessions(building_id)
    vsessions = [to_vehicle_session(repo, s) for s in active]
    allocations = allocate(vsessions, budget, now)
    by_id = {a.session_id: a for a in allocations}

    total_assigned = 0.0
    for session in active:
        alloc = by_id[session.session_id]
        status = SessionStatus.CHARGING if alloc.assigned_power_kw > 0.0 else SessionStatus.WAITING
        repo.update_session(session.session_id, assigned_power_kw=alloc.assigned_power_kw, status=status)
        total_assigned += alloc.assigned_power_kw

    return StepSnapshot(
        timestamp=now,
        base_load_kw=base_load,
        available_budget_kw=budget,
        total_assigned_kw=total_assigned,
        active_count=len(active),
        allocations=allocations,
    )


def _admit_arrivals(repo, building_id, arrivals, admitted, now) -> None:
    """Create sessions for vehicles whose connection time has arrived (Book §4.6.5)."""
    for index, a in enumerate(arrivals):
        if index in admitted or a.connection_time > now:
            continue
        vehicle = repo.get_or_create_vehicle(
            a.user_id, a.license_plate, a.battery_capacity_kwh, a.max_charge_rate_kw
        )
        repo.create_session(
            vehicle_id=vehicle.vehicle_id, charger_id=a.charger_id,
            start_soc=a.start_soc, current_soc=a.start_soc,
            target_soc=a.target_soc, departure_time=a.departure_time,
        )
        repo.add_event(building_id, a.charger_id, now, EventType.SESSION_STARTED,
                       f"Vehicle {a.license_plate} connected on charger {a.charger_id}.")
        admitted.add(index)


def run_simulation(
    repo: Repository,
    building_id: int,
    start: datetime,
    end: datetime,
    step_minutes: float = 5.0,
    arrivals: list[Arrival] | None = None,
) -> SimulationResult:
    """Replay the 5-minute cycle from `start` to `end` (inclusive)."""
    arrivals = list(arrivals or [])
    admitted: set[int] = set()
    snapshots: list[StepSnapshot] = []
    session_ids: set[int] = set()
    deadlines: dict[int, datetime] = {}
    completions: dict[int, datetime] = {}

    now = start
    dt = timedelta(minutes=step_minutes)
    while now <= end:
        _admit_arrivals(repo, building_id, arrivals, admitted, now)
        # Record the vehicles in play this cycle and their deadlines.
        for s in repo.list_active_sessions(building_id):
            session_ids.add(s.session_id)
            deadlines[s.session_id] = s.departure_time

        snapshots.append(step(repo, building_id, now, step_minutes))

        # Record the first time each vehicle reaches its target (it then leaves active).
        for sid in session_ids:
            if sid not in completions and repo.get_session(sid).status == SessionStatus.COMPLETED:
                completions[sid] = now
        now += dt

    return SimulationResult(
        building_id=building_id,
        building_limit_kw=repo.get_building(building_id).max_building_power_kw,
        snapshots=snapshots,
        step_minutes=step_minutes,
        session_ids=frozenset(session_ids),
        deadlines=deadlines,
        completions=completions,
    )
