"""Statistical analysis of a simulated charging night (M7) — Book §5.4 / Table 15.

Pure functions over a `SimulationResult`: no DB, no network (the `unmanaged_load_series`
baseline reads charger caps from the repository read-only). These are the measures that
characterise system behaviour beyond "deadlines met", plus the managed-vs-uncontrolled
comparison that visually demonstrates the safety and peak-shaving benefit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from .db import Repository
from .simulation import Arrival, SimulationResult


@dataclass(frozen=True)
class NightStatistics:
    """The Table 15 measures for one simulated night."""

    vehicle_count: int
    mean_building_load_kw: float       # avg aggregate (base + charging) across steps
    peak_load_kw: float                # max aggregate load
    peak_utilization: float            # peak_load / building_limit (<= 1.0 when safe)
    on_time_completion_rate: float     # share of vehicles meeting their deadline
    mean_waiting_minutes: float        # avg time a vehicle spends queued
    std_waiting_minutes: float         # dispersion of waiting times


def _aggregate_loads(result: SimulationResult) -> list[float]:
    """Aggregate building load (base load + EV charging) at each step."""
    return [s.base_load_kw + s.total_assigned_kw for s in result.snapshots]


def _waiting_minutes_per_vehicle(result: SimulationResult) -> dict[int, float]:
    minutes: dict[int, float] = {sid: 0.0 for sid in result.session_ids}
    for snap in result.snapshots:
        for alloc in snap.allocations:
            if alloc.waiting:
                minutes[alloc.session_id] = minutes.get(alloc.session_id, 0.0) + result.step_minutes
    return minutes


def summarize(result: SimulationResult) -> NightStatistics:
    loads = _aggregate_loads(result)
    mean_load = sum(loads) / len(loads) if loads else 0.0
    peak_load = max(loads) if loads else 0.0
    limit = result.building_limit_kw

    n = len(result.session_ids)
    on_time = sum(
        1 for sid in result.session_ids
        if sid in result.completions and result.completions[sid] <= result.deadlines[sid]
    )
    on_time_rate = on_time / n if n else 0.0

    waits = list(_waiting_minutes_per_vehicle(result).values())
    mean_wait = sum(waits) / len(waits) if waits else 0.0
    variance = sum((w - mean_wait) ** 2 for w in waits) / len(waits) if waits else 0.0

    return NightStatistics(
        vehicle_count=n,
        mean_building_load_kw=mean_load,
        peak_load_kw=peak_load,
        peak_utilization=(peak_load / limit) if limit > 0 else 0.0,
        on_time_completion_rate=on_time_rate,
        mean_waiting_minutes=mean_wait,
        std_waiting_minutes=math.sqrt(variance),
    )


def unmanaged_load_series(
    repo: Repository,
    building_id: int,
    arrivals: list[Arrival],
    start: datetime,
    end: datetime,
    step_minutes: float = 5.0,
) -> list[tuple[datetime, float]]:
    """The uncontrolled baseline: every vehicle charges at full rate on arrival.

    Each vehicle draws ``min(max_charge_rate, charger_max_power)`` continuously from its
    connection time until it has delivered its required energy — with no regard to the
    building limit. This is the profile that would trip protection (Book §5.4); plotting
    it against the managed profile shows both the safety guarantee and the peak shaving.
    """
    # Precompute each vehicle's full rate and charging duration.
    profiles = []
    for a in arrivals:
        charger_cap = repo.get_charger(a.charger_id).max_power_output_kw
        full_rate = min(a.max_charge_rate_kw, charger_cap)
        energy_needed = max(0.0, (a.target_soc - a.start_soc) / 100.0 * a.battery_capacity_kwh)
        duration_h = (energy_needed / full_rate) if full_rate > 0 else 0.0
        profiles.append((a.connection_time, a.connection_time + timedelta(hours=duration_h), full_rate))

    series: list[tuple[datetime, float]] = []
    now = start
    dt = timedelta(minutes=step_minutes)
    while now <= end:
        load = sum(rate for conn, done, rate in profiles if conn <= now < done)
        series.append((now, load))
        now += dt
    return series
