import { useState } from "react";
import { Badge, Button, Card, ErrorBox, Field, Input, PageHeader, TimeText } from "../components/common/ui";
import { useAuth } from "../context/AuthContext";
import { api } from "../services/api";

export function Account() {
  const { user, expiresAt, logout } = useAuth();
  const [form, setForm] = useState({ current: "", next: "", repeat: "" });
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setError(null);
    if (form.next !== form.repeat) {
      setError(new Error("Las contraseñas nuevas no coinciden"));
      return;
    }
    try {
      await api.changePassword(form.current, form.next);
      logout("Contraseña cambiada. Inicia sesión con la nueva contraseña.");
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <PageHeader title="Mi cuenta" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Datos">
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-slate-500">Usuario</dt>
              <dd className="font-medium">{user?.username}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Roles</dt>
              <dd className="flex gap-1">{user?.roles.map((r) => <Badge key={r}>{r}</Badge>)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">La sesión expira</dt>
              <dd>
                <TimeText iso={expiresAt} />
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Permisos</dt>
              <dd className="flex flex-wrap gap-1">{user?.permissions.map((p) => <Badge key={p} tone="sky">{p}</Badge>)}</dd>
            </div>
          </dl>
        </Card>
        <Card title="Cambiar contraseña">
          <form onSubmit={submit} className="space-y-3">
            <Field label="Contraseña actual">
              <Input type="password" autoComplete="current-password" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} required />
            </Field>
            <Field label="Nueva contraseña" hint="Mínimo 10 caracteres. Se cerrarán todas tus sesiones.">
              <Input type="password" autoComplete="new-password" minLength={10} value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} required />
            </Field>
            <Field label="Repite la nueva contraseña">
              <Input type="password" autoComplete="new-password" minLength={10} value={form.repeat} onChange={(e) => setForm({ ...form, repeat: e.target.value })} required />
            </Field>
            <ErrorBox error={error} />
            <Button type="submit">Cambiar</Button>
          </form>
        </Card>
      </div>
    </>
  );
}
