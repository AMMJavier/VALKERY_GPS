import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, PageHeader, Select, TimeText } from "../components/common/ui";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { useNow } from "../hooks/useNow";
import { api } from "../services/api";
import { connectionStatus } from "../utils/status";

const EMPTY = { imei: "", name: "", model: "FMC920", vehicle_id: "" };

export function Devices() {
  const { can } = useAuth();
  const canEdit = can("devices:manage");
  const now = useNow(5000);
  const devices = useAsync(() => api.devices(), []);
  const vehicles = useAsync(() => api.vehicles(), []);
  const [form, setForm] = useState(EMPTY);
  const [vehicleAlias, setVehicleAlias] = useState("");
  const [error, setError] = useState(null);

  async function create(event) {
    event.preventDefault();
    setError(null);
    try {
      await api.createDevice({ ...form, vehicle_id: form.vehicle_id ? Number(form.vehicle_id) : null });
      setForm(EMPTY);
      devices.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function createVehicle(event) {
    event.preventDefault();
    setError(null);
    try {
      await api.createVehicle({ alias: vehicleAlias });
      setVehicleAlias("");
      vehicles.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function toggle(device) {
    const action = device.enabled ? "deshabilitar" : "habilitar";
    if (device.enabled && !window.confirm(`¿Deshabilitar «${device.name}»? El servidor rechazará sus conexiones.`)) return;
    await api.updateDevice(device.id, { enabled: !device.enabled }).catch((err) => setError(new Error(`No se pudo ${action}: ${err.message}`)));
    devices.reload();
  }

  const vehicleName = Object.fromEntries((vehicles.data ?? []).map((v) => [v.id, v.alias]));

  return (
    <>
      <PageHeader title="Dispositivos" />
      <ErrorBox error={error} />
      <Card className="mt-3">
        {!devices.data?.length ? (
          <Empty>No hay dispositivos.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-500">
                <tr>
                  <th className="py-2">Nombre</th>
                  <th>IMEI</th>
                  <th>Modelo</th>
                  <th>Vehículo</th>
                  <th>Conexión</th>
                  <th>Última comunicación</th>
                  <th>Estado</th>
                  {canEdit && <th />}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {devices.data.map((d) => {
                  const conn = connectionStatus(d.state, now);
                  return (
                    <tr key={d.id}>
                      <td className="py-2 font-medium">{d.name}</td>
                      <td className="font-mono text-xs">{d.imei}</td>
                      <td>{d.model}</td>
                      <td>{vehicleName[d.vehicle_id] ?? "—"}</td>
                      <td>
                        <Badge tone={conn.tone}>{conn.label}</Badge>
                      </td>
                      <td>
                        <TimeText iso={d.state?.last_seen} />
                      </td>
                      <td>
                        <Badge tone={d.enabled ? "green" : "slate"}>{d.enabled ? "habilitado" : "deshabilitado"}</Badge>
                      </td>
                      {canEdit && (
                        <td className="text-right">
                          <Button variant="secondary" onClick={() => toggle(d)}>
                            {d.enabled ? "Deshabilitar" : "Habilitar"}
                          </Button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {canEdit && (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Card title="Registrar dispositivo">
            <form onSubmit={create} className="grid gap-3 sm:grid-cols-2">
              <Field label="IMEI" hint="14 a 17 dígitos">
                <Input value={form.imei} onChange={(e) => setForm({ ...form, imei: e.target.value.trim() })} pattern="\d{14,17}" required />
              </Field>
              <Field label="Nombre">
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
              </Field>
              <Field label="Modelo">
                <Input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
              </Field>
              <Field label="Vehículo">
                <Select value={form.vehicle_id} onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}>
                  <option value="">Sin asignar</option>
                  {(vehicles.data ?? []).map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.alias}
                    </option>
                  ))}
                </Select>
              </Field>
              <div className="sm:col-span-2">
                <Button type="submit">Registrar</Button>
              </div>
            </form>
          </Card>
          <Card title="Nuevo vehículo">
            <form onSubmit={createVehicle} className="flex items-end gap-2">
              <div className="flex-1">
                <Field label="Alias">
                  <Input value={vehicleAlias} onChange={(e) => setVehicleAlias(e.target.value)} required />
                </Field>
              </div>
              <Button type="submit">Crear</Button>
            </form>
          </Card>
        </div>
      )}
    </>
  );
}
