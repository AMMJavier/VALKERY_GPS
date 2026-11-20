"""Convierte un AvlRecord en la fila normalizada de ``positions``.

Contrato (documento de arquitectura, sección 8.1): identificación, hora GPS,
hora de recepción, validez, coordenadas, velocidad, rumbo, altitud, satélites,
prioridad, mapa I/O original (sin descartar desconocidos) y campos de primer
nivel interpretados.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from ..protocol.base import AvlRecord, IoValue
from .validity import is_valid_position

IO_IGNITION = 239
IO_MOVEMENT = 240
IO_DOUT1 = 179
IO_GNSS_STATUS = 69
IO_GSM_SIGNAL = 21
IO_EXTERNAL_VOLTAGE = 66
IO_BATTERY_VOLTAGE = 67
IO_TOTAL_ODOMETER = 16


def io_to_json(io: dict[int, IoValue]) -> dict[str, int | str]:
    """Claves como texto (JSON); valores de longitud variable en hexadecimal."""
    return {str(k): (v.hex() if isinstance(v, bytes) else v) for k, v in sorted(io.items())}


def dedup_key(record: AvlRecord) -> bytes:
    """SHA-256 del contenido del registro. Igual contenido = mismo registro."""
    parts = [
        str(int(record.timestamp.timestamp() * 1000)),
        f"{record.latitude:.7f}",
        f"{record.longitude:.7f}",
        str(record.altitude),
        str(record.angle),
        str(record.satellites),
        str(record.speed),
        str(record.priority),
        str(record.event_io_id),
    ]
    parts += [f"{k}={v}" for k, v in io_to_json(record.io).items()]
    return hashlib.sha256("|".join(parts).encode("ascii")).digest()


def _flag(io: dict[int, IoValue], io_id: int) -> bool | None:
    value = io.get(io_id)
    return None if value is None or isinstance(value, bytes) else bool(value)


def _number(io: dict[int, IoValue], io_id: int) -> int | None:
    value = io.get(io_id)
    return None if value is None or isinstance(value, bytes) else value


def position_row(
    record: AvlRecord, *, device_id: int, received_at: datetime, raw_packet_id: int | None
) -> dict[str, Any]:
    io = record.io
    return {
        "device_id": device_id,
        "raw_packet_id": raw_packet_id,
        "gps_time": record.timestamp,
        "received_at": received_at,
        "valid": is_valid_position(record),
        "latitude": record.latitude,
        "longitude": record.longitude,
        "altitude": record.altitude,
        "speed": record.speed,
        "course": record.angle,
        "satellites": record.satellites,
        "priority": record.priority,
        "event_io_id": record.event_io_id,
        "ignition": _flag(io, IO_IGNITION),
        "movement": _flag(io, IO_MOVEMENT),
        "dout1": _flag(io, IO_DOUT1),
        "gnss_status": _number(io, IO_GNSS_STATUS),
        "gsm_signal": _number(io, IO_GSM_SIGNAL),
        "external_voltage_mv": _number(io, IO_EXTERNAL_VOLTAGE),
        "battery_voltage_mv": _number(io, IO_BATTERY_VOLTAGE),
        "odometer_m": _number(io, IO_TOTAL_ODOMETER),
        "io": io_to_json(io),
        "dedup_key": dedup_key(record),
    }
