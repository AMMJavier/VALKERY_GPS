"""IGNITION_ON / IGNITION_OFF solo en transición real 0→1 / 1→0.

- Una posición con ignition=1 no genera IGNITION_ON en cada transmisión.
- Estado previo desconocido → el primer valor solo fija el estado.
- Hueco mayor que ignition_max_gap entre registros → el valor nuevo se toma
  como estado inicial, no como transición (no se sabe cuándo cambió).
- Registros más antiguos que el último conocido (memoria del equipo enviada
  tarde) no generan transiciones: compararían contra un estado posterior.

Referencia Traccar: handler/events/IgnitionEventHandler.java
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from valkery_core.enums import EventSource, EventType

from .base import EventCandidate, PreviousState


def detect_ignition(
    rows: list[dict[str, Any]], previous: PreviousState, max_gap: timedelta
) -> list[EventCandidate]:
    events: list[EventCandidate] = []
    state = previous.ignition
    state_time = previous.last_gps_time

    for row in sorted(rows, key=lambda r: r["gps_time"]):
        gps_time = row["gps_time"]
        if previous.last_gps_time is not None and gps_time < previous.last_gps_time:
            continue
        value = row["ignition"]
        if value is None:
            continue
        gap_too_big = state_time is not None and gps_time - state_time > max_gap
        if state is not None and not gap_too_big and value != state:
            events.append(
                EventCandidate(
                    event_type=EventType.IGNITION_ON if value else EventType.IGNITION_OFF,
                    source=EventSource.PLATFORM,
                    occurred_at=gps_time,
                    position_id=row["id"],
                    attributes={"latitude": row["latitude"], "longitude": row["longitude"], "valid": row["valid"]},
                )
            )
        state = value
        state_time = gps_time
    return events
