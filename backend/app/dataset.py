"""Synthetic dataset generator + ingestion (M3 - data layer).

Due to data-privacy constraints, the planned ACN-Data source (decision D2 in PLAN.md)
is replaced by a documented synthetic generator. It produces realistic charging-session
and base-load traces, stored as CSV ("the dataset"), which the replay engine ingests
through the same `Arrival` + base-load interface a real dataset would use. So the
algorithm and analysis are unchanged; only this read layer differs from a real-data setup.

Everything is seeded for reproducibility (no wall-clock or unseeded randomness), so a
given (count, seed) always yields the same dataset - exactly what reproducible Table 14 /
Table 15 results require.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from .db import Repository
from .simulation import Arrival


@dataclass(frozen=True)
class SessionRecord:
    """One synthetic charging session, with times as minute-offsets from a start instant."""

    license_plate: str
    charger_id: int
    battery_capacity_kwh: float
    max_charge_rate_kw: float
    start_soc: float
    target_soc: float
    connection_offset_min: int
    departure_offset_min: int


@dataclass(frozen=True)
class BaseLoadRecord:
    offset_min: int
    base_load_kw: float


# Representative EV models (capacity kWh, max AC/DC rate kW) - auditable assumptions.
_EV_MODELS = [(40.0, 7.4), (52.0, 11.0), (60.0, 11.0), (75.0, 11.0), (85.0, 22.0)]


def generate_sessions(count: int, seed: int = 42) -> list[SessionRecord]:
    """Generate `count` overnight top-up sessions. Deterministic for a given seed.

    Vehicles connect over the first ~2 hours and leave 5-10 hours later. SoC gaps are
    modest (overnight top-ups), so a well-sized building can satisfy most deadlines -
    mirroring the Book's feasible 30-vehicle scenario while staying varied.
    """
    rng = random.Random(seed)
    rows: list[SessionRecord] = []
    for i in range(count):
        battery, max_rate = rng.choice(_EV_MODELS)
        start_soc = float(rng.randint(45, 72))
        target_soc = float(rng.choice([80, 80, 90, 100]))
        if target_soc <= start_soc:
            target_soc = min(100.0, start_soc + 10.0)
        connection = rng.randrange(0, 121, 5)             # arrive within the first 2 h
        depart = connection + rng.choice([5, 6, 7, 8, 9, 10]) * 60  # leave 5-10 h later
        rows.append(
            SessionRecord(
                license_plate=f"SIM-{i:03d}",
                charger_id=i + 1,                          # one charger per vehicle
                battery_capacity_kwh=battery,
                max_charge_rate_kw=max_rate,
                start_soc=start_soc,
                target_soc=target_soc,
                connection_offset_min=connection,
                departure_offset_min=depart,
            )
        )
    return rows


def generate_base_load(horizon_min: int = 720, step_min: int = 5, seed: int = 42) -> list[BaseLoadRecord]:
    """Generate a base-load trace (Book §4.6.2): an evening peak that decays overnight.

    Shape: ~8 kW baseline, an elevator/HVAC evening bump toward ~15 kW in the first
    ~90 minutes, decaying to ~5 kW late at night, with small seeded jitter.
    """
    rng = random.Random(seed + 1000)
    rows: list[BaseLoadRecord] = []
    for offset in range(0, horizon_min + 1, step_min):
        hours = offset / 60.0
        if hours < 1.5:
            level = 8.0 + (15.0 - 8.0) * (1.0 - abs(hours - 0.75) / 0.75)  # peak at 45 min
        elif hours < 5.0:
            level = 8.0
        else:
            level = max(5.0, 8.0 - (hours - 5.0) * 0.4)                    # decay late
        level += rng.uniform(-0.6, 0.6)
        rows.append(BaseLoadRecord(offset, round(max(0.0, level), 2)))
    return rows


# --- CSV persistence -------------------------------------------------------- #
_SESSION_FIELDS = [
    "license_plate", "charger_id", "battery_capacity_kwh", "max_charge_rate_kw",
    "start_soc", "target_soc", "connection_offset_min", "departure_offset_min",
]


def write_sessions_csv(path: str, rows: list[SessionRecord]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_SESSION_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r.__dict__)


def read_sessions_csv(path: str) -> list[SessionRecord]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            SessionRecord(
                license_plate=row["license_plate"],
                charger_id=int(row["charger_id"]),
                battery_capacity_kwh=float(row["battery_capacity_kwh"]),
                max_charge_rate_kw=float(row["max_charge_rate_kw"]),
                start_soc=float(row["start_soc"]),
                target_soc=float(row["target_soc"]),
                connection_offset_min=int(row["connection_offset_min"]),
                departure_offset_min=int(row["departure_offset_min"]),
            )
            for row in csv.DictReader(f)
        ]


def write_base_load_csv(path: str, rows: list[BaseLoadRecord]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["offset_min", "base_load_kw"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r.__dict__)


def read_base_load_csv(path: str) -> list[BaseLoadRecord]:
    with open(path, newline="", encoding="utf-8") as f:
        return [BaseLoadRecord(int(row["offset_min"]), float(row["base_load_kw"])) for row in csv.DictReader(f)]


# --- Ingestion into the repository / simulation ----------------------------- #
def to_arrivals(rows: list[SessionRecord], start: datetime) -> list[Arrival]:
    """Convert session records to replay-engine arrivals at absolute times."""
    return [
        Arrival(
            connection_time=start + timedelta(minutes=r.connection_offset_min),
            charger_id=r.charger_id,
            license_plate=r.license_plate,
            battery_capacity_kwh=r.battery_capacity_kwh,
            max_charge_rate_kw=r.max_charge_rate_kw,
            start_soc=r.start_soc,
            target_soc=r.target_soc,
            departure_time=start + timedelta(minutes=r.departure_offset_min),
        )
        for r in rows
    ]


def load_base_load(repo: Repository, building_id: int, rows: list[BaseLoadRecord], start: datetime) -> None:
    """Load the base-load trace into the repository at absolute timestamps."""
    for r in rows:
        repo.add_base_load(building_id, start + timedelta(minutes=r.offset_min), r.base_load_kw)
