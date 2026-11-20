"""GEOFENCE_ENTER / GEOFENCE_EXIT con posiciones válidas.

- Solo cuentan posiciones con fix válido (una posición sin GPS repite la
  última coordenada y podría producir falsas entradas/salidas).
- Estado desconocido (sin fila en device_geofences) → la primera evaluación
  solo fija el estado.
- Histéresis: se entra al cruzar el borde, pero para salir hay que alejarse
  más que ``margin_m`` del borde. Evita entradas/salidas repetidas por el
  ruido del GPS cuando la moto está estacionada junto al límite.
- Posiciones más antiguas que el último fix conocido no cambian el estado.

Referencia Traccar: handler/GeofenceHandler.java, handler/events/GeofenceEventHandler.java
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from valkery_core.enums import EventSource, EventType, GeofenceType
from valkery_core.geo import Point, distance_to_polygon_edge_m, haversine_m, point_in_polygon

from .base import EventCandidate


@dataclass(frozen=True, slots=True)
class FenceShape:
    id: int
    name: str
    kind: GeofenceType
    center: Point | None = None
    radius_m: float | None = None
    polygon: tuple[Point, ...] = ()


@dataclass(slots=True)
class FenceTransition:
    inside: bool
    gps_time: datetime
    position_id: int


def is_inside(fence: FenceShape, lat: float, lon: float, was_inside: bool | None, margin_m: float) -> bool:
    if fence.kind == GeofenceType.CIRCLE:
        assert fence.center is not None and fence.radius_m is not None
        distance = haversine_m(lat, lon, fence.center[0], fence.center[1])
        limit = fence.radius_m + margin_m if was_inside else fence.radius_m
        return distance <= limit

    polygon = list(fence.polygon)
    if point_in_polygon(lat, lon, polygon):
        return True
    return bool(was_inside) and distance_to_polygon_edge_m(lat, lon, polygon) <= margin_m


def detect_geofences(
    rows: list[dict[str, Any]],
    fences: list[FenceShape],
    states: dict[int, bool],
    last_fix_time: datetime | None,
    margin_m: float,
) -> tuple[list[EventCandidate], dict[int, FenceTransition]]:
    """Devuelve eventos y el nuevo estado por geocerca (solo las que cambiaron o eran desconocidas)."""
    events: list[EventCandidate] = []
    updates: dict[int, FenceTransition] = {}
    current = dict(states)

    valid_rows = sorted((r for r in rows if r["valid"]), key=lambda r: r["gps_time"])
    for row in valid_rows:
        if last_fix_time is not None and row["gps_time"] < last_fix_time:
            continue
        for fence in fences:
            was_inside = current.get(fence.id)
            inside = is_inside(fence, row["latitude"], row["longitude"], was_inside, margin_m)
            if was_inside is not None and inside == was_inside:
                continue
            current[fence.id] = inside
            updates[fence.id] = FenceTransition(inside, row["gps_time"], row["id"])
            if was_inside is None:
                continue  # estado inicial
            events.append(
                EventCandidate(
                    event_type=EventType.GEOFENCE_ENTER if inside else EventType.GEOFENCE_EXIT,
                    source=EventSource.PLATFORM,
                    occurred_at=row["gps_time"],
                    position_id=row["id"],
                    geofence_id=fence.id,
                    attributes={
                        "geofence": fence.name,
                        "latitude": row["latitude"],
                        "longitude": row["longitude"],
                    },
                )
            )
    return events, updates
