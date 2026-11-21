"""Envío de comandos Codec 12 y seguimiento de su resultado (ADR 0002 y 0006).

Ciclo (cada ``interval_s``):
1. Comandos AUTORIZADO:
   - vencidos → EXPIRADO;
   - sin sesión TCP activa → FALLIDO (NUNCA se guardan para enviarlos al reconectar);
   - precondiciones re-validadas con el estado actual; si alguna falla → RECHAZADO;
   - si todo está bien → ENVIANDO (commit) → se escribe la trama → ENVIADO.
2. Plazos: ENVIANDO/ENVIADO sin respuesta y RESPUESTA_RECIBIDA sin verificación
   → RESULTADO_INCIERTO.

Respuestas: la respuesta Codec 12 no trae identificador; se asocia al último
comando ENVIADO del dispositivo (solo puede haber uno activo por equipo).

Verificación: un comando de relé pasa a VERIFICADO solo cuando un registro AVL
posterior al envío informa DOUT1 (I/O 179) con el valor esperado. La respuesta
del equipo no basta: no prueba el estado físico del relé.

Referencia Traccar: database/CommandsManager.java (sin readQueuedCommands)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from valkery_core.commands import SPECS, CommandType, analyze_response, check_preconditions, failed
from valkery_core.config import CoreSettings
from valkery_core.enums import CommandStatus, EventSource, EventType
from valkery_core.models import Command, CommandResponse, Device, DeviceState

from ..handlers.events.base import EventCandidate
from ..handlers.events.engine import store_events
from ..protocol.base import CommandResponse as Codec12Response
from ..protocol.teltonika.encoder import encode_codec12_command
from ..session.connection_manager import ConnectionManager
from ..session.device_session import DeviceSession

logger = logging.getLogger(__name__)

# Tolerancia entre el reloj del equipo (gps_time) y el del servidor (sent_at).
CLOCK_TOLERANCE = timedelta(seconds=30)


def _now() -> datetime:
    return datetime.now(UTC)


async def command_event(db: AsyncSession, cmd: Command, event_type: EventType, at: datetime, **extra: Any) -> None:
    """Eventos de control remoto, solo para comandos de relé (las consultas no ensucian el historial)."""
    spec = SPECS.get(CommandType(cmd.command_type))
    if spec is None or not spec.relay:
        return
    attributes = {"command_id": cmd.id, "command_type": cmd.command_type, "status": cmd.status, **extra}
    await store_events(
        db,
        cmd.device_id,
        [EventCandidate(event_type=event_type, source=EventSource.PLATFORM, occurred_at=at, attributes=attributes)],
    )


def _finish(cmd: Command, status: CommandStatus, at: datetime, reason: str | None = None) -> None:
    cmd.status = status.value
    cmd.finished_at = at
    if reason:
        cmd.failure_reason = reason[:255]


class CommandDispatcher:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        connections: ConnectionManager,
        settings: CoreSettings,
        interval_s: float = 1.0,
    ) -> None:
        self._session_factory = session_factory
        self._connections = connections
        self._settings = settings
        self._interval_s = interval_s

    # ------------------------------------------------------------------ envío

    async def dispatch_once(self) -> int:
        """Procesa los comandos AUTORIZADO. Devuelve cuántos se enviaron."""
        to_send: list[tuple[int, DeviceSession, bytes]] = []
        async with self._session_factory.begin() as db:
            commands = (
                await db.scalars(
                    select(Command)
                    .where(Command.status == CommandStatus.AUTORIZADO.value)
                    .order_by(Command.id)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for cmd in commands:
                prepared = await self._prepare(db, cmd)
                if prepared is not None:
                    to_send.append(prepared)

        sent = 0
        for command_id, session, frame in to_send:
            sent += await self._send(command_id, session, frame)
        return sent

    async def _prepare(self, db: AsyncSession, cmd: Command) -> tuple[int, DeviceSession, bytes] | None:
        now = _now()
        spec = SPECS[CommandType(cmd.command_type)]
        if cmd.expires_at <= now:
            _finish(cmd, CommandStatus.EXPIRADO, now, "venció antes de enviarse")
            await command_event(db, cmd, EventType.COMMAND_FAILED, now, reason=cmd.failure_reason)
            return None

        device = await db.get(Device, cmd.device_id)
        session = self._connections.get(device.imei) if device else None
        state = await db.get(DeviceState, cmd.device_id)
        checks = check_preconditions(
            spec,
            settings=self._settings,
            device_enabled=bool(device and device.enabled),
            online=session is not None,
            state=state,
            now=now,
        )
        cmd.preconditions = [*cmd.preconditions, *({"stage": "dispatch", **c.as_dict()} for c in checks)]
        problems = failed(checks)
        if problems:
            offline = any(c.name == "online" for c in problems)
            status = CommandStatus.FALLIDO if offline else CommandStatus.RECHAZADO
            _finish(cmd, status, now, "al enviar: " + "; ".join(c.detail for c in problems))
            await command_event(db, cmd, EventType.COMMAND_FAILED, now, reason=cmd.failure_reason)
            logger.warning("Comando %d no enviado: %s", cmd.id, cmd.failure_reason)
            return None

        frame = encode_codec12_command(cmd.command_text)
        cmd.status = CommandStatus.ENVIANDO.value
        cmd.sent_frame = frame
        cmd.session_id = session.record_id
        return cmd.id, session, frame

    async def _send(self, command_id: int, session: DeviceSession, frame: bytes) -> int:
        error: str | None = None
        try:
            await session.send(frame)
        except Exception as exc:  # conexión caída justo al escribir
            error = f"error al escribir en la conexión: {type(exc).__name__}"
        now = _now()
        async with self._session_factory.begin() as db:
            cmd = await db.get(Command, command_id, with_for_update=True)
            if cmd is None or cmd.status != CommandStatus.ENVIANDO.value:
                return 0
            if error:
                _finish(cmd, CommandStatus.FALLIDO, now, error)
                await command_event(db, cmd, EventType.COMMAND_FAILED, now, reason=error)
                return 0
            cmd.status = CommandStatus.ENVIADO.value
            cmd.sent_at = now
            await command_event(db, cmd, EventType.COMMAND_SENT, now)
        logger.info("Comando %d enviado a IMEI %s", command_id, session.imei)
        return 1

    # ------------------------------------------------------------------ respuestas

    async def on_response(
        self, db: AsyncSession, session: DeviceSession, response: Codec12Response, raw_packet_id: int | None
    ) -> CommandResponse:
        """Asocia la respuesta Codec 12 al comando enviado (dentro de la transacción del sink)."""
        now = _now()
        text = response.text
        cmd = await db.scalar(
            select(Command)
            .where(
                Command.device_id == session.device_id,
                Command.status.in_([CommandStatus.ENVIADO.value, CommandStatus.ENVIANDO.value]),
            )
            .order_by(Command.id.desc())
            .limit(1)
            .with_for_update()
        )
        if cmd is None:
            row = CommandResponse(
                command_id=None,
                device_id=session.device_id,
                raw_packet_id=raw_packet_id,
                received_at=now,
                response_text=text,
                result="unmatched",
                detail="respuesta sin comando enviado pendiente",
            )
            db.add(row)
            logger.warning("Respuesta Codec 12 sin comando pendiente (IMEI %s): %r", session.imei, text)
            return row

        spec = SPECS[CommandType(cmd.command_type)]
        analysis = analyze_response(spec, text)
        row = CommandResponse(
            command_id=cmd.id,
            device_id=session.device_id,
            raw_packet_id=raw_packet_id,
            received_at=now,
            response_text=text,
            result="ok" if analysis.ok else "error",
            detail=analysis.detail,
        )
        db.add(row)
        cmd.responded_at = now
        if cmd.sent_at is None:
            cmd.sent_at = now
        if not analysis.ok:
            _finish(cmd, CommandStatus.FALLIDO, now, f"respuesta del equipo: {analysis.detail}")
            await command_event(db, cmd, EventType.COMMAND_FAILED, now, response=text[:200])
        else:
            cmd.status = CommandStatus.RESPUESTA_RECIBIDA.value
            if spec.expected_dout1 is None:
                cmd.finished_at = now  # consulta: la respuesta es el resultado
            await command_event(db, cmd, EventType.COMMAND_RESPONSE, now, response=text[:200])
        logger.info("Comando %d: respuesta %r → %s", cmd.id, text, cmd.status)
        return row

    # ------------------------------------------------------------------ verificación

    async def verify_from_rows(self, db: AsyncSession, device_id: int, rows: list[dict[str, Any]]) -> list[int]:
        """Marca VERIFICADO los comandos de relé cuyo DOUT1 esperado aparece en registros posteriores al envío."""
        candidates = (
            await db.scalars(
                select(Command)
                .where(
                    Command.device_id == device_id,
                    Command.expected_dout1.is_not(None),
                    Command.status.in_([CommandStatus.ENVIADO.value, CommandStatus.RESPUESTA_RECIBIDA.value]),
                )
                .with_for_update()
            )
        ).all()
        verified: list[int] = []
        for cmd in candidates:
            if cmd.sent_at is None:
                continue
            for row in sorted(rows, key=lambda r: r["gps_time"]):
                if (
                    row["dout1"] is cmd.expected_dout1
                    and row["received_at"] >= cmd.sent_at
                    and row["gps_time"] >= cmd.sent_at - CLOCK_TOLERANCE
                ):
                    now = _now()
                    cmd.status = CommandStatus.VERIFICADO.value
                    cmd.verified_at = now
                    cmd.finished_at = now
                    cmd.verification = {
                        "position_id": row["id"],
                        "gps_time": row["gps_time"].isoformat(),
                        "dout1": row["dout1"],
                        "source": "I/O 179 en registro AVL posterior al envío",
                    }
                    await command_event(db, cmd, EventType.COMMAND_VERIFIED, now, position_id=row["id"])
                    verified.append(cmd.id)
                    logger.info("Comando %d VERIFICADO por DOUT1=%s", cmd.id, row["dout1"])
                    break
        return verified

    # ------------------------------------------------------------------ plazos

    async def expire_once(self) -> int:
        now = _now()
        s = self._settings
        changed = 0
        async with self._session_factory.begin() as db:
            commands = (
                await db.scalars(
                    select(Command)
                    .where(
                        Command.status.in_(
                            [
                                CommandStatus.CREADO.value,
                                CommandStatus.ENVIANDO.value,
                                CommandStatus.ENVIADO.value,
                                CommandStatus.RESPUESTA_RECIBIDA.value,
                            ]
                        ),
                        Command.finished_at.is_(None),
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for cmd in commands:
                reason = None
                status = CommandStatus.RESULTADO_INCIERTO
                if cmd.status == CommandStatus.CREADO.value and cmd.expires_at <= now:
                    status, reason = CommandStatus.EXPIRADO, "no se confirmó a tiempo"
                elif cmd.status in (CommandStatus.ENVIANDO.value, CommandStatus.ENVIADO.value):
                    started = cmd.sent_at or cmd.confirmed_at or cmd.requested_at
                    if now - started > timedelta(seconds=s.command_response_timeout_s):
                        reason = "sin respuesta del equipo en el plazo"
                elif cmd.status == CommandStatus.RESPUESTA_RECIBIDA.value and cmd.expected_dout1 is not None:
                    if cmd.responded_at and now - cmd.responded_at > timedelta(seconds=s.command_verify_timeout_s):
                        reason = "sin registro que confirme DOUT1 en el plazo; verificar en sitio"
                if reason:
                    _finish(cmd, status, now, reason)
                    await command_event(db, cmd, EventType.COMMAND_FAILED, now, reason=reason)
                    changed += 1
        return changed

    async def run(self) -> None:
        while True:
            try:
                await self.dispatch_once()
                await self.expire_once()
            except Exception:
                logger.exception("Fallo en el despachador de comandos")
            await asyncio.sleep(self._interval_s)
