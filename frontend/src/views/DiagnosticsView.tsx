import { useEffect, useState } from "react";
import { api } from "../api/client";
import { TopBar } from "../components/TopBar";
import { Banner, SectionTitle } from "./ManagerView";
import type { DiagnosticsResponse } from "../types";

const wrap: React.CSSProperties = { maxWidth: 1180, margin: "0 auto", padding: "28px" };

export function DiagnosticsView() {
  const [data, setData] = useState<DiagnosticsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const d = await api.getDiagnostics();
        if (alive) { setData(d); setError(null); }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Failed to load diagnostics");
      }
    };
    tick();
    const id = window.setInterval(tick, 3000);
    return () => { alive = false; window.clearInterval(id); };
  }, []);

  return (
    <>
      <TopBar live />
      <div style={wrap}>
        <SectionTitle eyebrow="Maintenance" title="System Diagnostics" />
        {error && <Banner text={`Backend unreachable — ${error}.`} />}

        <p className="eyebrow" style={{ marginBottom: 14 }}>Charging points</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 14, marginBottom: 30 }}>
          {data?.chargers.map((c) => (
            <div key={c.charger_id} className="panel rise" style={{ padding: 18 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                <span className="mono" style={{ fontSize: 15 }}>Charger {c.charger_id}</span>
                <span className={`pill ${c.status}`}><span className="dot" />{c.status}</span>
              </div>
              <p className="eyebrow" style={{ fontSize: 9.5 }}>Max output</p>
              <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>{c.max_power_output_kw.toFixed(1)} kW</div>
            </div>
          ))}
        </div>

        <p className="eyebrow" style={{ marginBottom: 14 }}>Event log</p>
        <div className="panel rise" style={{ padding: 8 }}>
          {data && data.event_log.length > 0 ? (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <tbody>
                {data.event_log.map((e) => (
                  <tr key={e.event_id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td className="mono" style={{ padding: "12px 16px", fontSize: 12, color: "var(--text-dim)", whiteSpace: "nowrap" }}>
                      {new Date(e.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                    </td>
                    <td style={{ padding: "12px 8px" }}>
                      <EventTag type={e.event_type} />
                    </td>
                    <td style={{ padding: "12px 16px", fontSize: 13, color: "var(--text)" }}>{e.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ padding: 30, textAlign: "center", color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
              No events logged yet.
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function EventTag({ type }: { type: string }) {
  const fault = type.includes("fault") || type.includes("disconnect");
  const color = fault ? "var(--red)" : type.includes("limit") ? "var(--amber)" : "var(--text-dim)";
  return (
    <span className="mono" style={{ fontSize: 10.5, letterSpacing: "0.06em", textTransform: "uppercase", color, border: `1px solid ${color}33`, borderRadius: 6, padding: "3px 8px", whiteSpace: "nowrap" }}>
      {type.replace(/_/g, " ")}
    </span>
  );
}
