"""Tipos comunes del motor de eventos.

Los detectores son funciones puras: reciben filas de posiciones normalizadas
(ver handlers/normalize.py, con su "id" ya asignado) y el estado previo, y
devuelven ``EventCandidate``. El motor (engine.py) aplica reglas y persiste.

Referencia Traccar: handler/events/BaseEventHandler.java
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from valkery_core.enums import EventSource, EventType


@dataclass(slots=True)
class EventCandidate:
    event_type: EventType
    source: EventSource
    occurred_at: datetime
    position_id: int | None = None
    geofence_id: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def dedup_key(self) -> bytes | None:
        """Solo los eventos ligados a una posición son deduplicables."""
        if self.position_id is None:
            return None
        raw = f"{self.position_id}|{self.event_type.value}|{self.geofence_id or 0}"
        return hashlib.sha256(raw.encode("ascii")).digest()


@dataclass(frozen=True, slots=True)
class PreviousState:
    """Estado del dispositivo ANTES de aplicar el paquete actual."""

    ignition: bool | None
    last_gps_time: datetime | None
    fix_time: datetime | None


def _int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


@dataclass(frozen=True, slots=True)
class EventSettings:
    # Si pasa más que esto entre dos registros, el valor nuevo de ignition se
    # toma como estado inicial y no como transición (documento, sección 8.2).
    ignition_max_gap_s: int = 3600
    # Sin comunicación durante este tiempo → DEVICE_OFFLINE.
    offline_after_s: int = 1800
    inactivity_check_s: int = 60
    # Histéresis de geocercas: para "salir" hay que alejarse este margen del borde.
    geofence_margin_m: int = 25

    @property
    def ignition_max_gap(self) -> timedelta:
        return timedelta(seconds=self.ignition_max_gap_s)

    @classmethod
    def from_env(cls) -> EventSettings:
        d = cls()
        return cls(
            ignition_max_gap_s=_int("VALKERY_EVENT_IGNITION_MAX_GAP_S", d.ignition_max_gap_s),
            offline_after_s=_int("VALKERY_EVENT_OFFLINE_AFTER_S", d.offline_after_s),
            inactivity_check_s=_int("VALKERY_EVENT_INACTIVITY_CHECK_S", d.inactivity_check_s),
            geofence_margin_m=_int("VALKERY_GEOFENCE_MARGIN_M", d.geofence_margin_m),
        )
