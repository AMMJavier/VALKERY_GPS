// Interpretación del estado de un dispositivo para mostrarlo sin engañar:
// - Conexión según online / reported_offline / last_seen (no según ignition).
// - Posición: hora del último fix válido, que puede ser anterior a la última comunicación.
// - Valores desconocidos (null) se muestran como "Desconocido", nunca como "No".

export const OFFLINE_AFTER_MS = 30 * 60 * 1000;
export const FIX_STALE_MS = 5 * 60 * 1000;

export const TONES = {
  green: "bg-emerald-100 text-emerald-800 ring-emerald-600/20",
  sky: "bg-sky-100 text-sky-800 ring-sky-600/20",
  amber: "bg-amber-100 text-amber-800 ring-amber-600/20",
  red: "bg-red-100 text-red-800 ring-red-600/20",
  slate: "bg-slate-100 text-slate-700 ring-slate-500/20",
};

export function connectionStatus(state, now = Date.now()) {
  if (!state || !state.last_seen) return { key: "never", label: "Sin datos", tone: "slate" };
  if (state.reported_offline) return { key: "offline", label: "Fuera de línea", tone: "red" };
  if (state.online) return { key: "online", label: "Conectado", tone: "green" };
  const age = now - Date.parse(state.last_seen);
  if (age > OFFLINE_AFTER_MS) return { key: "stale", label: "Sin comunicación", tone: "amber" };
  return { key: "idle", label: "Desconectado", tone: "sky" };
}

export function fixStatus(state, now = Date.now()) {
  if (!state || !state.fix_time) return { key: "none", label: "Sin posición", tone: "slate" };
  const age = now - Date.parse(state.fix_time);
  if (state.gnss_status != null && state.gnss_status !== 1) {
    return { key: "lost", label: "Sin señal GPS", tone: "amber" };
  }
  if (age > FIX_STALE_MS) return { key: "old", label: "Posición antigua", tone: "amber" };
  return { key: "ok", label: "GPS OK", tone: "green" };
}

export function boolLabel(value, yes = "Sí", no = "No") {
  if (value == null) return "Desconocido";
  return value ? yes : no;
}

export const SEVERITY_TONE = { info: "sky", warning: "amber", critical: "red" };

export const EVENT_LABELS = {
  IGNITION_ON: "Encendido",
  IGNITION_OFF: "Apagado",
  TOWING: "Remolque",
  CRASH: "Choque",
  JAMMING: "Interferencia (jamming)",
  POWER_CUT: "Corte de alimentación",
  GEOFENCE_ENTER: "Entrada a geocerca",
  GEOFENCE_EXIT: "Salida de geocerca",
  DEVICE_ONLINE: "Equipo en línea",
  DEVICE_OFFLINE: "Equipo fuera de línea",
};

export function eventLabel(type) {
  return EVENT_LABELS[type] ?? type;
}
