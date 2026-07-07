"""Conversational AI assistant (M6) - a read-only layer over live state (Book §4.6.6).

On every query the current system state is serialized and supplied to Claude as context,
so each answer reflects live data. The assistant has NO authority to modify the schedule
- it only reads. This preserves the safety guarantee while adding an interpretive layer.

The LLM client is injected behind the ``LLMClient`` protocol, so the assistant is unit-
tested with a fake client. The real client (``AnthropicClient``) talks to the Anthropic
Claude API; its key comes from the ANTHROPIC_API_KEY environment variable and is never
exposed to the frontend.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Protocol

from .db import Repository

# Default to the latest, most capable model; override via env if desired.
DEFAULT_MODEL = os.environ.get("CHARGESMART_CLAUDE_MODEL", "claude-opus-4-8")

SYSTEM_PROMPT = (
    "You are the ChargeSmart assistant, a read-only helper for a smart EV-charging "
    "system in a residential building. Answer questions ONLY from the live system state "
    "provided in the user's message. You are strictly read-only: you cannot change the "
    "charging schedule, power limits, or any vehicle's allocation - if asked to, explain "
    "that the scheduler is the only component that allocates power. Stay within the "
    "EV-charging domain. Answer in the same language as the question. Be concise."
)


class LLMClient(Protocol):
    """Anything that can turn a (system, user) prompt pair into an answer string."""

    def complete(self, system: str, user: str) -> str: ...


def build_context(repo: Repository, building_id: int, now: datetime | None = None) -> str:
    """Serialize the current system state as readable context (read-only)."""
    now = now or datetime.now(timezone.utc)
    building = repo.get_building(building_id)
    base_load = repo.get_base_load_at(building_id, now)
    budget = max(0.0, building.max_building_power_kw - base_load)
    sessions = repo.list_active_sessions(building_id)
    chargers = repo.list_chargers(building_id)
    total_assigned = sum(s.assigned_power_kw for s in sessions)

    lines = [
        f"As of: {now.isoformat()}",
        f"Building power limit: {building.max_building_power_kw:.1f} kW",
        f"Current base load: {base_load:.1f} kW",
        f"Available charging budget: {budget:.1f} kW",
        f"Total power currently assigned to vehicles: {total_assigned:.1f} kW",
        f"Active charging sessions ({len(sessions)}):",
    ]
    for s in sessions:
        vehicle = repo.get_vehicle(s.vehicle_id)
        lines.append(
            f"  - session #{s.session_id}: vehicle {vehicle.license_plate} on charger "
            f"{s.charger_id}, SoC {s.current_soc:.0f}%/{s.target_soc:.0f}%, "
            f"assigned {s.assigned_power_kw:.1f} kW, status {s.status.value}, "
            f"departs {s.departure_time.isoformat()}"
        )
    lines.append("Chargers:")
    for c in chargers:
        lines.append(f"  - charger {c.charger_id}: max {c.max_power_output_kw:.1f} kW, status {c.status.value}")
    return "\n".join(lines)


def ask(
    repo: Repository,
    building_id: int,
    query: str,
    client: LLMClient | None,
    now: datetime | None = None,
) -> str:
    """Answer a natural-language question from the live state (read-only)."""
    if client is None:
        return (
            "The AI assistant is currently unavailable (no Anthropic API key configured). "
            "You can still read the dashboard for live charging status."
        )
    context = build_context(repo, building_id, now=now)
    user_message = f"Live system state:\n{context}\n\nQuestion: {query}"
    return client.complete(SYSTEM_PROMPT, user_message)


class AnthropicClient:
    """Real LLM client backed by the Anthropic Claude API.

    A simple, non-streaming completion is appropriate here: the context is small and the
    answer is short. The API key is read from the environment by the SDK and never leaves
    the server.
    """

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        import anthropic  # imported lazily so the module loads without the package

        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._model = model

    def complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


_client_singleton: LLMClient | None = None
_client_resolved = False


def get_client() -> LLMClient | None:
    """Return a cached real client if an API key is configured, else None (graceful)."""
    global _client_singleton, _client_resolved
    if not _client_resolved:
        _client_resolved = True
        if os.environ.get("ANTHROPIC_API_KEY"):
            _client_singleton = AnthropicClient()
    return _client_singleton
