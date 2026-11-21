"""Catálogo de comandos, precondiciones de seguridad e interpretación de respuestas.

Lo usan la API (al crear y confirmar) y el servidor GPS (justo antes de enviar):
las precondiciones se validan TRES veces porque el estado de la moto puede
cambiar entre la confirmación y el envío.

Reglas (documento, sección 4.1):
- Inmovilizar solo con la moto detenida, comprobado con VARIAS señales
  (contacto apagado + velocidad 0 + sin movimiento), con datos recientes y
  el equipo conectado. Ninguna señal desconocida se toma como segura.
- No hay comandos arbitrarios: solo los del catálogo.
- Un ACK o una respuesta del equipo NO prueba el cambio del relé: la
  verificación exige observar DOUT1 en un registro posterior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from .config import CoreSettings
from .enums import Permission


class CommandType(StrEnum):
    GET_VERSION = "GET_VERSION"
    GET_STATUS = "GET_STATUS"
    GET_INFO = "GET_INFO"
    IMMOBILIZE = "IMMOBILIZE"
    RELEASE = "RELEASE"


@dataclass(frozen=True, slots=True)
class CommandSpec:
    type: CommandType
    label: str
    description: str
    permissions: tuple[Permission, ...]
    relay: bool  # cambia DOUT1 / el relé
    requires_confirmation: bool  # exige reingresar la contraseña
    expected_dout1: bool | None  # valor que verifica el comando
    fixed_text: str | None = None  # texto fijo (los de relé vienen de la configuración)

    def text(self, settings: CoreSettings) -> str:
        if self.type == CommandType.IMMOBILIZE:
            return settings.command_immobilize_text
        if self.type == CommandType.RELEASE:
            return settings.command_release_text
        assert self.fixed_text is not None
        return self.fixed_text


SPECS: dict[CommandType, CommandSpec] = {
    CommandType.GET_VERSION: CommandSpec(
        CommandType.GET_VERSION,
        "Versión de firmware",
        "Consulta de solo lectura (getver). Útil para probar el canal Codec 12 sin riesgo.",
        (Permission.COMMANDS_SEND,),
        relay=False,
        requires_confirmation=False,
        expected_dout1=None,
        fixed_text="getver",
    ),
    CommandType.GET_STATUS: CommandSpec(
        CommandType.GET_STATUS,
        "Estado del equipo",
        "Consulta de solo lectura (getstatus).",
        (Permission.COMMANDS_SEND,),
        relay=False,
        requires_confirmation=False,
        expected_dout1=None,
        fixed_text="getstatus",
    ),
    CommandType.GET_INFO: CommandSpec(
        CommandType.GET_INFO,
        "Información del equipo",
        "Consulta de solo lectura (getinfo).",
        (Permission.COMMANDS_SEND,),
        relay=False,
        requires_confirmation=False,
        expected_dout1=None,
        fixed_text="getinfo",
    ),
    CommandType.IMMOBILIZE: CommandSpec(
        CommandType.IMMOBILIZE,
        "Inmovilizar",
        "Activa DOUT1 (relé de corte). Solo con la moto detenida y el contacto apagado.",
        (Permission.COMMANDS_SEND, Permission.COMMANDS_IMMOBILIZE),
        relay=True,
        requires_confirmation=True,
        expected_dout1=True,
    ),
    CommandType.RELEASE: CommandSpec(
        CommandType.RELEASE,
        "Desbloquear",
        "Desactiva DOUT1 (libera el relé). Recuperación: no exige la moto detenida.",
        (Permission.COMMANDS_SEND,),
        relay=True,
        requires_confirmation=True,
        expected_dout1=False,
    ),
}


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


def _age(now: datetime, at: datetime | None) -> float | None:
    return None if at is None else (now - at).total_seconds()


def check_preconditions(
    spec: CommandSpec,
    *,
    settings: CoreSettings,
    device_enabled: bool,
    online: bool,
    state: Any | None,
    now: datetime,
) -> list[Check]:
    """Devuelve TODAS las comprobaciones (pasadas y fallidas) para mostrarlas y auditarlas.

    ``state`` es una fila de device_states (o un objeto con los mismos atributos).
    """
    checks = [
        Check("commands_enabled", settings.commands_enabled, "Comandos habilitados en la configuración"),
        Check("device_enabled", device_enabled, "Dispositivo habilitado"),
        Check("online", online, "Equipo conectado ahora (no se encolan comandos para después)"),
    ]
    if spec.relay:
        checks.append(
            Check(
                "relay_enabled",
                settings.commands_relay_enabled,
                "Comandos de relé habilitados (requiere la prueba física del relé)",
            )
        )
    if spec.type != CommandType.IMMOBILIZE:
        return checks

    max_age = settings.command_state_max_age_s
    seen_age = _age(now, getattr(state, "last_seen", None))
    data_age = _age(now, getattr(state, "last_gps_time", None))
    ignition = getattr(state, "ignition", None)
    speed = getattr(state, "speed", None)
    movement = getattr(state, "movement", None)
    dout1 = getattr(state, "dout1", None)

    checks += [
        Check(
            "recent_communication",
            seen_age is not None and seen_age <= max_age,
            f"Comunicación en los últimos {max_age} s" + (f" (hace {seen_age:.0f} s)" if seen_age is not None else ""),
        ),
        Check(
            "recent_record",
            data_age is not None and -60 <= data_age <= max_age,
            f"Registro del equipo de los últimos {max_age} s" + (f" (hace {data_age:.0f} s)" if data_age is not None else ""),
        ),
        Check("ignition_off", ignition is False, f"Contacto apagado (actual: {_tri(ignition, 'encendido', 'apagado')})"),
        Check("speed_zero", speed == 0, f"Velocidad 0 km/h (actual: {'desconocida' if speed is None else speed})"),
        Check("not_moving", movement is False, f"Sin movimiento (actual: {_tri(movement, 'en movimiento', 'detenido')})"),
        Check("not_already_active", dout1 is not True, "DOUT1 no está ya activa"),
    ]
    return checks


def _tri(value: bool | None, yes: str, no: str) -> str:
    return "desconocido" if value is None else (yes if value else no)


def failed(checks: list[Check]) -> list[Check]:
    return [c for c in checks if not c.ok]


_DOUT_RE = re.compile(r"DOUT1\s*[:=]\s*([01])", re.IGNORECASE)
_ERROR_RE = re.compile(r"unknown|invalid|error|not\s+(?:supported|allowed)|wrong", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ResponseAnalysis:
    ok: bool
    dout1: bool | None
    detail: str


def analyze_response(spec: CommandSpec, text: str) -> ResponseAnalysis:
    """Interpreta el texto de la respuesta Codec 12.

    La respuesta de setdigout informa el estado PEDIDO de la salida; no prueba el
    relé físico. Formato esperado (variable según firmware): "DOUT1:1 Timeout:INFINITY".
    """
    if _ERROR_RE.search(text or ""):
        return ResponseAnalysis(False, None, "El equipo informó un error")
    if not spec.relay:
        return ResponseAnalysis(True, None, "Respuesta recibida")
    match = _DOUT_RE.search(text or "")
    if match is None:
        return ResponseAnalysis(True, None, "Respuesta sin estado DOUT1 reconocible; se espera verificación")
    dout1 = match.group(1) == "1"
    if dout1 != spec.expected_dout1:
        return ResponseAnalysis(False, dout1, "El equipo informa un DOUT1 distinto al pedido")
    return ResponseAnalysis(True, dout1, "El equipo informa DOUT1 en el valor pedido")


def expires_at(now: datetime, settings: CoreSettings) -> datetime:
    return now + timedelta(seconds=settings.command_ttl_s)
