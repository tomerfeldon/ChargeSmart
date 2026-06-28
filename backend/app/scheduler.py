"""ChargeSmart scheduling core (M1) — pure, isolated, independently testable.

This module is the heart of the system (Book §4.3, §4.6). It has no dependency on
FastAPI, PostgreSQL, or the network: it takes plain dataclasses plus the current time
and returns power allocations. That isolation is what lets it be unit-tested in full
and reused for offline analysis (Book §5.1).

Algorithm (Book §4.6.1, §3.5): greedy, urgency-based.
  urgency = energy_required / time_until_departure        # the minimum rate to make the deadline
Vehicles are sorted by descending urgency and served greedily; each is assigned

  min(vehicle max charge rate, required rate, remaining budget, charger max power)

where the charger-max term is decision D1. The remaining-budget term makes the
building power limit a HARD constraint: once the budget is exhausted, later vehicles
receive 0 kW and wait (Book §2.1, §4.6.4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VehicleSession:
    """Everything the scheduler needs about one active vehicle for one cycle.

    Static vehicle physics (`battery_capacity_kwh`, `max_charge_rate_kw`) and the
    charger cap (`charger_max_power_kw`) are folded in by the caller (the repository /
    replay engine), so the core itself stays free of the data model.
    """

    session_id: int
    current_soc: float          # %
    target_soc: float           # %
    battery_capacity_kwh: float
    max_charge_rate_kw: float
    charger_max_power_kw: float  # decision D1: physical cap of the charging point
    departure_time: datetime


@dataclass(frozen=True)
class Allocation:
    session_id: int
    assigned_power_kw: float
    urgency_kw: float
    waiting: bool


def energy_required_kwh(session: VehicleSession) -> float:
    """Energy still needed to reach target SoC (Book §4.6.1). Never negative."""
    gap = (session.target_soc - session.current_soc) / 100.0
    return max(0.0, gap * session.battery_capacity_kwh)


def time_until_departure_hours(session: VehicleSession, now: datetime) -> float:
    """Hours from `now` until the vehicle's departure (Book §4.6.1)."""
    return (session.departure_time - now).total_seconds() / 3600.0


def compute_urgency(session: VehicleSession, now: datetime) -> float:
    """urgency = energy_required / time_until_departure  [kW]  (Book §4.6.1).

    Boundary behaviour:
      - no energy needed -> 0 (vehicle is done, yields all capacity)
      - deadline reached or passed -> +inf (must be served at maximum, first)
    """
    energy = energy_required_kwh(session)
    if energy <= 0.0:
        return 0.0
    hours = time_until_departure_hours(session, now)
    if hours <= 0.0:
        return math.inf
    return energy / hours


def allocate(
    sessions: list[VehicleSession],
    available_budget_kw: float,
    now: datetime,
) -> list[Allocation]:
    """Greedy urgency-based allocation under the hard power constraint.

    Returns allocations in descending-priority order. The sum of assigned power never
    exceeds `available_budget_kw` (the building limit minus base load).
    """
    # Rank by descending urgency; tie-break by larger energy deficit, then session_id
    # for full determinism (Book Table 12).
    def sort_key(s: VehicleSession):
        return (-compute_urgency(s, now), -energy_required_kwh(s), s.session_id)

    remaining = max(0.0, available_budget_kw)
    allocations: list[Allocation] = []

    for s in sorted(sessions, key=sort_key):
        urgency = compute_urgency(s, now)
        required_rate = urgency  # urgency IS the minimum rate needed (Book §4.6.1)
        # When past deadline, urgency is +inf; the required-rate term must not cap the
        # allocation, so treat it as "as much as possible".
        cap_terms = [s.max_charge_rate_kw, s.charger_max_power_kw, remaining]
        if math.isfinite(required_rate):
            cap_terms.append(required_rate)
        assigned = max(0.0, min(cap_terms))

        waiting = assigned <= 0.0 and energy_required_kwh(s) > 0.0
        allocations.append(
            Allocation(
                session_id=s.session_id,
                assigned_power_kw=assigned,
                urgency_kw=urgency,
                waiting=waiting,
            )
        )
        remaining -= assigned

    return allocations


def advance_soc(session: VehicleSession, assigned_power_kw: float, minutes: float) -> float:
    """New SoC after charging at `assigned_power_kw` for `minutes` (implied physics).

    energy_added = power * (minutes/60);  delta_soc = energy_added / capacity * 100.
    Capped at 100% (physical battery limit).
    """
    energy_added_kwh = assigned_power_kw * (minutes / 60.0)
    delta_soc = energy_added_kwh / session.battery_capacity_kwh * 100.0
    return min(100.0, session.current_soc + delta_soc)
