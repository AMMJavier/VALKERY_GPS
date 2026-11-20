"""Catálogo de elementos I/O de Teltonika e interpretación de valores.

Fuente: PDF «FMB1YX Protocols V0.15» (pp. 5-18). Es de otra familia de equipos:
la lista real del FMC920 (wiki de Teltonika y capturas reales) tiene prioridad.
Los IDs que no están en el catálogo se conservan como ``io_<id>``.

Referencia Traccar: TeltonikaProtocolDecoder.registerParameter
"""

from __future__ import annotations

from dataclasses import dataclass

from ..base import IoValue


@dataclass(frozen=True, slots=True)
class IoElement:
    key: str
    size: int  # bytes en la trama (Codec 8)
    signed: bool = False
    multiplier: float | None = None
    unit: str | None = None


IO_ELEMENTS: dict[int, IoElement] = {
    # Permanentes
    239: IoElement("ignition", 1),
    240: IoElement("movement", 1),
    80: IoElement("data_mode", 1),
    21: IoElement("gsm_signal", 1),
    200: IoElement("sleep_mode", 1),
    69: IoElement("gnss_status", 1),  # 0 off, 1 fix, 2 sin fix, 3 sleep
    181: IoElement("gnss_pdop", 2, multiplier=0.1),
    182: IoElement("gnss_hdop", 2, multiplier=0.1),
    66: IoElement("external_voltage", 2, unit="mV"),
    67: IoElement("battery_voltage", 2, unit="mV"),
    68: IoElement("battery_current", 2, unit="mA"),
    24: IoElement("io_speed", 2, unit="km/h"),
    205: IoElement("gsm_cell_id", 2),
    206: IoElement("gsm_area_code", 2),
    241: IoElement("gsm_operator", 4),
    199: IoElement("trip_odometer", 4, unit="m"),
    16: IoElement("total_odometer", 4, unit="m"),
    1: IoElement("din1", 1),
    9: IoElement("ain1", 2, unit="mV"),
    179: IoElement("dout1", 1),  # estado lógico de DOUT1; NO es una orden
    17: IoElement("axis_x", 2, signed=True, unit="mG"),
    18: IoElement("axis_y", 2, signed=True, unit="mG"),
    19: IoElement("axis_z", 2, signed=True, unit="mG"),
    11: IoElement("iccid1", 8),
    14: IoElement("iccid2", 8),
    7: IoElement("records_in_flash", 2),
    # Eventuales
    175: IoElement("auto_geofence", 1),
    250: IoElement("trip", 1),
    251: IoElement("idling", 1),
    252: IoElement("unplug", 1),
    253: IoElement("green_driving_type", 1),
    254: IoElement("green_driving_value", 1),
    255: IoElement("over_speeding", 1, unit="km/h"),
    246: IoElement("towing", 1),
    247: IoElement("crash", 1),
    248: IoElement("immobilizer_ibutton", 1),  # iButton, NO el relé
    249: IoElement("jamming", 1),
}


def _to_signed(value: int, size: int) -> int:
    bits = size * 8
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def interpret(io: dict[int, IoValue]) -> dict[str, int | float | str]:
    """Convierte el mapa crudo id->valor en atributos con nombre y escala."""
    result: dict[str, int | float | str] = {}
    for io_id, raw in io.items():
        element = IO_ELEMENTS.get(io_id)
        if isinstance(raw, bytes):
            result[element.key if element else f"io_{io_id}"] = raw.hex()
            continue
        if element is None:
            result[f"io_{io_id}"] = raw
            continue
        value: int | float = _to_signed(raw, element.size) if element.signed else raw
        if element.multiplier is not None:
            value = round(value * element.multiplier, 3)
        result[element.key] = value
    return result
