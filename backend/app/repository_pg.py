"""PostgreSQL / Supabase implementation of the Repository interface (M2 live wiring).

This is the production data tier the Book specifies (PostgreSQL via Supabase, §3.7). It
implements the exact same `Repository` interface as `InMemoryRepository`, so the
scheduler, simulation, service layer, and API are entirely unaware of which store is in
use - swapping the in-memory store for this one is a data-tier-only change (Book §6.6).

Connection details come from the DATABASE_URL environment variable (never hard-coded).
"""

from __future__ import annotations

from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from .db import Repository
from .entities import (
    Building,
    BuildingBaseLoad,
    Charger,
    ChargerStatus,
    ChargingSession,
    EventType,
    SessionStatus,
    SystemEventLog,
    User,
    UserRole,
    Vehicle,
)

# Columns a session UPDATE is allowed to touch (prevents SQL injection via field names).
_UPDATABLE_SESSION_COLUMNS = {
    "start_soc", "current_soc", "target_soc", "departure_time", "assigned_power_kw", "status", "charger_id",
}


class SupabaseRepository(Repository):
    """Repository backed by a Supabase/PostgreSQL database via psycopg (autocommit)."""

    def __init__(self, conninfo: str) -> None:
        self._conn = psycopg.connect(conninfo, autocommit=True, row_factory=dict_row)
        # Supabase's transaction-mode pooler (pgbouncer) rejects server-side prepared
        # statements; disabling them keeps this repository compatible with every pooler mode.
        self._conn.prepare_threshold = None

    def close(self) -> None:
        self._conn.close()

    # --- row -> entity mappers --- #
    @staticmethod
    def _building(r) -> Building:
        return Building(r["building_id"], r["address"], r["max_building_power_kw"])

    @staticmethod
    def _user(r) -> User:
        return User(r["user_id"], r["building_id"], r["email"], r["password_hash"], UserRole(r["role"]), r["full_name"])

    @staticmethod
    def _charger(r) -> Charger:
        return Charger(r["charger_id"], r["building_id"], r["max_power_output_kw"], ChargerStatus(r["status"]))

    @staticmethod
    def _vehicle(r) -> Vehicle:
        return Vehicle(r["vehicle_id"], r["user_id"], r["license_plate"], r["battery_capacity_kwh"], r["max_charge_rate_kw"])

    @staticmethod
    def _session(r) -> ChargingSession:
        return ChargingSession(
            session_id=r["session_id"], vehicle_id=r["vehicle_id"], charger_id=r["charger_id"],
            start_soc=r["start_soc"], current_soc=r["current_soc"], target_soc=r["target_soc"],
            departure_time=r["departure_time"], assigned_power_kw=r["assigned_power_kw"],
            status=SessionStatus(r["status"]),
        )

    @staticmethod
    def _event(r) -> SystemEventLog:
        return SystemEventLog(r["event_id"], r["building_id"], r["charger_id"], r["timestamp"],
                              EventType(r["event_type"]), r["description"])

    # --- Seed helpers (used by scripts/seed_supabase.py; not in the abstract interface) --- #
    def seed_building(self, building_id: int, address: str, max_building_power_kw: float) -> Building:
        row = self._conn.execute(
            "INSERT INTO buildings (building_id, address, max_building_power_kw) VALUES (%s, %s, %s) "
            "ON CONFLICT (building_id) DO UPDATE SET address = EXCLUDED.address, "
            "max_building_power_kw = EXCLUDED.max_building_power_kw RETURNING *",
            (building_id, address, max_building_power_kw),
        ).fetchone()
        return self._building(row)

    def seed_charger(self, charger_id: int, building_id: int, max_power_output_kw: float,
                     status: ChargerStatus = ChargerStatus.ONLINE) -> Charger:
        row = self._conn.execute(
            "INSERT INTO chargers (charger_id, building_id, max_power_output_kw, status) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (charger_id) DO UPDATE SET max_power_output_kw = EXCLUDED.max_power_output_kw, "
            "status = EXCLUDED.status RETURNING *",
            (charger_id, building_id, max_power_output_kw, status.value),
        ).fetchone()
        return self._charger(row)

    # --- Users --- #
    def create_user(self, building_id, email, password_hash, role, full_name) -> User:
        row = self._conn.execute(
            "INSERT INTO users (building_id, email, password_hash, role, full_name) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash, "
            "role = EXCLUDED.role, full_name = EXCLUDED.full_name RETURNING *",
            (building_id, email, password_hash, role.value, full_name),
        ).fetchone()
        return self._user(row)

    def get_user(self, user_id: int) -> User | None:
        row = self._conn.execute("SELECT * FROM users WHERE user_id = %s", (user_id,)).fetchone()
        return self._user(row) if row else None

    def get_user_by_email(self, email: str) -> User | None:
        row = self._conn.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()
        return self._user(row) if row else None

    # --- Building --- #
    def get_building(self, building_id: int) -> Building:
        row = self._conn.execute("SELECT * FROM buildings WHERE building_id = %s", (building_id,)).fetchone()
        return self._building(row)

    def update_building_limit(self, building_id: int, max_building_power_kw: float) -> Building:
        row = self._conn.execute(
            "UPDATE buildings SET max_building_power_kw = %s WHERE building_id = %s RETURNING *",
            (max_building_power_kw, building_id),
        ).fetchone()
        return self._building(row)

    # --- Chargers --- #
    def list_chargers(self, building_id: int) -> list[Charger]:
        rows = self._conn.execute(
            "SELECT * FROM chargers WHERE building_id = %s ORDER BY charger_id", (building_id,)
        ).fetchall()
        return [self._charger(r) for r in rows]

    def get_charger(self, charger_id: int) -> Charger:
        row = self._conn.execute("SELECT * FROM chargers WHERE charger_id = %s", (charger_id,)).fetchone()
        return self._charger(row)

    def update_charger_status(self, charger_id: int, status: ChargerStatus) -> Charger:
        row = self._conn.execute(
            "UPDATE chargers SET status = %s WHERE charger_id = %s RETURNING *",
            (status.value, charger_id),
        ).fetchone()
        return self._charger(row)

    # --- Vehicles --- #
    def get_or_create_vehicle(self, user_id, license_plate, battery_capacity_kwh, max_charge_rate_kw) -> Vehicle:
        existing = self._conn.execute(
            "SELECT * FROM vehicles WHERE license_plate = %s", (license_plate,)
        ).fetchone()
        if existing:
            return self._vehicle(existing)
        row = self._conn.execute(
            "INSERT INTO vehicles (user_id, license_plate, battery_capacity_kwh, max_charge_rate_kw) "
            "VALUES (%s, %s, %s, %s) RETURNING *",
            (user_id, license_plate, battery_capacity_kwh, max_charge_rate_kw),
        ).fetchone()
        return self._vehicle(row)

    def get_vehicle(self, vehicle_id: int) -> Vehicle:
        row = self._conn.execute("SELECT * FROM vehicles WHERE vehicle_id = %s", (vehicle_id,)).fetchone()
        return self._vehicle(row)

    # --- Charging sessions --- #
    def create_session(self, vehicle_id, charger_id, start_soc, current_soc, target_soc, departure_time) -> ChargingSession:
        row = self._conn.execute(
            "INSERT INTO charging_sessions (vehicle_id, charger_id, start_soc, current_soc, target_soc, "
            "departure_time, assigned_power_kw, status) VALUES (%s, %s, %s, %s, %s, %s, 0, 'waiting') RETURNING *",
            (vehicle_id, charger_id, start_soc, current_soc, target_soc, departure_time),
        ).fetchone()
        return self._session(row)

    def get_session(self, session_id: int) -> ChargingSession:
        row = self._conn.execute("SELECT * FROM charging_sessions WHERE session_id = %s", (session_id,)).fetchone()
        if row is None:
            raise KeyError(session_id)
        return self._session(row)

    def update_session(self, session_id: int, **fields) -> ChargingSession:
        if not fields:
            return self.get_session(session_id)
        sets, values = [], []
        for key, value in fields.items():
            if key not in _UPDATABLE_SESSION_COLUMNS:
                raise AttributeError(f"ChargingSession column '{key}' is not updatable")
            sets.append(f"{key} = %s")
            values.append(value.value if hasattr(value, "value") else value)  # enum -> str
        values.append(session_id)
        row = self._conn.execute(
            f"UPDATE charging_sessions SET {', '.join(sets)} WHERE session_id = %s RETURNING *",
            values,
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return self._session(row)

    def list_active_sessions(self, building_id: int) -> list[ChargingSession]:
        """Active = connected (not completed/canceled) and not yet at target SoC (Book §3.5)."""
        rows = self._conn.execute(
            "SELECT s.* FROM charging_sessions s JOIN chargers c ON s.charger_id = c.charger_id "
            "WHERE c.building_id = %s AND s.status NOT IN ('completed', 'canceled') "
            "AND s.current_soc < s.target_soc ORDER BY s.session_id",
            (building_id,),
        ).fetchall()
        return [self._session(r) for r in rows]

    # --- Base load --- #
    def add_base_load(self, building_id, timestamp, base_load_kw) -> BuildingBaseLoad:
        row = self._conn.execute(
            'INSERT INTO building_base_load (building_id, "timestamp", base_load_kw) VALUES (%s, %s, %s) RETURNING *',
            (building_id, timestamp, base_load_kw),
        ).fetchone()
        return BuildingBaseLoad(row["load_id"], row["building_id"], row["timestamp"], row["base_load_kw"])

    def get_base_load_at(self, building_id: int, timestamp: datetime) -> float:
        row = self._conn.execute(
            'SELECT base_load_kw FROM building_base_load WHERE building_id = %s AND "timestamp" <= %s '
            'ORDER BY "timestamp" DESC LIMIT 1',
            (building_id, timestamp),
        ).fetchone()
        return row["base_load_kw"] if row else 0.0

    # --- Event log --- #
    def add_event(self, building_id, charger_id, timestamp, event_type, description) -> SystemEventLog:
        row = self._conn.execute(
            'INSERT INTO system_event_log (building_id, charger_id, "timestamp", event_type, description) '
            "VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (building_id, charger_id, timestamp, event_type.value, description),
        ).fetchone()
        return self._event(row)

    def list_events(self, building_id: int, limit: int = 100) -> list[SystemEventLog]:
        rows = self._conn.execute(
            'SELECT * FROM system_event_log WHERE building_id = %s ORDER BY "timestamp" DESC LIMIT %s',
            (building_id, limit),
        ).fetchall()
        return [self._event(r) for r in rows]
