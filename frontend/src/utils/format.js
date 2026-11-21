// Formato de fechas, magnitudes y tiempos relativos.
// Todas las fechas de la API vienen en ISO 8601 con zona (UTC); se muestran en la
// zona horaria del navegador, y el valor UTC exacto queda en el atributo title.

const dateTimeFormat = new Intl.DateTimeFormat("es", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export function parseDate(iso) {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : new Date(ms);
}

export function formatDateTime(iso) {
  const date = parseDate(iso);
  return date ? dateTimeFormat.format(date) : "—";
}

export function formatUtc(iso) {
  const date = parseDate(iso);
  return date ? `${date.toISOString().replace("T", " ").slice(0, 19)} UTC` : "";
}

/** "hace 5 s", "hace 3 min", "hace 2 h", "hace 4 d"; "en el futuro" si el reloj del equipo va adelantado. */
export function formatRelative(iso, now = Date.now()) {
  const date = parseDate(iso);
  if (!date) return "nunca";
  const seconds = Math.round((now - date.getTime()) / 1000);
  if (seconds < -60) return "en el futuro (reloj adelantado)";
  if (seconds < 5) return "ahora";
  if (seconds < 60) return `hace ${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `hace ${hours} h`;
  return `hace ${Math.floor(hours / 24)} d`;
}

export function formatDuration(ms) {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const total = Math.round(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h} h ${m} min`;
  if (m) return `${m} min ${s} s`;
  return `${s} s`;
}

const decimal = new Intl.NumberFormat("es", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const integer = new Intl.NumberFormat("es", { maximumFractionDigits: 0 });

export function formatVoltage(mv) {
  return mv == null ? "—" : `${decimal.format(mv / 1000)} V`;
}

export function formatSpeed(kmh) {
  return kmh == null ? "—" : `${integer.format(kmh)} km/h`;
}

export function formatDistance(meters) {
  if (meters == null) return "—";
  return meters < 1000 ? `${integer.format(meters)} m` : `${decimal.format(meters / 1000)} km`;
}

export function formatCoords(lat, lon) {
  return lat == null || lon == null ? "—" : `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
}

/** Valor de <input type="datetime-local"> (hora local) → ISO UTC para la API. */
export function localInputToIso(value) {
  if (!value) return null;
  const date = new Date(value); // se interpreta en la zona del navegador
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** Date → valor para <input type="datetime-local"> en hora local. */
export function toLocalInput(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}
