# Dataset Selection & Schema Mapping

Resolves **Ambiguity #3** (the project book never names a dataset) and design decision
**D2**. The book validates the system by *trace-driven simulation*
over a historical dataset (Book §2.3, §3.5). We need two kinds of trace:

1. **EV charging sessions** - arrivals, departures (deadlines), energy requested.
2. **Building base load** - the time-varying non-EV consumption (elevators, HVAC,
   lighting) that shrinks the charging budget (Book §4.6.2).

## IMPLEMENTED - synthetic generator (privacy-driven substitution for D2)

Real charging datasets (including ACN-Data) carry personal/location data, and access was
not available for this project for **data-privacy** reasons. We therefore generate a
**deterministic synthetic dataset** that produces both traces, stored as CSV, and replay
it through the scheduler. This is a documented, deliberate deviation from D2 - the book
itself only ever planned to *select* a dataset, and trace-driven simulation over a
synthetic-but-realistic trace is a standard, defensible validation method.

- Generator + ingestion: [`backend/app/dataset.py`](../backend/app/dataset.py)
  (unit-tested in `backend/tests/test_dataset.py`).
- Produce the dataset: `py scripts/generate_dataset.py` → writes `data/sessions.csv`
  and `data/base_load.csv` (git-ignored; regenerated deterministically from a seed).
- Validate end-to-end: `py scripts/run_from_dataset.py` → ingests the CSVs, runs the
  5-minute cycle over the night, prints the Table 15 statistics and the
  managed-vs-uncontrolled peak. A 30-vehicle / 80 kW run yields 100% on-time with the
  load held at/below the ceiling, versus a ~338 kW uncontrolled peak.

### Synthetic CSV schema
`sessions.csv`: `license_plate, charger_id, battery_capacity_kwh, max_charge_rate_kw,
start_soc, target_soc, connection_offset_min, departure_offset_min` (times are minute
offsets from a fixed simulation start, so the trace is portable and reproducible).
`base_load.csv`: `offset_min, base_load_kw` (an evening elevator/HVAC peak decaying
overnight, per Book Table 11).

**The crucial property:** the replay engine ingests these via the same `Arrival` +
base-load interface a *real* dataset would use (`to_arrivals`, `load_base_load`). The
ACN-Data mapping below is therefore still the live "swap in real data later" path - only
the read layer changes, never the scheduler or analysis.

---

## Future real-data path (kept for when access is available)

## Why two sources

We searched for a single public dataset carrying both EV sessions and building-level
base load. None exists in a usable, openly licensed form - EV-charging datasets are
session-centric and omit building load; building-load datasets omit EV sessions. Per
the user's instruction ("prefer a single source; otherwise use two and document"), we
use **two documented sources** and join them on a simulated clock.

## Source 1 - EV charging sessions: ACN-Data (Caltech)

- **What:** the Adaptive Charging Network dataset (Caltech, JPL, Office sites) - tens of
  thousands of *real* EV charging sessions, the de-facto standard for EV-charging
  scheduling research.
- **Access:** public, free API token by email registration; consumable via the
  `acnportal`/`acndata` Python package or the JSON HTTP API.
- **License:** research/non-commercial - appropriate for an academic final project.
- **Why it fits:** it carries exactly what the urgency formula needs - connection time
  (arrival), an estimated departure (deadline), and requested energy.

### ACN-Data → ChargingSession mapping
| Our field (ChargingSession / Vehicle) | ACN-Data source | Notes |
|---|---|---|
| `start_soc` | derived | assume a per-session start SoC (see assumptions) |
| `target_soc` | from `userInputs.requestedDeparture` + `WhPerMile`×`milesRequested` | requested energy → target SoC given battery capacity |
| `departure_time` | `userInputs.requestedDeparture` (fallback `disconnectTime`) | the deadline used by urgency |
| `battery_capacity_kwh` (Vehicle) | assumption | not in ACN-Data; assign per representative EV model |
| `max_charge_rate_kw` (Vehicle) | assumption | typical AC rate (e.g. 7.4 / 11 kW) per model |
| `charger_id` | `spaceID` / `stationID` | maps to a Charger row |
| `charger.max_power_output_kw` | site spec (ACN EVSE) | needed for constraint D1 |
| connection (arrival) | `connectionTime` | when the session enters the active set |
| energy delivered (validation) | `kWhDelivered` | for comparing managed vs. uncontrolled |

**Assumptions documented here** (because ACN-Data omits battery physics): battery
capacity and max charge rate are assigned from a small lookup of representative EV
models; `start_soc` is inferred from requested energy and assumed capacity. These
assumptions live in one place in the ingestion code so they are auditable.

## Source 2 - Building base load: public residential/commercial load profile

- **Primary candidate:** NREL **End-Use Load Profiles (EULP)** / OpenEI commercial
  reference-building hourly profiles - publicly downloadable, openly licensed
  (U.S. Government work / CC0-like), and decomposed into end uses including HVAC,
  lighting, and elevators/plug loads - matching the components in Book Table 11.
- **Fallback:** a household-level smart-meter dataset (e.g. UK-DALE / REFIT) aggregated
  to a building, if a building-level profile proves unwieldy.
- **Processing:** resample to the 5-minute cycle, scale to the simulated building size,
  and load into `BuildingBaseLoad(timestamp, base_load_kw)`.

### Base-load → BuildingBaseLoad mapping
| Our field | Source | Notes |
|---|---|---|
| `timestamp` | profile time index (resampled to 5 min) | aligned to the sim clock |
| `base_load_kw` | sum of non-EV end uses at that timestamp | scaled to building size |
| `building_id` | constant for the simulated building | - |

## Joining the two sources

Both traces are projected onto one **simulated charging night**: the base-load profile
defines `Available_Charging_Power(t) = Building_Limit − Base_Building_Load(t)` at each
5-minute tick, and ACN-Data sessions are admitted as their (offset-aligned) connection
times arrive. The replay engine (`simulation.py`, M3) owns this join; the scheduler
core never sees the dataset - only the abstract data the repository feeds it.

## Reproducibility
Ingestion scripts pin source versions/queries, record the EV-model assumption table,
and write a deterministic seed so Table 14 / Table 15 runs are reproducible.
