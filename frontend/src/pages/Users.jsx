import { useState } from "react";
import { Badge, Button, Card, ErrorBox, Field, Input, PageHeader, Select, TimeText } from "../components/common/ui";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";

const EMPTY = { username: "", full_name: "", password: "", role: "viewer" };

export function Users() {
  const { user: me } = useAuth();
  const users = useAsync(() => api.users(), []);
  const roles = useAsync(() => api.roles(), []);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  async function run(action, success) {
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(success);
      users.reload();
      return true;
    } catch (err) {
      setError(err);
      return false;
    }
  }

  async function create(event) {
    event.preventDefault();
    const ok = await run(
      () => api.createUser({ username: form.username, full_name: form.full_name, password: form.password, roles: [form.role] }),
      `Usuario ${form.username} creado`,
    );
    if (ok) setForm(EMPTY);
  }

  function resetPassword(user) {
    const value = window.prompt(`Nueva contraseña para ${user.username} (mínimo 10 caracteres):`);
    if (value) run(() => api.resetPassword(user.id, value), "Contraseña cambiada; sus sesiones se cerraron");
  }

  return (
    <>
      <PageHeader title="Usuarios" subtitle="Cambiar roles o deshabilitar cierra las sesiones abiertas del usuario" />
      <div className="space-y-3">
        <ErrorBox error={error} />
        {message && <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{message}</p>}
      </div>
      <Card className="mt-3">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-500">
              <tr>
                <th className="py-2">Usuario</th>
                <th>Rol</th>
                <th>Estado</th>
                <th>Último acceso</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(users.data ?? []).map((u) => (
                <tr key={u.id}>
                  <td className="py-2">
                    <p className="font-medium">{u.username}</p>
                    <p className="text-xs text-slate-500">{u.full_name}</p>
                  </td>
                  <td className="max-w-[160px]">
                    <Select
                      value={u.roles[0] ?? ""}
                      onChange={(e) => run(() => api.updateUser(u.id, { roles: [e.target.value] }), `Rol de ${u.username} actualizado`)}
                    >
                      {(roles.data ?? []).map((r) => (
                        <option key={r.id} value={r.name}>
                          {r.name}
                        </option>
                      ))}
                    </Select>
                  </td>
                  <td>
                    <Badge tone={u.enabled ? "green" : "slate"}>{u.enabled ? "activo" : "deshabilitado"}</Badge>
                  </td>
                  <td>
                    <TimeText iso={u.last_login_at} />
                  </td>
                  <td className="space-x-2 text-right whitespace-nowrap">
                    <Button variant="secondary" onClick={() => resetPassword(u)}>
                      Cambiar contraseña
                    </Button>
                    {u.id !== me?.id && (
                      <Button
                        variant={u.enabled ? "danger" : "secondary"}
                        onClick={() => run(() => api.updateUser(u.id, { enabled: !u.enabled }), `Usuario ${u.username} ${u.enabled ? "deshabilitado" : "habilitado"}`)}
                      >
                        {u.enabled ? "Deshabilitar" : "Habilitar"}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="Nuevo usuario" className="mt-4">
        <form onSubmit={create} className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Usuario">
            <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} pattern="[a-zA-Z0-9_.\-]{3,50}" required />
          </Field>
          <Field label="Nombre">
            <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </Field>
          <Field label="Contraseña" hint="Mínimo 10 caracteres">
            <Input type="password" autoComplete="new-password" minLength={10} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
          </Field>
          <Field label="Rol">
            <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {(roles.data ?? []).map((r) => (
                <option key={r.id} value={r.name} title={r.description}>
                  {r.name}
                </option>
              ))}
            </Select>
          </Field>
          <Button type="submit">Crear</Button>
        </form>
      </Card>
    </>
  );
}
