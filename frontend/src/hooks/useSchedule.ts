import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { LoadPoint } from "../components/LoadChart";
import type { ScheduleResponse } from "../types";

const MAX_POINTS = 40;

// Polls /schedule on an interval and accumulates a rolling load history for the chart.
// The backend's in-memory store doesn't tick on its own, so the trace reflects changes
// the user makes (registering vehicles, editing the limit) in real time.
export function useSchedule(intervalMs = 2500) {
  const [schedule, setSchedule] = useState<ScheduleResponse | null>(null);
  const [history, setHistory] = useState<LoadPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      try {
        const data = await api.getSchedule();
        if (cancelled) return;
        setSchedule(data);
        setError(null);
        const point: LoadPoint = {
          t: new Date(data.as_of).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
          base: Number(data.base_load_kw.toFixed(2)),
          charging: Number(data.total_assigned_kw.toFixed(2)),
          limit: data.building_limit_kw,
        };
        setHistory((prev) => [...prev, point].slice(-MAX_POINTS));
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load schedule");
      }
    };

    tick();
    timer.current = window.setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [intervalMs]);

  return { schedule, history, error };
}
