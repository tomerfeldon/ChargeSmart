// The headline safety readout: stacked base + charging load against the hard limit.
// The red marker is the building ceiling the aggregate load must never cross.

export function PowerGauge({
  baseLoad,
  charging,
  limit,
}: {
  baseLoad: number;
  charging: number;
  limit: number;
}) {
  const total = baseLoad + charging;
  const util = limit > 0 ? total / limit : 0;
  const pct = (v: number) => `${Math.min(100, (v / limit) * 100)}%`;
  const danger = util > 0.98;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 14 }}>
        <span className="mono" style={{ fontSize: 46, fontWeight: 700, lineHeight: 1, color: "var(--lime)" }}>
          {total.toFixed(1)}
        </span>
        <span className="mono" style={{ fontSize: 15, color: "var(--text-dim)" }}>/ {limit.toFixed(0)} kW</span>
        <span
          className="mono"
          style={{
            marginLeft: "auto",
            fontSize: 13,
            color: danger ? "var(--red)" : "var(--text-dim)",
          }}
        >
          {(util * 100).toFixed(1)}% utilization
        </span>
      </div>

      {/* The bar */}
      <div
        style={{
          position: "relative",
          height: 30,
          borderRadius: 8,
          background: "var(--panel-2)",
          border: "1px solid var(--border)",
          overflow: "hidden",
        }}
      >
        <div style={{ display: "flex", height: "100%" }}>
          <div
            title={`Base load ${baseLoad.toFixed(1)} kW`}
            style={{ width: pct(baseLoad), background: "var(--cyan)", opacity: 0.5, transition: "width 0.5s ease" }}
          />
          <div
            title={`Charging ${charging.toFixed(1)} kW`}
            style={{
              width: pct(charging),
              background: "var(--lime)",
              boxShadow: "0 0 18px var(--lime)",
              transition: "width 0.5s ease",
            }}
          />
        </div>
        {/* The limit ceiling marker (always at 100% of the track) */}
        <div
          style={{
            position: "absolute",
            right: 0,
            top: -2,
            bottom: -2,
            width: 3,
            background: "var(--red)",
            boxShadow: "0 0 10px var(--red)",
          }}
        />
      </div>

      <div style={{ display: "flex", gap: 18, marginTop: 12 }}>
        <Legend color="var(--cyan)" label="Base load" value={`${baseLoad.toFixed(1)} kW`} dim />
        <Legend color="var(--lime)" label="EV charging" value={`${charging.toFixed(1)} kW`} />
        <Legend color="var(--red)" label="Limit" value={`${limit.toFixed(0)} kW`} />
      </div>
    </div>
  );
}

function Legend({ color, label, value, dim }: { color: string; label: string; value: string; dim?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
      <span style={{ width: 9, height: 9, borderRadius: 2, background: color, opacity: dim ? 0.5 : 1 }} />
      <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{label}</span>
      <span className="mono" style={{ fontSize: 12 }}>{value}</span>
    </div>
  );
}
