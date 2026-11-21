import { formatCoords } from "../../utils/format";
import { SEVERITY_TONE, eventLabel } from "../../utils/status";
import { Badge, Empty, TimeText } from "./ui";

export function EventList({ events, devices = {}, now, compact = false }) {
  if (!events?.length) return <Empty>Sin eventos</Empty>;
  return (
    <ul className="divide-y divide-slate-100">
      {events.map((e) => (
        <li key={e.id} className="flex items-start justify-between gap-3 py-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={SEVERITY_TONE[e.severity] ?? "slate"}>{e.severity}</Badge>
              <span className="text-sm font-medium text-slate-800">{eventLabel(e.event_type)}</span>
              {e.attributes?.geofence && <span className="text-xs text-violet-700">«{e.attributes.geofence}»</span>}
            </div>
            {!compact && (
              <p className="mt-0.5 text-xs text-slate-500">
                {devices[e.device_id]?.name ?? `Dispositivo ${e.device_id}`} · origen {e.source === "device" ? "equipo" : "plataforma"}
                {e.attributes?.latitude != null && ` · ${formatCoords(e.attributes.latitude, e.attributes.longitude)}`}
              </p>
            )}
          </div>
          <div className="shrink-0 text-right text-xs text-slate-500">
            <TimeText iso={e.occurred_at} />
            {now && (
              <div>
                <TimeText iso={e.occurred_at} now={now} relative />
              </div>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
