# ChargeSmart

**Smart EV charging management for residential buildings** - a software-only scheduling
layer that prevents electrical overload while guaranteeing every vehicle's charging deadline.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-4169E1?logo=postgresql&logoColor=white)
![Tests](https://img.shields.io/badge/tests-74%20passing-success)

When many tenants charge electric vehicles at once, the combined demand can exceed a
building's electrical capacity and trip its main breaker. ChargeSmart solves this in
software: a greedy, urgency-based scheduler allocates charging power across all connected
vehicles so the building's power limit is **never** exceeded, while still getting each car
to its target charge by its departure time - with no proprietary hardware.

> [!NOTE]
> **Live demo:** https://charge-smart-psi.vercel.app
> Sign in as `manager@chargesmart.test` / `manager123` (also `resident@…` and `tech@…`,
> password `<role>123`). The backend runs on a free tier that sleeps when idle, so the
> first request may take ~50 s to wake.

## Features

- **Hard safety guarantee** - aggregate charging load never crosses the building limit,
  enforced on every scheduling cycle.
- **Urgency-based scheduling** - power is prioritized by `energy needed ÷ time until
  departure`, not shared equally; urgent cars charge first, relaxed cars yield.
- **Dynamic budget** - the charging budget is the building limit minus the live base load
  (elevators, HVAC, lighting).
- **Trace-driven simulation** - replays a full charging night on a 5-minute cycle and
  reports the managed-vs-uncontrolled comparison and per-night statistics.
- **Role-based dashboards** - resident (register a vehicle), manager (live power dashboard
  + evaluation chart), technician (diagnostics), with a live Recharts power profile.
- **Read-only AI assistant** - ask natural-language questions about the live system state
  (optional, Claude-powered).
- **Swappable data tier** - the repository pattern lets the same scheduler run on an
  in-memory store or PostgreSQL/Supabase with zero algorithm changes.

## How it works

Each connected vehicle gets an urgency score - the minimum charging rate it needs to reach
its target by departure:

```
urgency = energy_required / time_until_departure   [kW]
```

Every cycle the scheduler sorts vehicles by descending urgency and greedily assigns each

```
min(vehicle max rate, required rate, remaining budget, charger max power)
```

subtracting from the budget as it goes. When the budget is spent, the remaining vehicles
wait. Because urgency is recomputed each cycle, a throttled car's urgency rises over time
and it self-corrects back into priority - so a simple greedy loop approximates a globally
fair schedule while keeping the power limit as a hard constraint.

## Architecture

Three decoupled tiers, with the scheduling core kept pure and isolated:

```
 React + TypeScript  ──HTTP──▶  FastAPI (Python)  ──▶  PostgreSQL (Supabase)
    Vercel                        Render                 7-entity schema
    role dashboards               REST API + JWT         scheduler = pure module
```

- **`backend/`** - FastAPI. The scheduling core (`app/scheduler.py`) is a pure,
  dependency-free module isolated from the API and database, so it can be unit-tested in
  full and reused for offline analysis. Also: repository layer (`app/db.py`,
  `app/repository_pg.py`), replay engine (`app/simulation.py`), statistics
  (`app/analysis.py`), and the AI assistant (`app/assistant.py`).
- **`frontend/`** - React + TypeScript (Vite), a "Grid Control" dashboard built on Recharts.
- **`db/`** - PostgreSQL schema for the seven data entities.

## Getting started

> [!TIP]
> Just want to see it running? Open the [live demo](https://charge-smart-psi.vercel.app) -
> no install required.

### Prerequisites

Python 3.12+, Node 18+, and Git.

### Setup

```bash
git clone https://github.com/tomerfeldon/ChargeSmart.git
cd ChargeSmart

# Backend
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt   # Windows
# macOS/Linux:  .venv/bin/python -m pip install -r requirements.txt
cd ..

# Frontend
cd frontend
npm install
cd ..
```

### Run

In two terminals:

```bash
# Backend (from backend/)
.venv\Scripts\python.exe -m uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs

# Frontend (from frontend/)
npm run dev                                                  # http://localhost:5173
```

> [!NOTE]
> **A database is optional.** With no `backend/.env`, the app runs on a seeded in-memory
> store - fully functional, just not persistent. To use PostgreSQL, create `backend/.env`
> with `DATABASE_URL=<Supabase connection string>` and run
> `python scripts/seed_supabase.py` once.

### Tests and simulation

```bash
cd backend
.venv\Scripts\python.exe -m pytest                     # 74 tests
.venv\Scripts\python.exe scripts/run_night.py          # simulate a 30-vehicle night
.venv\Scripts\python.exe scripts/generate_dataset.py   # write a synthetic dataset to data/
.venv\Scripts\python.exe scripts/run_from_dataset.py   # replay it and print the statistics
```

> [!NOTE]
> Four live-database integration tests skip automatically unless `DATABASE_URL` is set.

## Project structure

```
backend/
  app/         scheduler · repository (in-memory + PostgreSQL) · simulation · analysis · API · auth · assistant
  tests/       74 automated tests
  scripts/     simulation runners and database seeders
frontend/
  src/         views (resident / manager / technician), components, API client
db/
  migrations/  PostgreSQL schema (7 entities)
docs/          dataset and deployment notes
```

## Deployment

Deployed on Vercel (frontend) + Render (backend) + Supabase (database). See
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full walkthrough; configuration lives in
[`render.yaml`](render.yaml) and [`frontend/vercel.json`](frontend/vercel.json).

## AI assistant (optional)

Set `ANTHROPIC_API_KEY` (in `backend/.env` locally, or as an environment variable on
Render) to activate the in-app assistant. Without a key it returns a graceful
"unavailable" message and everything else works unchanged.

## Documentation

- [docs/DATASET.md](docs/DATASET.md) - dataset choice and schema mapping
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) - deployment guide

## Acknowledgements

Final-year software engineering project, Afeka College of Engineering - Department of
Software Engineering. Authors: Tomer Feldon, Avia Luria, Yuval Yehoshua.

> [!IMPORTANT]
> Hardware integration (OCPP) and live smart-meter feeds are out of scope by design; the
> system is validated through trace-driven simulation over a historical dataset.
