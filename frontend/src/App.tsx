import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { AssistantPanel } from "./components/AssistantPanel";
import { LoginView } from "./views/LoginView";
import { ResidentView } from "./views/ResidentView";
import { ManagerView } from "./views/ManagerView";
import { DiagnosticsView } from "./views/DiagnosticsView";
import type { Role } from "./types";

// Each role lands on its own view (Book §3.1 — role-specific views).
const HOME: Record<Role, string> = {
  resident: "/resident",
  manager: "/manager",
  technician: "/diagnostics",
};

export default function App() {
  const { role } = useAuth();

  if (!role) return <LoginView />;

  return (
    <>
      <Routes>
        <Route path="/resident" element={role === "resident" ? <ResidentView /> : <Navigate to={HOME[role]} />} />
        <Route path="/manager" element={role === "manager" ? <ManagerView /> : <Navigate to={HOME[role]} />} />
        <Route path="/diagnostics" element={role === "technician" ? <DiagnosticsView /> : <Navigate to={HOME[role]} />} />
        <Route path="*" element={<Navigate to={HOME[role]} />} />
      </Routes>
      {/* Available on every authenticated screen (Book §4.6.6). */}
      <AssistantPanel />
    </>
  );
}
