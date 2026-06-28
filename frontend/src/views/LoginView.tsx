import { useState } from "react";
import { useAuth } from "../auth/AuthContext";

const DEMO = [
  { label: "Resident", email: "resident@chargesmart.test", password: "resident123" },
  { label: "Manager", email: "manager@chargesmart.test", password: "manager123" },
  { label: "Technician", email: "tech@chargesmart.test", password: "tech123" },
];

export function LoginView() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch {
      setError("Could not authenticate. Check your credentials.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <div className="rise" style={{ width: "100%", maxWidth: 410 }}>
        <div style={{ textAlign: "center", marginBottom: 30 }}>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: 38, letterSpacing: "-0.03em" }}>
            Charge<span style={{ color: "var(--lime)" }}>Smart</span>
          </div>
          <p className="eyebrow" style={{ marginTop: 8 }}>Smart EV Charging · Grid Control</p>
        </div>

        <form onSubmit={submit} className="panel" style={{ padding: 28 }}>
          <div style={{ marginBottom: 16 }}>
            <label>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@building.test" required />
          </div>
          <div style={{ marginBottom: 22 }}>
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required />
          </div>
          {error && (
            <div style={{ color: "var(--red)", fontFamily: "var(--font-mono)", fontSize: 12, marginBottom: 16 }}>{error}</div>
          )}
          <button type="submit" className="primary" disabled={busy} style={{ width: "100%", padding: 13 }}>
            {busy ? "Authenticating…" : "Enter control room"}
          </button>
        </form>

        <div style={{ marginTop: 22 }}>
          <p className="eyebrow" style={{ marginBottom: 10, textAlign: "center" }}>Demo accounts — click to fill</p>
          <div style={{ display: "flex", gap: 8 }}>
            {DEMO.map((d) => (
              <button
                key={d.label}
                type="button"
                onClick={() => { setEmail(d.email); setPassword(d.password); }}
                style={{ flex: 1, fontSize: 12 }}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
