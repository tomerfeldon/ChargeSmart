"""End-to-end API tests for the real backend (M4).

These exercise the FastAPI endpoints over the live in-memory store with JWT auth and
role enforcement. The contract shapes are identical to M0; the bodies are now real
(scheduler-computed), so these supersede the M0 mock smoke tests.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.state import reset_state

client = TestClient(app)

RESIDENT = ("resident@chargesmart.test", "resident123")
MANAGER = ("manager@chargesmart.test", "manager123")
TECH = ("tech@chargesmart.test", "tech123")


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_state()
    yield


def login(creds) -> str:
    r = client.post("/auth/login", json={"email": creds[0], "password": creds[1]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def hdr(creds) -> dict:
    return {"Authorization": f"Bearer {login(creds)}"}


def future(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def session_payload(plate, charger_id=1, current_soc=20.0, target_soc=80.0, depart_h=5.0):
    return {
        "charger_id": charger_id,
        "license_plate": plate,
        "battery_capacity_kwh": 60.0,
        "max_charge_rate_kw": 11.0,
        "current_soc": current_soc,
        "target_soc": target_soc,
        "departure_time": future(depart_h),
    }


# --- Auth ------------------------------------------------------------------- #
def test_login_valid_returns_token_and_role():
    r = client.post("/auth/login", json={"email": RESIDENT[0], "password": RESIDENT[1]})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "resident"


def test_login_invalid_password_401():
    r = client.post("/auth/login", json={"email": RESIDENT[0], "password": "nope"})
    assert r.status_code == 401


def test_protected_endpoint_requires_auth():
    r = client.post("/sessions", json=session_payload("11-111-11"))
    assert r.status_code in (401, 403)


# --- Sessions (UC-1, UC-2) -------------------------------------------------- #
def test_resident_creates_session_with_scheduler_computed_power():
    r = client.post("/sessions", json=session_payload("11-111-11"), headers=hdr(RESIDENT))
    assert r.status_code == 201, r.text
    body = r.json()
    # A single vehicle with ample budget gets exactly its required rate (not the mock echo).
    # 60 kWh * (80-20)/100 = 36 kWh over 5 h => 7.2 kW.
    assert body["assigned_power_kw"] == pytest.approx(7.2, abs=0.1)
    assert body["status"] == "charging"
    assert body["projected_completion_time"] is not None


def test_patch_session_recomputes_on_earlier_departure():
    create = client.post("/sessions", json=session_payload("22-222-22", depart_h=10.0), headers=hdr(RESIDENT))
    sid = create.json()["session_id"]
    before = create.json()["assigned_power_kw"]
    patch = client.patch(f"/sessions/{sid}", json={"departure_time": future(1.0)}, headers=hdr(RESIDENT))
    assert patch.status_code == 200
    # Less time to the same target => higher required rate => more power.
    assert patch.json()["assigned_power_kw"] > before


# --- Schedule: hard constraint on real data (Book §2.1) --------------------- #
def test_schedule_respects_hard_constraint():
    for i in range(6):
        client.post("/sessions", json=session_payload(f"C{i}", charger_id=1 + i % 2, depart_h=1.0),
                    headers=hdr(RESIDENT))
    r = client.get("/schedule", headers=hdr(RESIDENT))
    assert r.status_code == 200
    body = r.json()
    assert body["total_assigned_kw"] <= body["available_budget_kw"] + 1e-9


# --- Building limit (UC-3): manager only ------------------------------------ #
def test_resident_cannot_set_limit_403():
    r = client.put("/building/limit", json={"max_building_power_kw": 80.0}, headers=hdr(RESIDENT))
    assert r.status_code == 403


def test_manager_sets_limit_and_it_constrains_schedule():
    # Many hungry vehicles, then squeeze the limit to 5 kW.
    for i in range(6):
        client.post("/sessions", json=session_payload(f"H{i}", charger_id=1 + i % 2, depart_h=0.5),
                    headers=hdr(RESIDENT))
    put = client.put("/building/limit", json={"max_building_power_kw": 5.0}, headers=hdr(MANAGER))
    assert put.status_code == 200
    assert put.json()["max_building_power_kw"] == 5.0
    sched = client.get("/schedule", headers=hdr(RESIDENT)).json()
    assert sched["total_assigned_kw"] <= 5.0 + 1e-9


# --- Diagnostics (UC-5): technician/manager only ---------------------------- #
def test_resident_cannot_view_diagnostics_403():
    assert client.get("/diagnostics", headers=hdr(RESIDENT)).status_code == 403


def test_technician_views_diagnostics():
    r = client.get("/diagnostics", headers=hdr(TECH))
    assert r.status_code == 200
    body = r.json()
    assert any(c["status"] == "faulted" for c in body["chargers"])


# --- Assistant (stub until M6) ---------------------------------------------- #
def test_assistant_returns_answer():
    r = client.post("/assistant", json={"query": "Is the building under safe load?"}, headers=hdr(RESIDENT))
    assert r.status_code == 200
    assert isinstance(r.json()["answer"], str)
