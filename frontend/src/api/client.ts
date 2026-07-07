// HttpService - the single module that talks to the FastAPI backend (Book §4.4).
// Mirrors the client-server interaction of Book §3.7.1.

import type {
  AnalysisResponse,
  DiagnosticsResponse,
  ScheduleResponse,
  SessionCreate,
  SessionRead,
  TokenResponse,
} from "../types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

const TOKEN_KEY = "chargesmart.token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = tokenStore.get();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  createSession: (payload: SessionCreate) =>
    request<SessionRead>("/sessions", { method: "POST", body: JSON.stringify(payload) }),

  updateSession: (id: number, payload: Partial<SessionCreate>) =>
    request<SessionRead>(`/sessions/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  getSchedule: () => request<ScheduleResponse>("/schedule"),

  setBuildingLimit: (kw: number) =>
    request<{ max_building_power_kw: number }>("/building/limit", {
      method: "PUT",
      body: JSON.stringify({ max_building_power_kw: kw }),
    }),

  getDiagnostics: () => request<DiagnosticsResponse>("/diagnostics"),

  getAnalysis: () => request<AnalysisResponse>("/analysis"),

  askAssistant: (query: string) =>
    request<{ answer: string }>("/assistant", { method: "POST", body: JSON.stringify({ query }) }),
};

export { ApiError };
