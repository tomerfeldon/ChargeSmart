# ChargeSmart — Development Plan

> Smart EV Charging Management System for Residential Buildings.
> Single source of truth: **ChargeSmart_Project_Book_v5_EN.docx** (English is authoritative).
> Status: **Approved** — implementation in progress.

## Guiding principles

1. **API contract first.** The OpenAPI/Pydantic contract is frozen in M0 so that
   frontend and backend develop in parallel against a mock.
2. **Scheduling core is a pure, isolated Python module** (`scheduler.py`) — no FastAPI,
   no DB. It is the only component fully unit-testable in isolation (Book §4.3).
3. **Repository pattern** (`db.py`) is the single data-access seam — this is what lets
   historical replay be swapped for live feeds later without touching the algorithm.
4. **Hard power constraint** enforced every cycle: a vehicle can only be assigned what
   is left of the budget; once exhausted, further vehicles get 0 kW (Book §2.1, §4.6).
5. Out-of-scope items (OCPP, live smart meters) are deferred explicitly — never stubbed
   into the core.

## Approved design decisions

- **D1 — Charger power cap (resolves Ambiguity #1):** allocation is bounded by a
  **fourth** term: `min(vehicle.max_charge_rate_kw, required_rate, remaining_budget,
  charger.max_power_output_kw)`. This aligns the code with the ERD field
  `Charger.max_power_output_kw`, which is physically real.
- **D2 — Dataset (resolves Ambiguity #3):** use **two documented public sources** —
  **ACN-Data** (Caltech Adaptive Charging Network) for EV charging sessions, and a
  **public building load profile** for the base load. No single public source carries
  both. Full rationale and schema mapping in [docs/DATASET.md](docs/DATASET.md).
- **D3 — Recompute triggers (resolves Ambiguity #4):** both the 5-minute tick
  (new-vehicle detection, Book §4.6.5) and event-driven changes (PATCH departure /
  PUT limit, UC-2/UC-3) call the **same** `recompute()` entry point.
- **D4 — AI assistant is in scope** (Book §4.6.6) as a read-only Claude layer; the
  Anthropic API key is supplied via a secured environment variable.

## Dependency graph

```
M0 (API contract + scaffold)
        ├──────────────┬───────────────────────────┐
        ▼              ▼                             ▼
M1 scheduler.py   M2 db.py + schema          M5 Frontend (vs. mock)
 (pure, isolated)  (repository)               React+TS + Recharts
        └──────┬───────┘                            │
               ▼                                     │
        M3 simulation.py + dataset                   │
               ▼                                     │
        M4 FastAPI endpoints  ◄──────────────────────┘ (mock → real)
               ▼
        M6 assistant.py (Claude, read-only)
               ▼
        M7 analysis.py + acceptance + statistical report
```

Sprint mapping (Book §3.8): **Sprint 1** = M0+M1+M2+M3 · **Sprint 2** = M4+M5 ·
**Sprint 3** = M6+M7.

## Milestones

### M0 — Scaffold & API contract *(contract first)*
- Monorepo: `backend/` (FastAPI), `frontend/` (React+TS+Vite), `db/` (migrations).
- Pydantic models for the 6 endpoints (Book §4.2):
  `POST /sessions`, `PATCH /sessions/{id}`, `GET /schedule`, `PUT /building/limit`,
  `GET /diagnostics`, `POST /assistant`.
- Mock FastAPI server returning fixed sample data.
- **DoD:** OpenAPI approved; mock returns valid 201/200 for all 6 endpoints; FE and BE
  can compile against the same contract.

### M1 — Scheduling core `scheduler.py` *(pure module — heart of the system)*
- `compute_urgency` = `Energy_Required / Time_Until_Departure` (Book §4.6.1).
- `allocate` — greedy loop, sort by descending urgency, assign
  `min(max_charge_rate, required_rate, remaining_budget, charger_max_power)` [D1],
  subtract from budget. **Hard power constraint.**
- `advance_soc` — SoC update per 5-min step: `energy = power_kw * (5/60)`.
- Edge cases (Book Table 12) + tie-break (equal departure → larger energy deficit).
- **Fully unit-tested in isolation** — no DB, no network.
- **DoD:** Book §3.9 scheduler tests pass (Power limit, Urgency ranking, Deadline
  satisfaction, Budget recompute); Table 10 worked example reproduced as a unit test.

### M2 — Data model & repository `db.py`
- PostgreSQL schema for the 7 entities (Book §3.2) via Supabase migrations; preserve
  the Vehicle (static) ↔ ChargingSession (dynamic) split.
- `db.py` as repository (Book §3.7.3) — all reads/writes behind one abstract interface.
- **DoD:** schema created in Supabase; `db.py` reads/writes sessions, vehicles, base
  load; integration tests pass.

### M3 — Simulation engine `simulation.py` + dataset
- Ingest ACN-Data sessions + base-load profile into the schema (see DATASET.md).
- Replay engine: simulated clock, 5-minute cycle (Book §4.6.5) — detect new vehicles,
  read base load, compute budget, call `scheduler.allocate`, advance SoC, persist.
- **DoD:** full-night run completes; Table 14 scenarios (5/15/30/50 vehicles)
  reproduced with the limit preserved.

### M4 — FastAPI endpoints
- Implement the 6 endpoints over `scheduler` + `db` (replace mock).
- Authentication + 3 roles (Resident/Manager/Technician).
- Both recompute triggers wired [D3].
- **DoD:** every endpoint works end-to-end; contract identical to M0.

### M5 — Frontend *(parallel with M1–M4, vs. mock)*
- `HttpService` for all backend calls.
- `ResidentView`, `ManagerView`, `DiagnosticsView`.
- Recharts: live power profile vs. limit line, per-vehicle status, projected completion.
- Login + role-based routing.
- **DoD:** UC-1..UC-5 performable via UI; dashboard updates live during replay.

### M6 — AI assistant `assistant.py` *(read-only over Claude)*
- Anthropic Claude API, key via secured env var, never in client.
- Serialize current state as per-query context; **no authority to modify the schedule**
  (Book §4.6.6).
- Assistant panel on every screen.
- **DoD:** answers the §4.6.6 sample questions from live data.

### M7 — `analysis.py` + acceptance + statistical report
- `analysis.py` (pure, unit-tested): Table 15 metrics — mean load, peak utilization,
  on-time rate, mean/σ waiting time.
- Managed vs. uncontrolled load-profile chart with the limit line (Book §5.4).
- E2E + system + acceptance tests (Book Tables 6–8).
- **DoD:** acceptance tests pass; statistical report produced for a 30-vehicle run.

## Deferred (Book Ch. 6 — out of scope)
OCPP · live smart-meter feeds · in-vehicle telemetry app · MILP / Reinforcement
Learning · push notifications · time-of-use cost optimization.

## Unit-testability map
| Module | Test type | Why |
|---|---|---|
| `scheduler.py` | **Unit (full, isolated)** | Pure I/O — no DB/network |
| `analysis.py` | **Unit (full)** | Pure statistics over run data |
| `db.py` | Integration | Needs real PostgreSQL |
| `simulation.py` | Integration | Composes scheduler + db |
| endpoints / UI | System / E2E | End-to-end flow |
