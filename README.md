# ChargeSmart

Smart EV charging management for residential buildings — a software-only scheduling
layer that prevents electrical overload while guaranteeing charging deadlines.

## 🌐 Live demo

- **App:** https://charge-smart-psi.vercel.app  (log in as `manager@chargesmart.test` / `manager123`)
- **API:** https://chargesmart-api.onrender.com/docs

Hosted on Vercel (frontend) + Render (backend) + Supabase (PostgreSQL). The Render free
tier sleeps after ~15 min idle, so the first load may take ~50 s to wake.

Authoritative spec: `ChargeSmart_Project_Book_v5_EN.docx`. Development plan and decisions:
[PLAN.md](PLAN.md). Dataset choice: [docs/DATASET.md](docs/DATASET.md).

## Architecture (three tiers)

- **`backend/`** — Python + FastAPI. Pure scheduling core (`app/scheduler.py`), repository
  (`app/db.py`), replay engine (`app/simulation.py`), statistics (`app/analysis.py`),
  REST API + JWT auth (`app/main.py`).
- **`frontend/`** — React + TypeScript (Vite), Recharts. "Grid Control" dashboard with
  resident / manager / technician role views.
- **`db/`** — PostgreSQL schema (`migrations/001_initial_schema.sql`) for the 7 entities.

The scheduling core is a pure, isolated module (no DB/API) so it can be unit-tested in
full and reused for offline analysis.

## Run it

**Backend** (from `backend/`):

```
.venv\Scripts\python.exe -m uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
```

**Frontend** (from `frontend/`):

```
npm install      # first time only
npm run dev      # http://localhost:5173
```

Demo logins: `resident@chargesmart.test / resident123`,
`manager@chargesmart.test / manager123`, `tech@chargesmart.test / tech123`.

## Tests & demo

```
cd backend
.venv\Scripts\python.exe -m pytest               # 69 tests (scheduler, repo, simulation, API, analysis, dataset)
.venv\Scripts\python.exe scripts/run_night.py    # in-code 30-vehicle night (Table 15 stats)

# Trace-driven run over a generated dataset on disk:
.venv\Scripts\python.exe scripts/generate_dataset.py   # writes data/*.csv (deterministic)
.venv\Scripts\python.exe scripts/run_from_dataset.py   # ingest + simulate + report
```

The dataset is **synthetic** (real charging data is private) but realistic and
deterministic; the replay engine ingests it through the same interface a real dataset
would use. See [docs/DATASET.md](docs/DATASET.md).

## AI assistant (M6)

The `/assistant` endpoint and the in-app assistant panel are a **read-only** layer over
live state (Book §4.6.6). They activate when an Anthropic API key is present:

```
# backend, before starting uvicorn:
setx ANTHROPIC_API_KEY "sk-ant-..."     # then open a new shell
```

Without a key, the assistant returns a graceful "unavailable" message — everything else
works unchanged.

## Status

All in-scope milestones built and verified: M0 API contract · M1 scheduler core ·
M2 data model + repository · M3 simulation · M4 REST API + auth · M5 frontend ·
M6 read-only AI assistant · M7 statistical analysis. **60 backend tests pass; frontend
builds clean.**

Pending (need your resources): activate M6 with an Anthropic key; swap the in-memory
store for a live `SupabaseRepository`; ingest the real ACN-Data dataset.

Out of scope (future work, Book Ch. 6): OCPP hardware integration, live smart-meter feeds.
