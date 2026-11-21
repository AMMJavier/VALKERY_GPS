import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { useAuth } from "../../context/AuthContext";
import { useLive } from "../../context/LiveContext";
import { Badge } from "../common/ui";

const LINKS = [
  { to: "/", label: "En vivo", end: true },
  { to: "/historial", label: "Historial", perm: "positions:read" },
  { to: "/eventos", label: "Eventos", perm: "events:read" },
  { to: "/geocercas", label: "Geocercas", perm: "devices:read" },
  { to: "/reglas", label: "Reglas", perm: "events:read" },
  { to: "/dispositivos", label: "Dispositivos", perm: "devices:read" },
  { to: "/usuarios", label: "Usuarios", perm: "users:manage" },
  { to: "/auditoria", label: "Auditoría", perm: "audit:read" },
];

const LIVE_STATUS = {
  open: { tone: "green", label: "En vivo" },
  connecting: { tone: "sky", label: "Conectando…" },
  reconnecting: { tone: "amber", label: "Reconectando…" },
  unauthorized: { tone: "red", label: "Sesión inválida" },
  closed: { tone: "slate", label: "Desconectado" },
};

export function Shell() {
  const { user, can, logout } = useAuth();
  const { status } = useLive();
  const [open, setOpen] = useState(false);
  const live = LIVE_STATUS[status] ?? LIVE_STATUS.closed;

  const links = LINKS.filter((l) => !l.perm || can(l.perm));
  const linkClass = ({ isActive }) =>
    `block rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-slate-800 text-white" : "text-slate-300 hover:bg-slate-800/60 hover:text-white"}`;

  return (
    <div className="flex h-full flex-col md:flex-row">
      <aside className="bg-slate-900 text-white md:flex md:w-56 md:flex-col">
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-lg font-bold tracking-wide">
            VALKERY <span className="text-sky-400">GPS</span>
          </span>
          <button className="rounded p-1 md:hidden" onClick={() => setOpen((v) => !v)} aria-label="Menú">
            ☰
          </button>
        </div>
        <nav className={`${open ? "block" : "hidden"} space-y-1 px-2 pb-3 md:block md:flex-1`}>
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end} className={linkClass} onClick={() => setOpen(false)}>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className={`${open ? "block" : "hidden"} border-t border-slate-800 px-4 py-3 text-xs md:block`}>
          <div className="mb-2">
            <Badge tone={live.tone}>● {live.label}</Badge>
          </div>
          <NavLink to="/cuenta" className="block truncate text-slate-300 hover:text-white">
            {user?.full_name || user?.username}
          </NavLink>
          <button className="mt-1 text-slate-400 hover:text-white" onClick={() => logout()}>
            Cerrar sesión
          </button>
        </div>
      </aside>
      <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  );
}
