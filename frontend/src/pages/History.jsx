import { useEffect, useMemo, useState } from "react";
import { CircleMarker, Marker, Polyline, Popup } from "react-leaflet";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, PageHeader, Select, Spinner, TimeText } from "../components/common/ui";
import { BaseMap, FitBounds, GeofenceLayer, dotIcon, vehicleIcon } from "../components/map/BaseMap";
import { useAsync } from "../hooks/useAsync";
import { api, fetchAllPages } from "../services/api";
import {
  formatCoords,
  formatDistance,
  formatDuration,
  formatSpeed,
  formatVoltage,
  localInputToIso,
  toLocalInput,
} from "../utils/format";
import { trackSummary } from "../utils/geo";
import { boolLabel } from "../utils/status";

const MAX_POINTS = 20000;

function defaultRange() {
  const to = new Date();
  const from = new Date(to.getTime() - 24 * 3600 * 1000);
  return { from: toLocalInput(from), to: toLocalInput(new Date(to.getTime() + 60_000)) };
}

export function History() {
  const devices = useAsync(() => api.devices(), []);
  const geofences = useAsync(() => api.geofences().catch(() => []), []);
  const [deviceId, setDeviceId] = useState("");
  const [range, setRange] = useState(defaultRange);
  const [validOnly, setValidOnly] = useState(true);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(null);
  const [error, setError] = useState(null);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    if (!deviceId && devices.data?.length) setDeviceId(String(devices.data[0].id));
  }, [devices.data, deviceId]);

  async function load(event) {
    event?.preventDefault();
    setError(null);
    const from = localInputToIso(range.from);
    const to = localInputToIso(range.to);
    if (!from || !to || Date.parse(to) <= Date.parse(from)) {
      setError(new Error("El rango de fechas no es válido"));
      return;
    }
    setLoading(0);
    try {
      const data = await fetchAllPages(
        `/devices/${deviceId}/positions`,
        { from, to, limit: 1000, valid_only: validOnly },
        { maxItems: MAX_POINTS, onProgress: setLoading },
      );
      setResult({ ...data, from, to });
      setCursor(Math.max(data.items.length - 1, 0));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(null);
    }
  }

  const positions = result?.items ?? [];
  const summary = useMemo(() => trackSummary(positions), [positions]);
  const line = useMemo(() => positions.filter((p) => p.valid).map((p) => [p.latitude, p.longitude]), [positions]);
  const current = positions[cursor];

  return (
    <>
      <PageHeader title="Historial" subtitle="Recorridos por rango de fechas (hora local del navegador)" />
      <Card className="mb-4">
        <form onSubmit={load} className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(180px,1.2fr)_1fr_1fr_auto_auto]">
          <Field label="Dispositivo">
            <Select value={deviceId} onChange={(e) => setDeviceId(e.target.value)} required>
              {(devices.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Desde">
            <Input type="datetime-local" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} required />
          </Field>
          <Field label="Hasta">
            <Input type="datetime-local" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} required />
          </Field>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input type="checkbox" checked={validOnly} onChange={(e) => setValidOnly(e.target.checked)} />
            Solo con GPS válido
          </label>
          <Button type="submit" disabled={!deviceId || loading != null}>
            Consultar
          </Button>
        </form>
        <div className="mt-3">
          <ErrorBox error={error} />
          {loading != null && <Spinner label={`Cargando posiciones… ${loading}`} />}
        </div>
      </Card>

      {result && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-3">
            <BaseMap className="h-[55vh] min-h-[320px]">
              <GeofenceLayer geofences={geofences.data} />
              {line.length > 1 && <Polyline positions={line} pathOptions={{ color: "#0284c7", weight: 4 }} />}
              {positions
                .filter((p) => !p.valid)
                .map((p) => (
                  <CircleMarker key={p.id} center={[p.latitude, p.longitude]} radius={3} pathOptions={{ color: "#d97706" }} />
                ))}
              {line.length > 0 && <Marker position={line[0]} icon={dotIcon("#059669")} />}
              {line.length > 1 && <Marker position={line[line.length - 1]} icon={dotIcon("#dc2626")} />}
              {current && (
                <Marker position={[current.latitude, current.longitude]} icon={vehicleIcon(current.course, current.valid ? "sky" : "amber")}>
                  <Popup>
                    <TimeText iso={current.gps_time} />
                  </Popup>
                </Marker>
              )}
              <FitBounds points={line} fitKey={`${result.from}-${result.to}-${positions.length}`} />
            </BaseMap>
            {positions.length > 0 && (
              <Card title="Reproducción">
                <input
                  type="range"
                  min={0}
                  max={positions.length - 1}
                  value={cursor}
                  onChange={(e) => setCursor(Number(e.target.value))}
                  className="w-full"
                  aria-label="Posición del recorrido"
                />
                {current && (
                  <dl className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                    <Stat label="Hora GPS"><TimeText iso={current.gps_time} /></Stat>
                    <Stat label="Recibido"><TimeText iso={current.received_at} /></Stat>
                    <Stat label="Velocidad">{formatSpeed(current.speed)}</Stat>
                    <Stat label="GPS">{current.valid ? <Badge tone="green">válido</Badge> : <Badge tone="amber">sin fix</Badge>}</Stat>
                    <Stat label="Contacto">{boolLabel(current.ignition, "Encendido", "Apagado")}</Stat>
                    <Stat label="Alimentación">{formatVoltage(current.external_voltage_mv)}</Stat>
                    <Stat label="Satélites">{current.satellites}</Stat>
                    <Stat label="Coordenadas">{formatCoords(current.latitude, current.longitude)}</Stat>
                  </dl>
                )}
              </Card>
            )}
          </div>
          <Card title="Resumen">
            {positions.length === 0 ? (
              <Empty>No hay posiciones en ese rango.</Empty>
            ) : (
              <dl className="space-y-2 text-sm">
                <Stat label="Posiciones">{summary.points} ({summary.validPoints} con GPS válido)</Stat>
                <Stat label="Distancia estimada">{formatDistance(summary.distanceM)}</Stat>
                <Stat label="Velocidad máxima">{formatSpeed(summary.maxSpeed)}</Stat>
                <Stat label="Duración">{formatDuration(summary.durationMs)}</Stat>
                <Stat label="Primera"><TimeText iso={positions[0].gps_time} /></Stat>
                <Stat label="Última"><TimeText iso={positions[positions.length - 1].gps_time} /></Stat>
                {result.truncated && (
                  <p className="rounded bg-amber-50 p-2 text-xs text-amber-800">
                    Se muestran las primeras {MAX_POINTS} posiciones; acorta el rango para ver el resto.
                  </p>
                )}
                <p className="text-xs text-slate-500">La distancia se estima con las posiciones válidas consecutivas.</p>
              </dl>
            )}
          </Card>
        </div>
      )}
    </>
  );
}

function Stat({ label, children }) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-800">{children}</dd>
    </div>
  );
}
