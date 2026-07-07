import { useState } from "react";
import { api } from "../api/client";
import { PowerGauge } from "../components/PowerGauge";
import { TopBar } from "../components/TopBar";
import { Banner, SectionTitle } from "./ManagerView";
import { useSchedule } from "../hooks/useSchedule";
import type { SessionRead } from "../types";

const wrap: React.CSSProperties = { maxWidth: 1180, margin: "0 auto", padding: "28px" };

// Default departure: 6 hours from now, formatted for <input type="datetime-local">.
function defaultDeparture(): string {
  const d = new Date(Date.now() + 6 * 3600 * 1000);
  d.setSeconds(0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function ResidentView() {
  const { schedule, error } = useSchedule(2500);
  const [form, setForm] = useState({
    charger_id: 1,
    license_plate: "",
    battery_capacity_kwh: 60,
    max_charge_rate_kw: 11,
    current_soc: 40,
    target_soc: 80,
    departure: defaultDeparture(),
  });
  const [created, setCreated] = useState<SessionRead | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const set = (k: keyof typeof form, v: string | number) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const session = await api.createSession({
        charger_id: Number(form.charger_id),
        license_plate: form.license_plate,
        battery_capacity_kwh: Number(form.battery_capacity_kwh),
        max_charge_rate_kw: Number(form.max_charge_rate_kw),
        current_soc: Number(form.current_soc),
        target_soc: Number(form.target_soc),
        departure_time: new Date(form.departure).toISOString(),
      });
      setCreated(session);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Could not register vehicle.");
    } finally {
      setBusy(false);
    }
  };

  const ready = created?.projected_completion_time
    ? new Date(created.projected_completion_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "-";

  return (
    <>
      <TopBar live />
      <div style={wrap}>
        <SectionTitle eyebrow="My vehicle" title="Connect to Charge" />
        {error && <Banner text={`Backend unreachable - ${error}.`} />}

        <div style={{ display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: 16 }}>
          <form onSubmit={submit} className="panel rise" style={{ padding: 26 }}>
            <p className="eyebrow" style={{ marginBottom: 18 }}>Vehicle parameters</p>

            <Field label="License plate">
              <input value={form.license_plate} onChange={(e) => set("license_plate", e.target.value)} placeholder="12-345-67" required />
            </Field>

            <Row>
              <Field label="Charger #"><input type="number" min={1} value={form.charger_id} onChange={(e) => set("charger_id", e.target.value)} /></Field>
              <Field label="Battery (kWh)"><input type="number" value={form.battery_capacity_kwh} onChange={(e) => set("battery_capacity_kwh", e.target.value)} /></Field>
            </Row>

            <Row>
              <Field label="Current SoC %"><input type="number" min={0} max={100} value={form.current_soc} onChange={(e) => set("current_soc", e.target.value)} /></Field>
              <Field label="Target SoC %"><input type="number" min={0} max={100} value={form.target_soc} onChange={(e) => set("target_soc", e.target.value)} /></Field>
            </Row>

            <Row>
              <Field label="Max rate (kW)"><input type="number" value={form.max_charge_rate_kw} onChange={(e) => set("max_charge_rate_kw", e.target.value)} /></Field>
              <Field label="Departure"><input type="datetime-local" value={form.departure} onChange={(e) => set("departure", e.target.value)} /></Field>
            </Row>

            {msg && <div style={{ color: "var(--red)", fontFamily: "var(--font-mono)", fontSize: 12, marginBottom: 14 }}>{msg}</div>}
            <button type="submit" className="primary" disabled={busy} style={{ width: "100%", padding: 13, marginTop: 6 }}>
              {busy ? "Computing schedule…" : "Plug in & schedule"}
            </button>
          </form>

          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="panel rise" style={{ padding: 24, animationDelay: "0.06s" }}>
              <p className="eyebrow" style={{ marginBottom: 14 }}>Your charging plan</p>
              {created ? (
                <>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                    <span className="mono" style={{ fontSize: 40, fontWeight: 700, color: "var(--lime)" }}>{created.assigned_power_kw.toFixed(1)}</span>
                    <span className="mono" style={{ color: "var(--text-dim)" }}>kW assigned</span>
                  </div>
                  <div style={{ marginTop: 16, display: "flex", gap: 26 }}>
                    <Readout label="Status" value={created.status} />
                    <Readout label="Ready by" value={ready} />
                    <Readout label="Session" value={`#${created.session_id}`} />
                  </div>
                </>
              ) : (
                <p style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
                  Register your vehicle to receive a power allocation.
                </p>
              )}
            </div>

            <div className="panel rise" style={{ padding: 24, animationDelay: "0.1s" }}>
              <p className="eyebrow" style={{ marginBottom: 16 }}>Building load right now</p>
              {schedule && <PowerGauge baseLoad={schedule.base_load_kw} charging={schedule.total_assigned_kw} limit={schedule.building_limit_kw} />}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div style={{ marginBottom: 16, flex: 1 }}><label>{label}</label>{children}</div>;
}
function Row({ children }: { children: React.ReactNode }) {
  return <div style={{ display: "flex", gap: 12 }}>{children}</div>;
}
function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="eyebrow" style={{ fontSize: 9.5 }}>{label}</p>
      <div className="mono" style={{ fontSize: 15, marginTop: 5, textTransform: "capitalize" }}>{value}</div>
    </div>
  );
}
