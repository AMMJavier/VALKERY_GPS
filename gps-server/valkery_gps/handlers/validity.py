"""Determina si un registro trae una posición GPS válida.

Sin señal, el equipo repite la última latitud/longitud/altitud y pone ángulo,
satélites y velocidad en 0 (PDF pág. 3). Por eso no basta con que existan
coordenadas.

Reglas:
- Coordenadas dentro de rango y distintas de (0, 0).
- Al menos 1 satélite (0 = sin fix según el PDF).
- Si el equipo informa I/O 69 (GNSS status), debe ser 1 = "ON with fix".

Referencia Traccar: handler/FilterHandler.java
"""

from __future__ import annotations

from ..protocol.base import AvlRecord

IO_GNSS_STATUS = 69
GNSS_STATUS_FIX = 1


def is_valid_position(record: AvlRecord) -> bool:
    if not (-90.0 <= record.latitude <= 90.0 and -180.0 <= record.longitude <= 180.0):
        return False
    if record.latitude == 0.0 and record.longitude == 0.0:
        return False
    if record.satellites < 1:
        return False
    gnss_status = record.io.get(IO_GNSS_STATUS)
    return gnss_status is None or gnss_status == GNSS_STATUS_FIX
