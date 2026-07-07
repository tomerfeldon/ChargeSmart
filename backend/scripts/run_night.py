"""Demo: a 30-vehicle simulated charging night (Book §5.3, §5.4, Tables 14-15).

Builds a deterministic 30-vehicle scenario, runs the managed scheduler over the night,
and prints the Table 15 statistics alongside the uncontrolled baseline peak. No external
services - pure in-memory simulation.

Run from backend/:  py scripts/run_night.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analysis import summarize, unmanaged_load_series
from app.db import InMemoryRepository
from app.simulation import Arrival, run_simulation

START = datetime(2025, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
N_VEHICLES = 30
BUILDING_LIMIT_KW = 50.0


def build_scenario() -> tuple[InMemoryRepository, list[Arrival], datetime]:
    repo = InMemoryRepository()
    repo.seed_building(1, "Demo Tower, Tel Aviv", BUILDING_LIMIT_KW)
    for cid in range(1, N_VEHICLES + 1):
        repo.seed_charger(cid, 1, max_power_output_kw=22.0)

    # A base-load trace: 8 kW baseline, with an evening "elevator/HVAC" bump to 15 kW.
    repo.add_base_load(1, START, 8.0)
    repo.add_base_load(1, START + timedelta(hours=1), 15.0)
    repo.add_base_load(1, START + timedelta(hours=2), 8.0)

    arrivals: list[Arrival] = []
    max_departure = START
    for i in range(N_VEHICLES):
        # Deterministic variety (no RNG): an overnight top-up scenario sized to be
        # feasible under the 50 kW limit, mirroring the Book's 30-vehicle run.
        conn_h = (i % 6) * 10 / 60.0                 # arrive over the first hour
        depart_h = 6.0 + (i % 5)                     # leave between +6 h and +10 h
        battery = 40.0 + (i % 4) * 10.0              # 40..70 kWh
        start_soc = 60.0 + (i % 5) * 3.0             # 60..72 % (overnight top-up)
        target_soc = 80.0                            # all want 80 % by departure
        max_rate = 7.4 if i % 3 == 0 else 11.0
        departure = START + timedelta(hours=depart_h)
        max_departure = max(max_departure, departure)
        arrivals.append(Arrival(
            connection_time=START + timedelta(hours=conn_h),
            charger_id=i + 1, license_plate=f"SIM-{i:02d}",
            battery_capacity_kwh=battery, max_charge_rate_kw=max_rate,
            start_soc=start_soc, target_soc=target_soc, departure_time=departure,
        ))
    return repo, arrivals, max_departure


def main() -> None:
    repo, arrivals, max_departure = build_scenario()
    end = max_departure + timedelta(minutes=5)

    result = run_simulation(repo, 1, START, end, step_minutes=5.0, arrivals=arrivals)
    stats = summarize(result)

    unmanaged = unmanaged_load_series(repo, 1, arrivals, START, end, step_minutes=5.0)
    unmanaged_peak = max(load for _, load in unmanaged)

    print("=" * 56)
    print(f" ChargeSmart - {N_VEHICLES}-vehicle simulated night")
    print(f" Building limit: {BUILDING_LIMIT_KW:.0f} kW | steps: {len(result.snapshots)} x 5 min")
    print("=" * 56)
    print(" Table 15 - statistical measures")
    print("-" * 56)
    print(f"  Mean building load .......... {stats.mean_building_load_kw:6.1f} kW")
    print(f"  Peak load ................... {stats.peak_load_kw:6.1f} kW")
    print(f"  Peak utilization ............ {stats.peak_utilization * 100:6.1f} %")
    print(f"  On-time completion rate ..... {stats.on_time_completion_rate * 100:6.1f} %")
    print(f"  Mean waiting time ........... {stats.mean_waiting_minutes:6.1f} min")
    print(f"  Std. dev. of waiting time ... {stats.std_waiting_minutes:6.1f} min")
    print("-" * 56)
    print(" Managed vs. uncontrolled (Book §5.4)")
    print("-" * 56)
    print(f"  Managed peak ................ {stats.peak_load_kw:6.1f} kW  (<= {BUILDING_LIMIT_KW:.0f} kW limit)")
    print(f"  Uncontrolled peak ........... {unmanaged_peak:6.1f} kW  "
          f"({'EXCEEDS' if unmanaged_peak > BUILDING_LIMIT_KW else 'within'} the limit -> would trip)")
    print("=" * 56)


if __name__ == "__main__":
    main()
