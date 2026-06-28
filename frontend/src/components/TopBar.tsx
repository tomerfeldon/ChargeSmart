import { useAuth } from "../auth/AuthContext";
import type { Role } from "../types";

const ROLE_LABEL: Record<Role, string> = {
  resident: "Resident",
  manager: "Building Manager",
  technician: "Maintenance Tech",
};

export function TopBar({ live }: { live?: boolean }) {
  const { role, logout } = useAuth();
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "18px 28px",
        borderBottom: "1px solid var(--border)",
        background: "rgba(7,8,10,0.7)",
        backdropFilter: "blur(8px)",
        position: "sticky",
        top: 0,
        zIndex: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <BoltMark />
        <div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: 19, letterSpacing: "-0.02em" }}>
            ChargeSmart
          </div>
          <div className="eyebrow" style={{ fontSize: 9.5 }}>Grid Control · Tel Aviv</div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
        {live && (
          <span style={{ display: "flex", alignItems: "center", gap: 8 }} className="mono">
            <span className="live-dot" />
            <span style={{ fontSize: 11, letterSpacing: "0.14em", color: "var(--text-dim)" }}>LIVE</span>
          </span>
        )}
        {role && (
          <span className="pill" style={{ color: "var(--text)" }}>
            {ROLE_LABEL[role]}
          </span>
        )}
        <button onClick={logout}>Sign out</button>
      </div>
    </header>
  );
}

function BoltMark() {
  return (
    <svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden>
      <rect x="1" y="1" width="28" height="28" rx="8" stroke="var(--border-bright)" />
      <path d="M17 6 L10 16 H15 L13 24 L20 13 H15 L17 6 Z" fill="var(--lime)" />
    </svg>
  );
}
