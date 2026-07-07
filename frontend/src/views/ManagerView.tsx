import { useState } from "react";
import { api } from "../api/client";
import { AnalysisPanel } from "../components/AnalysisPanel";
import { LoadChart } from "../components/LoadChart";
import { PowerGauge } from "../components/PowerGauge";
import { SessionTable } from "../components/SessionTable";
import { TopBar } from "../components/TopBar";
import { useSchedule } from "../hooks/useSchedule";

const wrap: React.CSSProperties = { maxWidth: 1180, margin: "0 auto", padding: "28px" };

export function ManagerView() {
  const { schedule, history, error } = useSchedule();
  const [limitInput, setLimitInput] = useState("");
  const [busy, setBusy] = useState(false);

  const applyLimit = async () => {
    const kw = parseFloat(limitInput);
    if (!kw || kw <= 0) return;
    setBusy(true);
    try {
      await api.setBuildingLimit(kw);
      setLimitInput("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <TopBar live />
      <div style={wrap}>
        <SectionTitle eyebrow="Building overview" title="Power Operations" />
        {error && <Banner text={`Backend unreachable - ${error}. Is uvicorn running on :8000?`} />}

        <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 16, marginBottom: 16 }}>
          <div className="panel rise" style={{ padding: 24 }}>
            <p className="eyebrow" style={{ marginBottom: 18 }}>Aggregate load vs. ceiling</p>
            {schedule && (
              <PowerGauge baseLoad={schedule.base_load_kw} charging={schedule.total_assigned_kw} limit={schedule.building_limit_kw} />
            )}
          </div>

          <div className="panel rise" style={{ padding: 24, animationDelay: "0.06s" }}>
            <p className="eyebrow" style={{ marginBottom: 18 }}>Set charging ceiling</p>
            <p style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.5, marginBottom: 16 }}>
              The hard constraint. Charging is re-solved instantly under the new limit -
              the aggregate load can never cross it.
            </p>
            <label>New limit (kW)</label>
            <div style={{ display: "flex", gap: 10 }}>
              <input
                type="number"
                value={limitInput}
                onChange={(e) => setLimitInput(e.target.value)}
                placeholder={schedule ? `${schedule.building_limit_kw}` : "50"}
              />
              <button className="primary" onClick={applyLimit} disabled={busy} style={{ whiteSpace: "nowrap" }}>
                Apply
              </button>
            </div>
          </div>
        </div>

        <div className="panel rise" style={{ padding: 24, marginBottom: 16, animationDelay: "0.1s" }}>
          <p className="eyebrow" style={{ marginBottom: 16 }}>Live power profile</p>
          {schedule && <LoadChart data={history} limit={schedule.building_limit_kw} />}
        </div>

        {schedule && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 16 }}>
            <Kpi label="Active vehicles" value={`${schedule.sessions.length}`} />
            <Kpi label="EV charging" value={`${schedule.total_assigned_kw.toFixed(1)} kW`} accent />
            <Kpi label="Free budget" value={`${(schedule.available_budget_kw - schedule.total_assigned_kw).toFixed(1)} kW`} />
            <Kpi label="Utilization" value={`${((schedule.total_assigned_kw + schedule.base_load_kw) / schedule.building_limit_kw * 100).toFixed(0)}%`} />
          </div>
        )}

        <div className="panel rise" style={{ padding: 24, marginBottom: 16, animationDelay: "0.14s" }}>
          <p className="eyebrow" style={{ marginBottom: 16 }}>Charging sessions</p>
          <SessionTable sessions={schedule?.sessions ?? []} />
        </div>

        <AnalysisPanel />
      </div>
    </>
  );
}

export function SectionTitle({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div style={{ marginBottom: 22 }}>
      <p className="eyebrow">{eyebrow}</p>
      <h1 style={{ fontSize: 32, marginTop: 6 }}>{title}</h1>
    </div>
  );
}

export function Kpi({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="panel rise" style={{ padding: "18px 20px" }}>
      <p className="eyebrow" style={{ fontSize: 9.5 }}>{label}</p>
      <div className="mono" style={{ fontSize: 26, fontWeight: 700, marginTop: 8, color: accent ? "var(--lime)" : "var(--text)" }}>
        {value}
      </div>
    </div>
  );
}

export function Banner({ text }: { text: string }) {
  return (
    <div style={{ padding: "12px 16px", borderRadius: 10, background: "var(--red-soft)", border: "1px solid rgba(255,77,98,0.3)", color: "var(--red)", fontFamily: "var(--font-mono)", fontSize: 12.5, marginBottom: 16 }}>
      {text}
    </div>
  );
}
