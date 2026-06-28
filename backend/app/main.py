"""ChargeSmart API server (M4) — real endpoints over the scheduler + repository.

The six endpoints of the contract (Book §4.2) plus authentication. Bodies are now
backed by the pure scheduler and the repository (no more mock data); the response
shapes are identical to the M0 contract, so the frontend is unaffected.

Run:  py -m uvicorn app.main:app --reload   (from backend/)
Docs: http://127.0.0.1:8000/docs

Demo users (dev only): resident@chargesmart.test / resident123,
manager@chargesmart.test / manager123, tech@chargesmart.test / tech123.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from . import assistant, service
from .deps import get_current_user, repo_dependency, require_role
from .db import Repository
from .entities import User, UserRole
from .schemas import (
    AnalysisResponse,
    AssistantQuery,
    AssistantResponse,
    BuildingLimitUpdate,
    BuildingRead,
    DiagnosticsResponse,
    LoginRequest,
    ScheduleResponse,
    SessionCreate,
    SessionRead,
    SessionUpdate,
    TokenResponse,
)
from .security import create_access_token, verify_password

app = FastAPI(
    title="ChargeSmart API",
    version="0.1.0",
    description="Smart EV charging management for residential buildings (M4).",
)

# Allowed browser origins. Defaults to the local dev server; in production set
# CHARGESMART_CORS_ORIGINS to the deployed frontend URL(s), comma-separated.
_DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
_cors_origins = [o.strip() for o in os.environ.get("CHARGESMART_CORS_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# --- Authentication --------------------------------------------------------- #
@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(payload: LoginRequest, repo: Repository = Depends(repo_dependency)) -> TokenResponse:
    user = repo.get_user_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(user.user_id, user.role), role=user.role)


# --- Session management (UC-1, UC-2) — resident ----------------------------- #
@app.post("/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED, tags=["sessions"])
def create_session(
    payload: SessionCreate,
    user: User = Depends(require_role(UserRole.RESIDENT)),
    repo: Repository = Depends(repo_dependency),
) -> SessionRead:
    return service.register_session(repo, user, payload)


@app.patch("/sessions/{session_id}", response_model=SessionRead, tags=["sessions"])
def update_session(
    session_id: int,
    payload: SessionUpdate,
    user: User = Depends(require_role(UserRole.RESIDENT)),
    repo: Repository = Depends(repo_dependency),
) -> SessionRead:
    try:
        return service.update_session(repo, user, session_id, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found.")


# --- Scheduling — any authenticated user ------------------------------------ #
@app.get("/schedule", response_model=ScheduleResponse, tags=["scheduling"])
def get_schedule(
    user: User = Depends(get_current_user),
    repo: Repository = Depends(repo_dependency),
) -> ScheduleResponse:
    return service.get_schedule(repo, user.building_id)


# --- Building configuration (UC-3) — manager -------------------------------- #
@app.put("/building/limit", response_model=BuildingRead, tags=["building"])
def set_building_limit(
    payload: BuildingLimitUpdate,
    user: User = Depends(require_role(UserRole.MANAGER)),
    repo: Repository = Depends(repo_dependency),
) -> BuildingRead:
    return service.set_building_limit(repo, user.building_id, payload.max_building_power_kw)


# --- Analysis report (Book §5.4) — any authenticated user ------------------- #
@app.get("/analysis", response_model=AnalysisResponse, tags=["analysis"])
def get_analysis(
    user: User = Depends(get_current_user),
    repo: Repository = Depends(repo_dependency),
) -> AnalysisResponse:
    """Trace-driven evaluation: Table 15 statistics + managed-vs-uncontrolled curves."""
    return service.build_analysis(repo, user.building_id)


# --- Diagnostics (UC-5) — technician or manager ----------------------------- #
@app.get("/diagnostics", response_model=DiagnosticsResponse, tags=["diagnostics"])
def get_diagnostics(
    user: User = Depends(require_role(UserRole.TECHNICIAN, UserRole.MANAGER)),
    repo: Repository = Depends(repo_dependency),
) -> DiagnosticsResponse:
    return service.get_diagnostics(repo, user.building_id)


# --- AI assistant (read-only stub until M6) — any authenticated user -------- #
@app.post("/assistant", response_model=AssistantResponse, tags=["assistant"])
def ask_assistant(
    payload: AssistantQuery,
    user: User = Depends(get_current_user),
    repo: Repository = Depends(repo_dependency),
) -> AssistantResponse:
    """Read-only natural-language query over live state (Book §4.6.6).

    Backed by Claude when ANTHROPIC_API_KEY is set; otherwise returns a graceful
    'unavailable' message. The assistant never mutates the schedule.
    """
    answer = assistant.ask(repo, user.building_id, payload.query, client=assistant.get_client())
    return AssistantResponse(answer=answer)
