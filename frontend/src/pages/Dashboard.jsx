import { useMemo, useState } from "react";
import { Marker, Popup } from "react-leaflet";
import { DeviceStatusCard } from "../components/common/DeviceStatus";
import { EventList } from "../components/common/EventList";
import { Card, Empty, PageHeader, Spinner, TimeText } from "../components/common/ui";
import { BaseMap, FitBounds, GeofenceLayer, vehicleIcon } from "../components/map/BaseMap";
import { useLive } from "../context/LiveContext";
import { useAsync } from "../hooks/useAsync";
import { useNow } from "../hooks/useNow";
import { api } from "../services/api";
import { formatSpeed } from "../utils/format";
import { connectionStatus } from "../utils/status";

export function Dashboard() {
  const { devices, events, status, receivedAt } = useLive();
  const now = useNow();
  const geofences = useAsync(() => api.geofences().catch(() => []), []);
  const [selected, setSelected] = useState(null);
  const [follow, setFollow] = useState(true);

  const list = useMemo(() => Object.values(devices).sort((a, b) => a.id - b.id), [devices]);
  const located = list.filter((d) => d.state?.latitude != null);
  const focus = selected ? located.filter((d) => d.id === selected) : located;

  return (
    <>
      <PageHeader
        title="En vivo"
        actions={
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
            Seguir vehículo
          </label>
        }
        subtitle={
          receivedAt ? (
            <>
              Última actualización recibida <TimeText iso={new Date(receivedAt).toISOString()} now={now} relative />
            </>
          ) : (
            "Esperando datos del servidor…"
          )
        }
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <BaseMap className="h-[55vh] min-h-[320px]">
            <GeofenceLayer geofences={geofences.data} />
            {located.map((d) => {
              const conn = connectionStatus(d.state, now);
              return (
                <Marker
                  key={d.id}
                  position={[d.state.latitude, d.state.longitude]}
                  icon={vehicleIcon(d.state.course, conn.tone)}
                  eventHandlers={{ click: () => setSelected(d.id) }}
                >
                  <Popup>
                    <strong>{d.name}</strong>
                    <br />
                    {conn.label} · {formatSpeed(d.state.speed)}
                    <br />
                    Posición GPS: <TimeText iso={d.state.fix_time} />
                  </Popup>
                </Marker>
              );
            })}
            <FitBounds
              points={focus.map((d) => [d.state.latitude, d.state.longitude])}
              fitKey={
                follow
                  ? `${selected}-${focus.map((d) => `${d.state.latitude},${d.state.longitude}`).join("|")}`
                  : `${selected}-${located.length}`
              }
            />
          </BaseMap>
        </div>
        <div className="space-y-3">
          {status !== "open" && list.length === 0 && <Spinner label="Conectando con el servidor…" />}
          {status === "open" && list.length === 0 && <Empty>No hay dispositivos registrados.</Empty>}
          {list.map((d) => (
            <DeviceStatusCard
              key={d.id}
              device={d}
              now={now}
              selected={selected === d.id}
              onSelect={(id) => setSelected((cur) => (cur === id ? null : id))}
            />
          ))}
          <Card title="Eventos recientes">
            <EventList events={events.slice(0, 15)} devices={devices} now={now} compact />
          </Card>
        </div>
      </div>
    </>
  );
}
