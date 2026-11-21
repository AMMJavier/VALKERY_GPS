import { useState } from "react";
import { Navigate } from "react-router";
import { Button, ErrorBox, Field, Input } from "../components/common/ui";
import { useAuth } from "../context/AuthContext";

export function Login() {
  const { token, login, notice } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  if (token) return <Navigate to="/" replace />;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-slate-900 p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-6 shadow-xl">
        <div className="text-center">
          <h1 className="text-2xl font-bold">
            VALKERY <span className="text-sky-600">GPS</span>
          </h1>
          <p className="text-sm text-slate-500">Plataforma de monitoreo</p>
        </div>
        {notice && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{notice}</p>}
        <ErrorBox error={error} />
        <Field label="Usuario">
          <Input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </Field>
        <Field label="Contraseña">
          <Input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        <Button type="submit" className="w-full" disabled={busy || !username || !password}>
          {busy ? "Ingresando…" : "Ingresar"}
        </Button>
      </form>
    </div>
  );
}
