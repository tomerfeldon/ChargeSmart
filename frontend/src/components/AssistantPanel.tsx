// Read-only conversational assistant (Book §4.6.6), available on every screen.
// Posts natural-language questions to /assistant and renders the answers. It can only
// read system state — it never changes the schedule.

import { useRef, useState } from "react";
import { api } from "../api/client";

interface Msg {
  role: "user" | "assistant";
  text: string;
}

const SUGGESTIONS = [
  "Is the building under safe load?",
  "How much free charging budget is left?",
  "Which vehicle will be ready first?",
];

export function AssistantPanel() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setBusy(true);
    try {
      const { answer } = await api.askAssistant(q);
      setMessages((m) => [...m, { role: "assistant", text: answer }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: e instanceof Error ? e.message : "Request failed." }]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight));
    }
  };

  return (
    <>
      {/* Launcher */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Toggle assistant"
        style={{
          position: "fixed", right: 24, bottom: 24, zIndex: 50,
          width: 56, height: 56, borderRadius: "50%", padding: 0,
          background: "var(--lime)", color: "#0a0d04", border: "none",
          boxShadow: "0 0 0 5px var(--lime-soft), 0 8px 24px rgba(0,0,0,0.4)",
          display: "grid", placeItems: "center", fontSize: 22,
        }}
      >
        {open ? "×" : "✦"}
      </button>

      {open && (
        <div
          className="panel rise"
          style={{
            position: "fixed", right: 24, bottom: 92, zIndex: 50,
            width: 360, maxWidth: "calc(100vw - 48px)", height: 460,
            display: "flex", flexDirection: "column", overflow: "hidden",
            boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
          }}
        >
          <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="live-dot" />
              <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 15 }}>Assistant</span>
            </div>
            <p style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 4, fontFamily: "var(--font-mono)" }}>
              Read-only · answers from live state
            </p>
          </div>

          <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            {messages.length === 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <p style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.5 }}>
                  Ask about charging status, building load, or completion times.
                </p>
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)} style={{ textAlign: "left", fontSize: 12, padding: "8px 11px" }}>
                    {s}
                  </button>
                ))}
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                style={{
                  alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "85%",
                  padding: "9px 12px",
                  borderRadius: 11,
                  fontSize: 13,
                  lineHeight: 1.45,
                  background: m.role === "user" ? "var(--lime)" : "var(--panel-2)",
                  color: m.role === "user" ? "#0a0d04" : "var(--text)",
                  border: m.role === "user" ? "none" : "1px solid var(--border)",
                  whiteSpace: "pre-wrap",
                }}
              >
                {m.text}
              </div>
            ))}
            {busy && <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-faint)" }}>thinking…</div>}
          </div>

          <form
            onSubmit={(e) => { e.preventDefault(); send(input); }}
            style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid var(--border)" }}
          >
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask something…" style={{ fontSize: 13 }} />
            <button type="submit" className="primary" disabled={busy || !input.trim()}>↑</button>
          </form>
        </div>
      )}
    </>
  );
}
