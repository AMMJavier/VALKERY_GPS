import { useCallback, useEffect, useMemo, useState } from "react";
import { DeviceStatusCard } from "../components/common/DeviceStatus";
import { VehicleHero } from "../components/common/VehicleHero";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, PageHeader, Select, TimeText } from "../components/common/ui";
import { useLive } from "../context/LiveContext";
import { useAsync } from "../hooks/useAsync";
import { useNow } from "../hooks/useNow";
import { api } from "../services/api";
import { commandStatus } from "../utils/status";

const POLL_MS = 1000;

export function Commands() {
  const { devices } = useLive();
  const now = useNow();
  const types = useAsync(() => api.commandTypes(), []);
  const list = useMemo(() => Object.values(devices).sort((a, b) => a.id - b.id), [devices]);
  const [deviceId, setDeviceId] = useState("");
  const [active, setActive] = useState(null); // comando en seguimiento
  const [blocked, setBlocked] = useState(null); // precondiciones fallidas al solicitar
  const [error, setError] = useState(null);
  const history = useAsync(() => (deviceId ? api.deviceCommands(deviceId) : Promise.resolve([])), [deviceId]);

  useEffect(() => {
    if (!deviceId && list.length) setDeviceId(String(list[0].id));
  }, [list, deviceId]);

  const finished = active && (active.finished_at || ["RECHAZADO", "EXPIRADO", "FALLIDO", "VERIFICADO", "RESULTADO_INCIERTO"].includes(active.status));

  // Seguimiento del comando activo hasta que termine.
  useEffect(() => {
    if (!active || finished) return undefined;
    const timer = setInterval(async () => {
      try {
        setActive(await api.command(active.id));
      } catch (err) {
        setError(err);
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [active, finished]);

  useEffect(() => {
    if (finished) history.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished]);

  const request = useCallback(
    async (type) => {
      setError(null);
      setBlocked(null);
      try {
        setActive(await api.createCommand(deviceId, type));
        history.reload();
      } catch (err) {
        if (err.status === 409 && err.detail?.checks) setBlocked(err.detail);
        else setError(err);
      }
    },
    [deviceId, history],
  );

  const device = devices[deviceId];
  const allTypes = types.data ?? [];
  const relayDisabled = allTypes.find((t) => t.relay && !t.allowed);

  return (
    <>
      <PageHeader
        title="Comandos remotos"
        subtitle="Cada comando queda registrado. Una respuesta del equipo no confirma el relé: solo DOUT1 observado lo verifica."
        actions={
          <div className="w-56">
            <Select value={deviceId} onChange={(e) => { setDeviceId(e.target.value); setActive(null); setBlocked(null); }}>
              {list.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </div>
        }
      />
      {relayDisabled && (
        <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-200">
          {relayDisabled.unavailable_reason}
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="min-w-0 space-y-4">
          {device ? <DeviceStatusCard device={device} now={now} /> : <Empty>Selecciona un dispositivo.</Empty>}
          <Card title="Acciones">
            <div className="space-y-2">
              {allTypes.map((t) => (
                <div key={t.command_type} className="flex items-start justify-between gap-3">
                  <div className="text-sm">
                    <p className="font-medium">{t.label}</p>
                    <p className="text-xs text-slate-500">{t.allowed ? t.description : t.unavailable_reason}</p>
                  </div>
                  <Button
                    variant={t.command_type === "IMMOBILIZE" ? "danger" : t.relay ? "primary" : "secondary"}
                    disabled={!t.allowed || !deviceId || (active && !finished)}
                    onClick={() => request(t.command_type)}
                  >
                    {t.relay ? "Solicitar" : "Enviar"}
                  </Button>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="min-w-0 space-y-4">
          {device && <VehicleHero device={device} now={now} />}
          <ErrorBox error={error} />
          {blocked && <ChecksCard title="No se puede solicitar" message={blocked.message} checks={blocked.checks} />}
          {active && (
            <ActiveCommand
              command={active}
              now={now}
              onChange={(cmd) => { setActive(cmd); history.reload(); }}
              onError={setError}
            />
          )}
          <Card title="Historial de comandos">
            {!history.data?.length ? (
              <Empty>Sin comandos para este equipo.</Empty>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-slate-500">
                    <tr>
                      <th className="py-2">#</th>
                      <th>Comando</th>
                      <th>Estado</th>
                      <th>Solicitado</th>
                      <th>Respuesta</th>
                      <th>Detalle</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {history.data.map((c) => {
                      const st = commandStatus(c);
                      return (
                        <tr key={c.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setActive(c)}>
                          <td className="py-1.5 text-slate-500">{c.id}</td>
                          <td>
                            <span className="font-medium">{c.command_type}</span>{" "}
                            <code className="text-xs text-slate-500">{c.command_text}</code>
                          </td>
                          <td>
                            <Badge tone={st.tone}>{st.label}</Badge>
                          </td>
                          <td className="whitespace-nowrap">
                            <TimeText iso={c.requested_at} />
                          </td>
                          <td className="max-w-[220px] truncate font-mono text-xs" title={c.responses.at(-1)?.response_text}>
                            {c.responses.at(-1)?.response_text ?? "—"}
                          </td>
                          <td className="max-w-[240px] truncate text-xs text-slate-500" title={c.failure_reason ?? ""}>
                            {c.failure_reason ?? ""}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

function ChecksCard({ title, message, checks }) {
  return (
    <Card title={title}>
      {message && <p className="mb-2 text-sm text-red-700">{message}</p>}
      <ul className="space-y-1 text-sm">
        {checks.map((c, i) => (
          <li key={`${c.stage}-${c.name}-${i}`} className="flex items-start gap-2">
            <span className={c.ok ? "text-emerald-600" : "text-red-600"}>{c.ok ? "✔" : "✘"}</span>
            <span className={c.ok ? "text-slate-600" : "font-medium text-red-800"}>{c.detail}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

const TIMELINE = [
  ["requested_at", "Solicitado"],
  ["confirmed_at", "Confirmado"],
  ["sent_at", "Enviado al equipo"],
  ["responded_at", "Respuesta del equipo"],
  ["verified_at", "Verificado por DOUT1"],
  ["finished_at", "Finalizado"],
];

function ActiveCommand({ command, now, onChange, onError }) {
  const [password, setPassword] = useState("");
  const [acknowledge, setAcknowledge] = useState(false);
  const [busy, setBusy] = useState(false);
  const st = commandStatus(command);
  const secondsLeft = Math.max(0, Math.round((Date.parse(command.expires_at) - now) / 1000));
  const awaitingConfirm = command.status === "CREADO";
  const isImmobilize = command.command_type === "IMMOBILIZE";

  async function act(fn) {
    setBusy(true);
    onError(null);
    try {
      onChange(await fn());
    } catch (err) {
      onError(err);
      if (err.status === 409) onChange(await api.command(command.id).catch(() => command));
    } finally {
      setBusy(false);
      setPassword("");
    }
  }

  const lastChecks = command.preconditions.filter((c) => c.stage === command.preconditions.at(-1)?.stage);

  return (
    <Card
      title={`Comando #${command.id}: ${command.command_type}`}
      actions={<Badge tone={st.tone}>{st.label}</Badge>}
    >
      <p className="mb-3 text-sm text-slate-600">
        Texto enviado al equipo: <code className="rounded bg-slate-100 px-1">{command.command_text}</code>
        {command.expected_dout1 != null && <> · DOUT1 esperado: <strong>{command.expected_dout1 ? "1 (activa)" : "0 (inactiva)"}</strong></>}
      </p>

      {awaitingConfirm && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act(() => api.confirmCommand(command.id, password));
          }}
          className={`mb-4 space-y-3 rounded-lg p-3 ring-1 ${isImmobilize ? "bg-red-50 ring-red-200" : "bg-sky-50 ring-sky-200"}`}
        >
          <p className="text-sm font-medium">
            Confirmación requerida · vence en {secondsLeft} s
          </p>
          {isImmobilize && (
            <p className="text-sm text-red-800">
              Inmovilizar corta el encendido. Hazlo solo con la moto detenida y en un lugar seguro. Comprueba que
              sabes desbloquearla también de forma manual.
            </p>
          )}
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={acknowledge} onChange={(e) => setAcknowledge(e.target.checked)} />
            Verifiqué que la moto está detenida y que es seguro ejecutar este comando.
          </label>
          <Field label="Tu contraseña">
            <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" variant={isImmobilize ? "danger" : "primary"} disabled={busy || !acknowledge || !password || secondsLeft === 0}>
              Confirmar y enviar
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => act(() => api.cancelCommand(command.id))}>
              Cancelar
            </Button>
          </div>
        </form>
      )}

      <ol className="space-y-1 text-sm">
        {TIMELINE.map(([key, label]) => (
          <li key={key} className="flex justify-between gap-2">
            <span className={command[key] ? "text-slate-800" : "text-slate-400"}>{label}</span>
            <TimeText iso={command[key]} />
          </li>
        ))}
      </ol>

      {command.responses.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-slate-500">Respuesta del equipo</p>
          {command.responses.map((r, i) => (
            <p key={i} className="font-mono text-xs">
              {r.response_text} <span className="text-slate-500">({r.detail})</span>
            </p>
          ))}
        </div>
      )}
      {command.verification && (
        <p className="mt-2 text-xs text-emerald-700">
          Verificado: DOUT1 = {command.verification.dout1 ? "1 (activa)" : "0 (inactiva)"} en el registro de las <TimeText iso={command.verification.gps_time} />.
        </p>
      )}
      {command.status === "RESULTADO_INCIERTO" && (
        <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-900">
          No hay confirmación del resultado. Verifica el estado físico de la moto antes de asumir nada.
        </p>
      )}
      {command.failure_reason && <p className="mt-2 text-xs text-red-700">{command.failure_reason}</p>}
      {lastChecks.length > 0 && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer text-slate-500">Precondiciones evaluadas ({lastChecks[0].stage})</summary>
          <ul className="mt-1 space-y-0.5">
            {lastChecks.map((c, i) => (
              <li key={i} className={c.ok ? "text-slate-600" : "text-red-700"}>
                {c.ok ? "✔" : "✘"} {c.detail}
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}
