"""Geometría para geocercas (distancias en metros, coordenadas WGS84).

Para polígonos se usa una proyección equirectangular local: el error es
despreciable a escala de ciudad, que es el uso de una geocerca.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8

Point = tuple[float, float]  # (lat, lon)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def point_in_polygon(lat: float, lon: float, polygon: list[Point]) -> bool:
    """Ray casting. El polígono puede venir cerrado o abierto."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[j]
        if (lat_i > lat) != (lat_j > lat):
            lon_cross = lon_i + (lat - lat_i) * (lon_j - lon_i) / (lat_j - lat_i)
            if lon < lon_cross:
                inside = not inside
        j = i
    return inside


def distance_to_polygon_edge_m(lat: float, lon: float, polygon: list[Point]) -> float:
    """Distancia mínima del punto al borde del polígono, en metros."""
    k_lat = math.pi * EARTH_RADIUS_M / 180
    k_lon = k_lat * math.cos(math.radians(lat))

    def project(p: Point) -> tuple[float, float]:
        return ((p[1] - lon) * k_lon, (p[0] - lat) * k_lat)  # origen en el punto

    pts = [project(p) for p in polygon]
    best = math.inf
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1], strict=True):
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, -(x1 * dx + y1 * dy) / length2))
        best = min(best, math.hypot(x1 + t * dx, y1 + t * dy))
    return best


def validate_polygon(points: list[list[float]]) -> list[Point]:
    polygon = [(float(p[0]), float(p[1])) for p in points]
    if len(polygon) > 1 and polygon[0] == polygon[-1]:
        polygon = polygon[:-1]
    if len(polygon) < 3:
        raise ValueError("un polígono necesita al menos 3 vértices distintos")
    for lat, lon in polygon:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"coordenada fuera de rango: {lat}, {lon}")
    return polygon
