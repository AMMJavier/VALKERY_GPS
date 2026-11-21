// Cliente HTTP de la API. El token lo fija AuthContext; un 401 cierra la sesión.

const BASE = import.meta.env.VITE_API_URL ?? "";

let token = null;
let onUnauthorized = () => {};

export function setToken(value) {
  token = value;
}

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : formatDetail(detail));
    this.status = status;
    this.detail = detail;
  }
}

function formatDetail(detail) {
  // FastAPI devuelve una lista de errores de validación en 422.
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc ?? []).slice(1).join(".") || "dato"}: ${d.msg}`).join("; ");
  }
  return "Error inesperado";
}

export async function request(path, { method = "GET", body, params, auth = true } = {}) {
  const url = new URL(`${BASE}/api/v1${path}`, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value == null || value === "") continue;
    for (const v of Array.isArray(value) ? value : [value]) url.searchParams.append(key, v);
  }
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "No se pudo conectar con el servidor");
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && auth) onUnauthorized();
    throw new ApiError(response.status, data?.detail ?? `Error ${response.status}`);
  }
  return data;
}

/** Descarga todas las páginas de un recurso paginado (con un tope de seguridad). */
export async function fetchAllPages(path, params, { maxItems = 20000, onProgress } = {}) {
  const items = [];
  let cursor = null;
  do {
    const page = await request(path, { params: { ...params, cursor } });
    items.push(...page.items);
    onProgress?.(items.length);
    cursor = page.next_cursor;
  } while (cursor && items.length < maxItems);
  return { items, truncated: Boolean(cursor) };
}

export const api = {
  login: (username, password) =>
    request("/auth/login", { method: "POST", body: { username, password }, auth: false }),
  me: () => request("/auth/me"),
  changePassword: (current_password, new_password) =>
    request("/auth/change-password", { method: "POST", body: { current_password, new_password } }),

  devices: () => request("/devices"),
  createDevice: (body) => request("/devices", { method: "POST", body }),
  updateDevice: (id, body) => request(`/devices/${id}`, { method: "PATCH", body }),
  vehicles: () => request("/vehicles"),
  createVehicle: (body) => request("/vehicles", { method: "POST", body }),

  events: (params) => request("/events", { params }),
  eventRules: () => request("/event-rules"),
  setEventRule: (body) => request("/event-rules", { method: "PUT", body }),
  deleteEventRule: (id) => request(`/event-rules/${id}`, { method: "DELETE" }),

  geofences: () => request("/geofences"),
  createGeofence: (body) => request("/geofences", { method: "POST", body }),
  updateGeofence: (id, body) => request(`/geofences/${id}`, { method: "PUT", body }),
  deleteGeofence: (id) => request(`/geofences/${id}`, { method: "DELETE" }),

  users: () => request("/users"),
  roles: () => request("/users/roles"),
  createUser: (body) => request("/users", { method: "POST", body }),
  updateUser: (id, body) => request(`/users/${id}`, { method: "PATCH", body }),
  resetPassword: (id, new_password) =>
    request(`/users/${id}/reset-password`, { method: "POST", body: { new_password } }),

  audit: (params) => request("/audit", { params }),
};
