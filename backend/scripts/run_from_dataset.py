"""Replay the synthetic dataset through the scheduler and report the statistics.

Run from backend/:
    py scripts/generate_dataset.py     # once, to create data/*.csv
    py scripts/run_from_dataset.py     # ingest + simulate + report

This is the end-to-end trace-driven validation (Book §2.3, §5.3, §5.4): it reads the
dataset from CSV, ingests it through the repository, runs the 5-minute cycle over the
whole night, and prints the Table 15 statistics plus the managed-vs-uncontrolled peak.
Nothing is hand-built in code - the scenario comes entirely from the files on disk.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analysis import summarize, unmanaged_load_series
from app.dataset import load_base_load, read_base_load_csv, read_sessions_csv, to_arrivals
from app.db import InMemoryRepository
from app.simulation import run_simulation

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

START = datetime(2025, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
# A realistically-sized ceiling for a 30-charger building: enough headroom for the
# overnight demand to be feasible, while still far below the uncontrolled peak.
BUILDING_LIMIT_KW = 80.0


def main() -> None:
    sessions_path = os.path.join(DATA_DIR, "sessions.csv")
    base_load_path = os.path.join(DATA_DIR, "base_load.csv")
    if not (os.path.exists(sessions_path) and os.path.exists(base_load_path)):
        print("Dataset not found. Run:  py scripts/generate_dataset.py")
        raise SystemExit(1)

    sessions = read_sessions_csv(sessions_path)
    base_load = read_base_load_csv(base_load_path)

    # Build the building, one charger per vehicle, and ingest the dataset.
    repo = InMemoryRepository()
    repo.seed_building(1, "Demo Tower, Tel Aviv", max_building_power_kw=BUILDING_LIMIT_KW)
    for r in sessions:
        repo.seed_charger(r.charger_id, 1, max_power_output_kw=r.max_charge_rate_kw)
    load_base_load(repo, 1, base_load, START)
    arrivals = to_arrivals(sessions, START)

    end = START + timedelta(minutes=max(r.departure_offset_min for r in sessions) + 5)
    result = run_simulation(repo, 1, START, end, step_minutes=5.0, arrivals=arrivals)
    stats = summarize(result)

    unmanaged = unmanaged_load_series(repo, 1, arrivals, START, end, step_minutes=5.0)
    unmanaged_peak = max(load for _, load in unmanaged)

    print("=" * 60)
    print(f" ChargeSmart - trace-driven run over data/  ({len(sessions)} vehicles)")
    print(f" Building limit: {BUILDING_LIMIT_KW:.0f} kW | steps: {len(result.snapshots)} x 5 min")
    print("=" * 60)
    print(" Table 15 - statistical measures")
    print("-" * 60)
    print(f"  Mean building load .......... {stats.mean_building_load_kw:6.1f} kW")
    print(f"  Peak load ................... {stats.peak_load_kw:6.1f} kW")
    print(f"  Peak utilization ............ {stats.peak_utilization * 100:6.1f} %")
    print(f"  On-time completion rate ..... {stats.on_time_completion_rate * 100:6.1f} %")
    print(f"  Mean waiting time ........... {stats.mean_waiting_minutes:6.1f} min")
    print(f"  Std. dev. of waiting time ... {stats.std_waiting_minutes:6.1f} min")
    print("-" * 60)
    print(" Managed vs. uncontrolled (Book 5.4)")
    print("-" * 60)
    print(f"  Managed peak ................ {stats.peak_load_kw:6.1f} kW  (<= {BUILDING_LIMIT_KW:.0f} kW limit)")
    verdict = "EXCEEDS -> would trip" if unmanaged_peak > BUILDING_LIMIT_KW else "within limit"
    print(f"  Uncontrolled peak ........... {unmanaged_peak:6.1f} kW  ({verdict})")
    print("=" * 60)


if __name__ == "__main__":
    main()
