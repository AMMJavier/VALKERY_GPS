import L from "leaflet";
import { useEffect } from "react";
import { Circle, MapContainer, Polygon, Popup, TileLayer, useMap } from "react-leaflet";

// Teselas configurables (VITE_MAP_TILE_URL). Por defecto OpenStreetMap: apto para uso
// personal de bajo tráfico respetando su política y la atribución.
const TILE_URL = import.meta.env.VITE_MAP_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION =
  import.meta.env.VITE_MAP_TILE_ATTRIBUTION ??
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

export const DEFAULT_CENTER = [54.6990336, 25.2618832];

export function BaseMap({ center = DEFAULT_CENTER, zoom = 14, className = "h-[420px]", children }) {
  return (
    <MapContainer center={center} zoom={zoom} className={`w-full rounded-xl ${className}`} scrollWheelZoom>
      <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} maxZoom={19} />
      {children}
    </MapContainer>
  );
}

/** Ajusta la vista a los puntos dados cuando cambian (una vez por `fitKey`). */
export function FitBounds({ points, fitKey, maxZoom = 16 }) {
  const map = useMap();
  useEffect(() => {
    const valid = (points ?? []).filter((p) => p && p[0] != null && p[1] != null);
    if (valid.length === 1) map.setView(valid[0], Math.max(map.getZoom(), 15));
    else if (valid.length > 1) map.fitBounds(L.latLngBounds(valid), { padding: [30, 30], maxZoom });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, map]);
  return null;
}

export function GeofenceLayer({ geofences }) {
  return (geofences ?? [])
    .filter((g) => g.enabled)
    .map((g) => {
      const style = { color: "#7c3aed", weight: 2, fillOpacity: 0.08 };
      const popup = <Popup>{g.name}</Popup>;
      return g.geofence_type === "circle" ? (
        <Circle key={g.id} center={[g.center_lat, g.center_lon]} radius={g.radius_m} pathOptions={style}>
          {popup}
        </Circle>
      ) : (
        <Polygon key={g.id} positions={g.points} pathOptions={style}>
          {popup}
        </Polygon>
      );
    });
}

const TONE_COLOR = { green: "#059669", sky: "#0284c7", amber: "#d97706", red: "#dc2626", slate: "#64748b" };

export function vehicleIcon(course, tone = "sky") {
  const color = TONE_COLOR[tone] ?? TONE_COLOR.sky;
  return L.divIcon({
    className: "vehicle-marker",
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    html: `<div class="arrow" style="background:${color}"><svg width="16" height="16" viewBox="0 0 16 16" style="transform:rotate(${course ?? 0}deg)"><path d="M8 1 14 15 8 11 2 15Z" fill="white"/></svg></div>`,
  });
}

export function dotIcon(color) {
  return L.divIcon({
    className: "vehicle-marker",
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    html: `<div style="width:14px;height:14px;border-radius:9999px;background:${color};border:2px solid white;box-shadow:0 1px 3px rgb(0 0 0/.4)"></div>`,
  });
}
