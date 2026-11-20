"""Configuración del servidor GPS desde variables de entorno (ver .env.example).

La base de datos se configura en valkery_core.config (VALKERY_DB_URL).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


@dataclass(frozen=True, slots=True)
class GpsServerConfig:
    host: str = "0.0.0.0"
    port: int = 5027
    idle_timeout_s: int = 600
    handshake_timeout_s: int = 30
    max_connections: int = 50
    max_frame_bytes: int = 64 * 1024

    @classmethod
    def from_env(cls) -> GpsServerConfig:
        defaults = cls()  # con slots=True, cls.<campo> no devuelve el valor por defecto
        return cls(
            host=os.environ.get("VALKERY_GPS_HOST", defaults.host),
            port=_int("VALKERY_GPS_PORT", defaults.port),
            idle_timeout_s=_int("VALKERY_GPS_IDLE_TIMEOUT_S", defaults.idle_timeout_s),
            handshake_timeout_s=_int("VALKERY_GPS_HANDSHAKE_TIMEOUT_S", defaults.handshake_timeout_s),
            max_connections=_int("VALKERY_GPS_MAX_CONNECTIONS", defaults.max_connections),
            max_frame_bytes=_int("VALKERY_GPS_MAX_FRAME_BYTES", defaults.max_frame_bytes),
        )
