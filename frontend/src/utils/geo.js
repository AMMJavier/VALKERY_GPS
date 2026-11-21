const EARTH_RADIUS_M = 6371008.8;

export function haversineM(lat1, lon1, lat2, lon2) {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a));
}

/** Resumen de un recorrido usando solo posiciones válidas. */
export function trackSummary(positions) {
  const valid = positions.filter((p) => p.valid);
  let distance = 0;
  for (let i = 1; i < valid.length; i += 1) {
    distance += haversineM(valid[i - 1].latitude, valid[i - 1].longitude, valid[i].latitude, valid[i].longitude);
  }
  const maxSpeed = valid.reduce((max, p) => Math.max(max, p.speed), 0);
  const first = positions[0];
  const last = positions[positions.length - 1];
  return {
    points: positions.length,
    validPoints: valid.length,
    distanceM: distance,
    maxSpeed: valid.length ? maxSpeed : null,
    durationMs: first && last ? Date.parse(last.gps_time) - Date.parse(first.gps_time) : null,
  };
}
