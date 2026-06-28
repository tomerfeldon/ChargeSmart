import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { api, tokenStore } from "../api/client";
import type { Role } from "../types";

interface AuthState {
  role: Role | null;
  email: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

// Decode the role from the persisted JWT payload (no verification needed client-side).
function roleFromToken(): Role | null {
  const token = tokenStore.get();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return (payload.role as Role) ?? null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role | null>(roleFromToken());
  const [email, setEmail] = useState<string | null>(null);

  const value = useMemo<AuthState>(
    () => ({
      role,
      email,
      login: async (em, password) => {
        const res = await api.login(em, password);
        tokenStore.set(res.access_token);
        setRole(res.role);
        setEmail(em);
      },
      logout: () => {
        tokenStore.clear();
        setRole(null);
        setEmail(null);
      },
    }),
    [role, email],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
