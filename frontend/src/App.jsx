import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { Shell } from "./components/layout/Shell";
import { Spinner } from "./components/common/ui";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { LiveProvider } from "./context/LiveContext";
import { Account } from "./pages/Account";
import { Audit } from "./pages/Audit";
import { Commands } from "./pages/Commands";
import { Dashboard } from "./pages/Dashboard";
import { Devices } from "./pages/Devices";
import { Events } from "./pages/Events";
import { Geofences } from "./pages/Geofences";
import { History } from "./pages/History";
import { Login } from "./pages/Login";
import { Rules } from "./pages/Rules";
import { Users } from "./pages/Users";

function Protected() {
  const { token, user } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  if (!user) {
    return (
      <div className="p-6">
        <Spinner />
      </div>
    );
  }
  return (
    <LiveProvider>
      <Shell />
    </LiveProvider>
  );
}

/** Oculta la página si falta el permiso (la API lo vuelve a comprobar). */
function RequirePermission({ perm, children }) {
  const { can } = useAuth();
  return can(perm) ? children : <p className="text-sm text-slate-500">No tienes permiso para ver esta sección.</p>;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Protected />}>
            <Route index element={<Dashboard />} />
            <Route path="historial" element={<RequirePermission perm="positions:read"><History /></RequirePermission>} />
            <Route path="eventos" element={<RequirePermission perm="events:read"><Events /></RequirePermission>} />
            <Route path="geocercas" element={<RequirePermission perm="devices:read"><Geofences /></RequirePermission>} />
            <Route path="reglas" element={<RequirePermission perm="events:read"><Rules /></RequirePermission>} />
            <Route path="comandos" element={<RequirePermission perm="commands:send"><Commands /></RequirePermission>} />
            <Route path="dispositivos" element={<RequirePermission perm="devices:read"><Devices /></RequirePermission>} />
            <Route path="usuarios" element={<RequirePermission perm="users:manage"><Users /></RequirePermission>} />
            <Route path="auditoria" element={<RequirePermission perm="audit:read"><Audit /></RequirePermission>} />
            <Route path="cuenta" element={<Account />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
