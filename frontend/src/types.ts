// Mirrors the backend API contract (app/schemas.py).

export type Role = "resident" | "manager" | "technician";
export type SessionStatus = "waiting" | "charging" | "completed" | "canceled";
export type ChargerStatus = "online" | "offline" | "faulted";

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: Role;
}

export interface SessionRead {
  session_id: number;
  vehicle_id: number;
  charger_id: number;
  start_soc: number;
  current_soc: number;
  target_soc: number;
  departure_time: string;
  assigned_power_kw: number;
  status: SessionStatus;
  projected_completion_time: string | null;
}

export interface ScheduleResponse {
  building_limit_kw: number;
  base_load_kw: number;
  available_budget_kw: number;
  total_assigned_kw: number;
  as_of: string;
  sessions: SessionRead[];
}

export interface ChargerRead {
  charger_id: number;
  building_id: number;
  max_power_output_kw: number;
  status: ChargerStatus;
}

export interface EventLogRead {
  event_id: number;
  building_id: number;
  charger_id: number | null;
  timestamp: string;
  event_type: string;
  description: string;
}

export interface DiagnosticsResponse {
  chargers: ChargerRead[];
  event_log: EventLogRead[];
}

export interface SessionCreate {
  charger_id: number;
  license_plate: string;
  battery_capacity_kwh: number;
  max_charge_rate_kw: number;
  current_soc: number;
  target_soc: number;
  departure_time: string;
}
