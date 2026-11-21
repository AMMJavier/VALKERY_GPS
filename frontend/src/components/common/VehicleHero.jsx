import motoImage from "../../assets/moto.webp";
import { formatSpeed, formatVoltage } from "../../utils/format";
import { boolLabel, connectionStatus } from "../../utils/status";
import { Badge, TimeText } from "./ui";

/** Foto del vehículo con el estado relevante para los comandos (conexión, contacto, relé). */
export function VehicleHero({ device, now }) {
  const state = device?.state;
  const conn = connectionStatus(state, now);
  const immobilized = state?.dout1 === true;

  return (
    <section className="grid overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-200 xl:grid-cols-[minmax(240px,380px)_minmax(0,1fr)]">
      {/* La foto trae mucho margen blanco: se amplía dentro de un marco 4:3 para que la moto lo llene. */}
      <div className="relative mx-auto aspect-[3/2] w-full max-w-[520px] overflow-hidden bg-white xl:aspect-[4/3] xl:max-w-none">
        <img
          src={motoImage}
          alt={device ? `Moto de ${device.name}` : "Moto"}
          className={`h-full w-full scale-[1.15] object-cover object-[center_57%] transition xl:scale-125 ${immobilized ? "grayscale-[60%]" : ""}`}
          loading="lazy"
        />
        {immobilized && (
          <span className="absolute bottom-3 left-3 rounded-md bg-red-600 px-2.5 py-1 text-xs font-semibold text-white shadow">
            🔒 Inmovilizada
          </span>
        )}
      </div>

      <div className="flex flex-col justify-between gap-4 border-t border-slate-100 p-4 xl:border-t-0 xl:border-l">
        <div>
          <div className="flex flex-wrap gap-1.5">
            <Badge tone={conn.tone}>● {conn.label}</Badge>
            {state?.dout1 == null ? (
              <Badge tone="slate">Relé: desconocido</Badge>
            ) : immobilized ? (
              <Badge tone="red">DOUT1 activa · relé de corte activado</Badge>
            ) : (
              <Badge tone="green">DOUT1 inactiva · relé libre</Badge>
            )}
          </div>
          <p className="mt-3 text-xl font-semibold text-slate-900">{device?.name ?? "—"}</p>
          <p className="text-sm text-slate-500">
            {device?.model} · Última comunicación <TimeText iso={state?.last_seen} now={now} relative />
          </p>
        </div>

        <dl className="grid grid-cols-3 gap-3 text-sm">
          <Stat label="Contacto">{boolLabel(state?.ignition, "Encendido", "Apagado")}</Stat>
          <Stat label="Velocidad">{formatSpeed(state?.speed)}</Stat>
          <Stat label="Batería moto">{formatVoltage(state?.external_voltage_mv)}</Stat>
        </dl>
        <p className="text-xs text-slate-400">
          DOUT1 es lo que informa el equipo; no confirma por sí solo el estado físico del relé.
        </p>
      </div>
    </section>
  );
}

function Stat({ label, children }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="font-semibold text-slate-800">{children}</dd>
    </div>
  );
}
