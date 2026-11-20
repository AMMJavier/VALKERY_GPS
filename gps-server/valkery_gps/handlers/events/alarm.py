"""Alarmas nativas del equipo (I/O eventuales).

Solo se genera la alarma cuando el registro fue CAUSADO por ese I/O
(event_io_id) y el valor indica inicio. Así el valor que se repite en los
registros periódicos no produce alarmas repetidas.

Las alarmas de registros antiguos (memoria del equipo) sí se generan, con su
hora GPS real: el hecho ocurrió aunque llegue tarde.

IDs según el PDF FMB1YX (pp. 17-18). Deben confirmarse con la lista I/O del
FMC920 y su configuración (cada alarma debe estar habilitada en el equipo).

OVERSPEED nativo (I/O 255) no se usa: el equipo envía el mismo I/O al inicio y
al final del exceso, y no se pueden distinguir sin ambigüedad.

Referencia Traccar: handler/events/AlarmEventHandler.java
"""

from __future__ import annotations

from typing import Any

from valkery_core.enums import EventSource, EventType

from .base import EventCandidate

IO_TOWING = 246  # 1 = remolque
IO_CRASH = 247  # >0 = choque
IO_UNPLUG = 252  # 1 = batería/alimentación desconectada
IO_JAMMING = 249  # 1 = inicio de jamming

NATIVE_ALARMS: dict[int, EventType] = {
    IO_TOWING: EventType.TOWING,
    IO_CRASH: EventType.CRASH,
    IO_UNPLUG: EventType.POWER_CUT,
    IO_JAMMING: EventType.JAMMING,
}


def detect_alarms(rows: list[dict[str, Any]]) -> list[EventCandidate]:
    events: list[EventCandidate] = []
    for row in rows:
        event_io_id = row["event_io_id"]
        event_type = NATIVE_ALARMS.get(event_io_id)
        if event_type is None:
            continue
        value = row["io"].get(str(event_io_id))
        if not isinstance(value, int) or value < 1:
            continue
        events.append(
            EventCandidate(
                event_type=event_type,
                source=EventSource.DEVICE,
                occurred_at=row["gps_time"],
                position_id=row["id"],
                attributes={
                    "io_id": event_io_id,
                    "value": value,
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "valid": row["valid"],
                    "speed": row["speed"],
                },
            )
        )
    return events
