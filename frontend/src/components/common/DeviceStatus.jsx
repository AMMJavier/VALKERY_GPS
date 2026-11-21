import { formatCoords, formatSpeed, formatVoltage } from "../../utils/format";
import { boolLabel, connectionStatus, fixStatus } from "../../utils/status";
import { Badge, TimeText } from "./ui";

/** Tarjeta de estado: separa conexión, última comunicación y última posición válida. */
export function DeviceStatusCard({ device, now, selected, onSelect }) {
  const state = device.state;
  const conn = connectionStatus(state, now);
  const fix = fixStatus(state, now);

  return (
    <button
      type="button"
      onClick={() => onSelect?.(device.id)}
      className={`w-full rounded-xl bg-white p-3 text-left shadow-sm ring-1 transition ${selected ? "ring-2 ring-sky-500" : "ring-slate-200 hover:ring-slate-300"}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-slate-900">{device.name}</p>
          <p className="text-xs text-slate-500">
            {device.model} · IMEI …{device.imei.slice(-4)}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Badge tone={conn.tone}>{conn.label}</Badge>
          <Badge tone={fix.tone}>{fix.label}</Badge>
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <Item label="Última comunicación">
          <TimeText iso={state?.last_seen} now={now} relative />
        </Item>
        <Item label="Última posición (GPS)">
          <TimeText iso={state?.fix_time} now={now} relative />
        </Item>
        <Item label="Contacto">
          <Badge tone={state?.ignition == null ? "slate" : state.ignition ? "green" : "slate"}>
            {boolLabel(state?.ignition, "Encendido", "Apagado")}
          </Badge>
        </Item>
        <Item label="Velocidad">{formatSpeed(state?.speed)}</Item>
        <Item label="Alimentación">{formatVoltage(state?.external_voltage_mv)}</Item>
        <Item label="Señal GSM">{state?.gsm_signal == null ? "—" : `${state.gsm_signal}/5`}</Item>
        <Item label="Salida DOUT1" title="Estado lógico informado por el equipo; no confirma el relé físico">
          {boolLabel(state?.dout1, "Activa", "Inactiva")}
        </Item>
        <Item label="Coordenadas">{formatCoords(state?.latitude, state?.longitude)}</Item>
      </dl>
    </button>
  );
}

function Item({ label, title, children }) {
  return (
    <div title={title}>
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-800">{children}</dd>
    </div>
  );
}
