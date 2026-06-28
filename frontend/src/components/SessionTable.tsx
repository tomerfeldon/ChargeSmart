import type { SessionRead } from "../types";

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`pill ${status}`}>
      <span className="dot" />
      {status}
    </span>
  );
}

function SocBar({ current, target }: { current: number; target: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9, minWidth: 150 }}>
      <div style={{ position: "relative", flex: 1, height: 7, borderRadius: 4, background: "var(--panel-2)", border: "1px solid var(--border)" }}>
        <div style={{ position: "absolute", inset: 0, width: `${current}%`, background: "var(--lime)", borderRadius: 4, transition: "width 0.5s ease" }} />
        <div style={{ position: "absolute", top: -3, bottom: -3, left: `${target}%`, width: 2, background: "var(--text-dim)" }} title={`Target ${target}%`} />
      </div>
      <span className="mono" style={{ fontSize: 12, color: "var(--text-dim)", width: 36 }}>{current.toFixed(0)}%</span>
    </div>
  );
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function SessionTable({ sessions }: { sessions: SessionRead[] }) {
  if (sessions.length === 0) {
    return (
      <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
        No active charging sessions.
      </div>
    );
  }
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr>
          {["Session", "Charge level", "Assigned", "Status", "Ready by"].map((h) => (
            <th key={h} className="eyebrow" style={{ textAlign: "left", padding: "0 0 12px", fontSize: 10 }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sessions.map((s) => (
          <tr key={s.session_id} style={{ borderTop: "1px solid var(--border)" }}>
            <td style={{ padding: "13px 0" }}>
              <div className="mono" style={{ fontSize: 13 }}>#{s.session_id}</div>
              <div style={{ fontSize: 11, color: "var(--text-faint)" }}>charger {s.charger_id}</div>
            </td>
            <td><SocBar current={s.current_soc} target={s.target_soc} /></td>
            <td className="mono" style={{ fontSize: 14, color: s.assigned_power_kw > 0 ? "var(--lime)" : "var(--text-faint)" }}>
              {s.assigned_power_kw.toFixed(1)} kW
            </td>
            <td><StatusPill status={s.status} /></td>
            <td className="mono" style={{ fontSize: 13, color: "var(--text-dim)" }}>{fmtTime(s.projected_completion_time)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
