// The evaluation centerpiece (Book §5.4): a trace-driven overnight simulation showing
// the managed load held under the building limit while the uncontrolled baseline blows
// past it, plus the Table 15 statistics.

import { useEffect, useState } from "react";
import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { AnalysisResponse } from "../types";

export function AnalysisPanel() {
  const [data, setData] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getAnalysis()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Failed to load analysis"));
    return () => { alive = false; };
  }, []);

  return (
    <div className="panel rise" style={{ padding: 24, animationDelay: "0.18s" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
        <p className="eyebrow">Evaluation benchmark · trace-driven overnight simulation</p>
        {data && <span className="mono" style={{ fontSize: 11, color: "var(--text-faint)" }}>{data.stats.vehicle_count} vehicles · {data.building_limit_kw}kW</span>}
      </div>
      <h2 style={{ fontSize: 21, marginBottom: 18 }}>Managed vs. Uncontrolled</h2>

      {error && <p style={{ color: "var(--red)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{error}</p>}
      {!data && !error && <p style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 13 }}>Running simulation…</p>}

      {data && (
        <>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={data.series} margin={{ top: 8, right: 14, left: -6, bottom: 0 }}>
              <defs>
                <linearGradient id="gManaged" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#b6ff3a" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="#b6ff3a" stopOpacity={0.04} />
                </linearGradient>
              </defs>
              <XAxis dataKey="t" tick={{ fill: "#565c54", fontSize: 10, fontFamily: "JetBrains Mono" }}
                     axisLine={{ stroke: "rgba(255,255,255,0.07)" }} tickLine={false} minTickGap={48} />
              <YAxis tick={{ fill: "#565c54", fontSize: 10, fontFamily: "JetBrains Mono" }}
                     axisLine={false} tickLine={false} width={44} unit="kW" />
              <Tooltip
                contentStyle={{ background: "#0c0f14", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, fontFamily: "JetBrains Mono", fontSize: 12 }}
                labelStyle={{ color: "#8b9088" }}
              />
              {/* Uncontrolled baseline - soars past the ceiling */}
              <Line type="monotone" dataKey="unmanaged" name="Uncontrolled" stroke="#ff4d62" strokeWidth={2} dot={false} isAnimationActive={false} />
              {/* Managed - held under the limit */}
              <Area type="monotone" dataKey="managed" name="Managed" stroke="#b6ff3a" strokeWidth={2} fill="url(#gManaged)" isAnimationActive={false} />
              <ReferenceLine y={data.building_limit_kw} stroke="#ff4d62" strokeDasharray="5 4" strokeWidth={1.5}
                label={{ value: `LIMIT ${data.building_limit_kw}kW`, fill: "#ff4d62", fontSize: 10, fontFamily: "JetBrains Mono", position: "insideTopRight" }} />
            </ComposedChart>
          </ResponsiveContainer>

          <div style={{ display: "flex", gap: 20, margin: "10px 2px 22px" }}>
            <Legend color="var(--lime)" label={`Managed peak ${data.stats.peak_load_kw.toFixed(1)} kW (under limit)`} />
            <Legend color="var(--red)" label={`Uncontrolled peak ${data.unmanaged_peak_kw.toFixed(0)} kW (would trip)`} />
          </div>

          <p className="eyebrow" style={{ marginBottom: 14 }}>Table 15 - statistical measures</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 14 }}>
            <Stat label="On-time completion" value={`${(data.stats.on_time_completion_rate * 100).toFixed(0)}%`} accent />
            <Stat label="Peak utilization" value={`${(data.stats.peak_utilization * 100).toFixed(0)}%`} />
            <Stat label="Mean building load" value={`${data.stats.mean_building_load_kw.toFixed(1)} kW`} />
            <Stat label="Mean waiting" value={`${data.stats.mean_waiting_minutes.toFixed(0)} min`} />
            <Stat label="Waiting σ" value={`${data.stats.std_waiting_minutes.toFixed(0)} min`} />
          </div>
        </>
      )}
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ width: 14, height: 3, borderRadius: 2, background: color }} />
      <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{label}</span>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div style={{ background: "var(--panel-2)", border: "1px solid var(--border)", borderRadius: 10, padding: "14px 16px" }}>
      <p className="eyebrow" style={{ fontSize: 9 }}>{label}</p>
      <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 6, color: accent ? "var(--lime)" : "var(--text)" }}>{value}</div>
    </div>
  );
}
