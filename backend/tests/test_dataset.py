"""Tests for the synthetic dataset generator and ingestion (M3 - data layer).

Due to data-privacy constraints, ACN-Data (decision D2) is replaced by a documented
synthetic generator. It produces realistic charging-session and base-load traces stored
as CSV, which the replay engine ingests exactly as it would a real dataset - same
`Arrival` + base-load interface, so a real dataset could be swapped in later.

The generator is deterministic (seeded) so runs are reproducible.
"""

from datetime import datetime, timedelta, timezone

from app.dataset import (
    BaseLoadRecord,
    SessionRecord,
    generate_base_load,
    generate_sessions,
    load_base_load,
    read_base_load_csv,
    read_sessions_csv,
    to_arrivals,
    write_base_load_csv,
    write_sessions_csv,
)
from app.db import InMemoryRepository
from app.simulation import run_simulation

START = datetime(2025, 1, 15, 20, 0, 0, tzinfo=timezone.utc)


# --- Determinism (reproducibility) ----------------------------------------- #
def test_generate_sessions_is_deterministic():
    a = generate_sessions(count=12, seed=7)
    b = generate_sessions(count=12, seed=7)
    assert a == b


def test_different_seed_gives_different_data():
    a = generate_sessions(count=12, seed=1)
    b = generate_sessions(count=12, seed=2)
    assert a != b


# --- Structural validity ---------------------------------------------------- #
def test_generated_sessions_are_well_formed():
    rows = generate_sessions(count=30, seed=3)
    assert len(rows) == 30
    plates = {r.license_plate for r in rows}
    assert len(plates) == 30  # unique plates
    for r in rows:
        assert 0 <= r.start_soc < r.target_soc <= 100
        assert r.battery_capacity_kwh > 0 and r.max_charge_rate_kw > 0
        assert r.departure_offset_min > r.connection_offset_min


def test_generate_base_load_is_nonnegative_and_covers_horizon():
    rows = generate_base_load(horizon_min=600, step_min=5, seed=3)
    assert len(rows) == 600 // 5 + 1
    assert all(r.base_load_kw >= 0 for r in rows)


# --- CSV round-trip --------------------------------------------------------- #
def test_sessions_csv_roundtrip(tmp_path):
    rows = generate_sessions(count=8, seed=5)
    path = tmp_path / "sessions.csv"
    write_sessions_csv(str(path), rows)
    loaded = read_sessions_csv(str(path))
    assert loaded == rows


def test_base_load_csv_roundtrip(tmp_path):
    rows = generate_base_load(horizon_min=120, step_min=5, seed=5)
    path = tmp_path / "base_load.csv"
    write_base_load_csv(str(path), rows)
    loaded = read_base_load_csv(str(path))
    assert loaded == rows


# --- Ingestion into the repository ------------------------------------------ #
def test_to_arrivals_maps_offsets_to_absolute_times():
    rows = [SessionRecord("X-1", 1, 60.0, 11.0, 40.0, 80.0, connection_offset_min=10, departure_offset_min=310)]
    arrivals = to_arrivals(rows, START)
    assert arrivals[0].connection_time == START + timedelta(minutes=10)
    assert arrivals[0].departure_time == START + timedelta(minutes=310)
    assert arrivals[0].license_plate == "X-1"


def test_load_base_load_populates_repo():
    repo = InMemoryRepository()
    repo.seed_building(1, "Demo", 50.0)
    rows = [BaseLoadRecord(0, 8.0), BaseLoadRecord(30, 14.0)]
    load_base_load(repo, 1, rows, START)
    assert repo.get_base_load_at(1, START) == 8.0
    assert repo.get_base_load_at(1, START + timedelta(minutes=45)) == 14.0


# --- End-to-end: hard constraint holds on the generated dataset ------------- #
def test_simulation_over_generated_dataset_respects_limit():
    sessions = generate_sessions(count=20, seed=11)
    base_load = generate_base_load(horizon_min=720, step_min=5, seed=11)

    repo = InMemoryRepository()
    repo.seed_building(1, "Demo Tower", max_building_power_kw=50.0)
    for r in sessions:
        repo.seed_charger(r.charger_id, 1, max_power_output_kw=22.0)
    load_base_load(repo, 1, base_load, START)
    arrivals = to_arrivals(sessions, START)

    end = START + timedelta(hours=14)
    result = run_simulation(repo, 1, START, end, step_minutes=5.0, arrivals=arrivals)

    for snap in result.snapshots:
        assert snap.total_assigned_kw <= snap.available_budget_kw + 1e-9
