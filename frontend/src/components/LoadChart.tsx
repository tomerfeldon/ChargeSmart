// The live power profile: stacked base + charging load over time, with the building
// limit drawn as a red ceiling (Book §5.4 — managed load held below the limit).

import {
  Area,
  ComposedChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface LoadPoint {
  t: string;
  base: number;
  charging: number;
  limit: number;
}

export function LoadChart({ data, limit }: { data: LoadPoint[]; limit: number }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
        <defs>
          <linearGradient id="gCharging" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#b6ff3a" stopOpacity={0.55} />
            <stop offset="100%" stopColor="#b6ff3a" stopOpacity={0.04} />
          </linearGradient>
          <linearGradient id="gBase" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4ad6e0" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#4ad6e0" stopOpacity={0.03} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="t"
          tick={{ fill: "#565c54", fontSize: 10, fontFamily: "JetBrains Mono" }}
          axisLine={{ stroke: "rgba(255,255,255,0.07)" }}
          tickLine={false}
          minTickGap={40}
        />
        <YAxis
          domain={[0, (max: number) => Math.max(max, limit * 1.1)]}
          tick={{ fill: "#565c54", fontSize: 10, fontFamily: "JetBrains Mono" }}
          axisLine={false}
          tickLine={false}
          width={42}
          unit="kW"
        />
        <Tooltip
          contentStyle={{
            background: "#0c0f14",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 10,
            fontFamily: "JetBrains Mono",
            fontSize: 12,
          }}
          labelStyle={{ color: "#8b9088" }}
        />
        <Area
          type="monotone"
          dataKey="base"
          stackId="load"
          stroke="#4ad6e0"
          strokeWidth={1.5}
          fill="url(#gBase)"
          name="Base"
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="charging"
          stackId="load"
          stroke="#b6ff3a"
          strokeWidth={2}
          fill="url(#gCharging)"
          name="Charging"
          isAnimationActive={false}
        />
        <ReferenceLine
          y={limit}
          stroke="#ff4d62"
          strokeDasharray="5 4"
          strokeWidth={1.5}
          label={{ value: `LIMIT ${limit}kW`, fill: "#ff4d62", fontSize: 10, fontFamily: "JetBrains Mono", position: "insideTopRight" }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
