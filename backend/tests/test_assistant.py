"""Unit tests for the read-only AI assistant (M6).

The assistant is a read-only layer over live system state (Book §4.6.6): it serializes
the current state as context, sends it to Claude with the user's question, and returns
the answer. It has NO authority to modify the schedule — these tests pin that.

The LLM client is injected, so the assistant is fully testable with a fake client; no
API key or network is required here.
"""

from datetime import datetime, timedelta, timezone

from app.assistant import ask, build_context
from app.db import InMemoryRepository

NOW = datetime(2025, 1, 15, 22, 0, 0, tzinfo=timezone.utc)


class FakeClient:
    """Captures the prompt it receives and returns a canned answer."""

    def __init__(self, answer="canned answer"):
        self.answer = answer
        self.last_system = None
        self.last_user = None

    def complete(self, system: str, user: str) -> str:
        self.last_system = system
        self.last_user = user
        return self.answer


def seeded_repo():
    r = InMemoryRepository()
    r.seed_building(1, "1 Rothschild Blvd", max_building_power_kw=50.0)
    r.seed_charger(1, 1, max_power_output_kw=22.0)
    r.add_base_load(1, NOW, 8.0)
    vehicle = r.get_or_create_vehicle(1, "AAA-111", battery_capacity_kwh=60.0, max_charge_rate_kw=11.0)
    s = r.create_session(vehicle.vehicle_id, 1, start_soc=40.0, current_soc=40.0, target_soc=80.0,
                         departure_time=NOW + timedelta(hours=5))
    r.update_session(s.session_id, assigned_power_kw=7.2)
    return r


def test_build_context_includes_live_state():
    ctx = build_context(seeded_repo(), 1, now=NOW)
    assert "50" in ctx           # building limit
    assert "AAA-111" in ctx or "7.2" in ctx  # the live session


def test_ask_passes_live_state_to_client():
    fake = FakeClient()
    ask(seeded_repo(), 1, "Is the building safe?", client=fake, now=NOW)
    # The serialized live state must reach the model as context.
    assert "50" in fake.last_user
    assert fake.last_system  # a system prompt was supplied


def test_ask_returns_client_answer():
    fake = FakeClient(answer="The building is under safe load.")
    answer = ask(seeded_repo(), 1, "How are we doing?", client=fake, now=NOW)
    assert answer == "The building is under safe load."


def test_ask_is_read_only():
    repo = seeded_repo()
    before = repo.get_session(1)
    before_power = before.assigned_power_kw
    before_status = before.status
    ask(repo, 1, "Change everything to 100 kW now!", client=FakeClient(), now=NOW)
    after = repo.get_session(1)
    # The assistant must never mutate the schedule (Book §4.6.6).
    assert after.assigned_power_kw == before_power
    assert after.status == before_status


def test_ask_without_client_returns_graceful_message():
    answer = ask(seeded_repo(), 1, "Hello?", client=None, now=NOW)
    assert isinstance(answer, str)
    assert "assistant" in answer.lower() or "unavailable" in answer.lower()
