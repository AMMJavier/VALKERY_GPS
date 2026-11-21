import { useState } from "react";
import { Circle, Marker, Polygon, Polyline, useMapEvents } from "react-leaflet";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, PageHeader, Select } from "../components/common/ui";
import { BaseMap, FitBounds, GeofenceLayer, dotIcon } from "../components/map/BaseMap";
import { useAuth } from "../context/AuthContext";
import { useLive } from "../context/LiveContext";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";

function ClickCapture({ onClick }) {
  useMapEvents({ click: (e) => onClick([e.latlng.lat, e.latlng.lng]) });
  return null;
}

const EMPTY = { name: "", type: "circle", center: null, radius: 150, points: [] };

export function Geofences() {
  const { can } = useAuth();
  const { devices } = useLive();
  const canEdit = can("geofences:manage");
  const fences = useAsync(() => api.geofences(), []);
  const [draft, setDraft] = useState(EMPTY);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  function mapClick(point) {
    if (!canEdit) return;
    setDraft((d) => (d.type === "circle" ? { ...d, center: point } : { ...d, points: [...d.points, point] }));
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body =
        draft.type === "circle"
          ? { name: draft.name, geofence_type: "circle", center_lat: draft.center?.[0], center_lon: draft.center?.[1], radius_m: Number(draft.radius) }
          : { name: draft.name, geofence_type: "polygon", points: draft.points };
      await api.createGeofence(body);
      setDraft(EMPTY);
      fences.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(fence) {
    const { id, created_at, updated_at, ...rest } = fence;
    await api.updateGeofence(id, { ...rest, enabled: !fence.enabled }).catch(setError);
    fences.reload();
  }

  async function remove(fence) {
    if (!window.confirm(`¿Eliminar la geocerca «${fence.name}»? Esta acción no se puede deshacer.`)) return;
    await api.deleteGeofence(fence.id).catch(setError);
    fences.reload();
  }

  const ready = draft.name.trim() && (draft.type === "circle" ? draft.center && draft.radius > 0 : draft.points.length >= 3);
  const vehicles = Object.values(devices).filter((d) => d.state?.latitude != null);
  const fitPoints = [
    ...vehicles.map((d) => [d.state.latitude, d.state.longitude]),
    ...(fences.data ?? []).filter((f) => f.center_lat != null).map((f) => [f.center_lat, f.center_lon]),
  ];

  return (
    <>
      <PageHeader title="Geocercas" subtitle="Zonas que generan eventos de entrada y salida" />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <BaseMap className="h-[60vh] min-h-[320px]">
          <GeofenceLayer geofences={fences.data} />
          {vehicles.map((d) => (
            <Marker key={d.id} position={[d.state.latitude, d.state.longitude]} icon={dotIcon("#0284c7")} />
          ))}
          <ClickCapture onClick={mapClick} />
          {draft.type === "circle" && draft.center && (
            <Circle center={draft.center} radius={Number(draft.radius) || 0} pathOptions={{ color: "#0ea5e9", dashArray: "6" }} />
          )}
          {draft.type === "polygon" && draft.points.length > 0 &&
            (draft.points.length >= 3 ? (
              <Polygon positions={draft.points} pathOptions={{ color: "#0ea5e9", dashArray: "6" }} />
            ) : (
              <Polyline positions={draft.points} pathOptions={{ color: "#0ea5e9", dashArray: "6" }} />
            ))}
          <FitBounds points={fitPoints} fitKey={fences.data ? "loaded" : "loading"} />
        </BaseMap>

        <div className="space-y-4">
          {canEdit && (
            <Card title="Nueva geocerca">
              <div className="space-y-3">
                <Field label="Nombre">
                  <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} maxLength={100} />
                </Field>
                <Field label="Forma">
                  <Select value={draft.type} onChange={(e) => setDraft({ ...EMPTY, name: draft.name, type: e.target.value })}>
                    <option value="circle">Círculo</option>
                    <option value="polygon">Polígono</option>
                  </Select>
                </Field>
                {draft.type === "circle" ? (
                  <Field label="Radio (m)" hint="Haz clic en el mapa para fijar el centro.">
                    <Input type="number" min={10} max={100000} value={draft.radius} onChange={(e) => setDraft({ ...draft, radius: e.target.value })} />
                  </Field>
                ) : (
                  <p className="text-xs text-slate-500">
                    Haz clic en el mapa para agregar vértices ({draft.points.length}; mínimo 3).{" "}
                    {draft.points.length > 0 && (
                      <button className="text-sky-700 underline" onClick={() => setDraft({ ...draft, points: draft.points.slice(0, -1) })}>
                        Deshacer último
                      </button>
                    )}
                  </p>
                )}
                <ErrorBox error={error} />
                <div className="flex gap-2">
                  <Button onClick={save} disabled={!ready || busy}>
                    Guardar
                  </Button>
                  <Button variant="secondary" onClick={() => setDraft(EMPTY)}>
                    Limpiar
                  </Button>
                </div>
              </div>
            </Card>
          )}
          <Card title="Geocercas">
            {!fences.data?.length ? (
              <Empty>No hay geocercas.</Empty>
            ) : (
              <ul className="divide-y divide-slate-100">
                {fences.data.map((f) => (
                  <li key={f.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                    <div>
                      <p className="font-medium">{f.name}</p>
                      <p className="text-xs text-slate-500">
                        {f.geofence_type === "circle" ? `Círculo de ${f.radius_m} m` : `Polígono de ${f.points.length} vértices`}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={f.enabled ? "green" : "slate"}>{f.enabled ? "activa" : "inactiva"}</Badge>
                      {canEdit && (
                        <>
                          <Button variant="secondary" onClick={() => toggle(f)}>
                            {f.enabled ? "Desactivar" : "Activar"}
                          </Button>
                          <Button variant="danger" onClick={() => remove(f)}>
                            Eliminar
                          </Button>
                        </>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
