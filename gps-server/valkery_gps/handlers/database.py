"""Persistencia en MySQL: tramas, posiciones, estado actual y sesiones.

Cada paquete AVL se guarda en UNA transacción (raw_packets + positions +
device_states + events). Solo si el commit termina bien el servidor envía
el ACK (ADR 0003). Las posiciones se insertan con ON DUPLICATE KEY sobre
(device_id, dedup_key): una retransmisión del equipo no crea duplicados y se
vuelve a confirmar con el mismo ACK.

Referencia Traccar: handler/DatabaseHandler.java, database/DeviceLookupService.java
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from valkery_core.enums import EventType, ParseStatus
from valkery_core.models import Device, DeviceSessionRecord, DeviceState, Position, RawPacket

from ..protocol.base import AvlPacket, CommandResponse, CrcError, ProtocolError, UnsupportedCodecError
from ..protocol.teltonika.decoder import CODEC_12
from ..session.device_session import DeviceSession
from .events.base import EventSettings, PreviousState
from .events.engine import EventEngine, connectivity_event
from .normalize import position_row

if TYPE_CHECKING:
    from ..commands.dispatcher import CommandDispatcher

logger = logging.getLogger(__name__)

# Campos de device_states que se copian del registro más reciente.
TELEMETRY_FIELDS = (
    "ignition",
    "movement",
    "dout1",
    "gnss_status",
    "gsm_signal",
    "external_voltage_mv",
    "battery_voltage_mv",
    "odometer_m",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _raw_packet_values(
    session: DeviceSession, raw: bytes, *, codec: int | None, records: int, status: ParseStatus, error: str | None
) -> dict:
    return {
        "device_id": session.device_id,
        "session_id": session.record_id,
        "received_at": _now(),
        "codec": codec,
        "record_count": records,
        "payload": raw,
        "digest": hashlib.sha256(raw).digest(),
        "parse_status": status.value,
        "error": error[:255] if error else None,
    }


class DatabaseDeviceRegistry:
    """Autoriza IMEIs registrados y habilitados en la tabla devices."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def authorize(self, imei: str) -> int | None:
        async with self._session_factory() as db:
            return await db.scalar(select(Device.id).where(Device.imei == imei, Device.enabled.is_(True)))


class DatabaseSink:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        events: EventSettings | None = None,
        commands: CommandDispatcher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._engine = EventEngine(events or EventSettings())
        self.commands = commands

    async def mark_all_offline(self) -> None:
        """Al arrancar no hay sesiones vivas: limpia estados de un cierre abrupto anterior."""
        async with self._session_factory.begin() as db:
            await db.execute(update(DeviceState).where(DeviceState.online.is_(True)).values(online=False))
            await db.execute(
                update(DeviceSessionRecord)
                .where(DeviceSessionRecord.disconnected_at.is_(None))
                .values(disconnected_at=_now(), close_reason="server_restart")
            )

    # ------------------------------------------------------------- sesiones

    async def session_opened(self, session: DeviceSession) -> None:
        async with self._session_factory.begin() as db:
            result = await db.execute(
                insert(DeviceSessionRecord).values(
                    device_id=session.device_id,
                    transport=session.transport,
                    remote_addr=session.peer[:64],
                    connected_at=session.connected_at,
                    packets=0,
                    records=0,
                )
            )
            session.record_id = result.inserted_primary_key[0]
            state = await self._lock_state(db, session.device_id)
            state.online = True
            await self._communication(db, state, session.connected_at)

    async def session_closed(self, session: DeviceSession, reason: str, device_still_online: bool) -> None:
        async with self._session_factory.begin() as db:
            if session.record_id is not None:
                await db.execute(
                    update(DeviceSessionRecord)
                    .where(DeviceSessionRecord.id == session.record_id)
                    .values(
                        disconnected_at=_now(),
                        close_reason=reason,
                        packets=session.packets_received,
                        records=session.records_received,
                    )
                )
            state = await self._lock_state(db, session.device_id)
            if state.last_seen is None or session.last_seen > state.last_seen:
                state.last_seen = session.last_seen
            if not device_still_online:
                state.online = False

    # ------------------------------------------------------------- paquetes

    async def handle_packet(self, session: DeviceSession, packet: AvlPacket, raw: bytes) -> int:
        received_at = _now()
        async with self._session_factory.begin() as db:
            result = await db.execute(
                insert(RawPacket).values(
                    _raw_packet_values(
                        session, raw, codec=packet.codec, records=len(packet.records), status=ParseStatus.OK, error=None
                    )
                )
            )
            raw_packet_id = result.inserted_primary_key[0]

            rows = [
                position_row(r, device_id=session.device_id, received_at=received_at, raw_packet_id=raw_packet_id)
                for r in packet.records
            ]
            # El bloqueo del estado serializa los paquetes del mismo dispositivo.
            state = await self._lock_state(db, session.device_id)
            previous = PreviousState(state.ignition, state.last_gps_time, state.fix_time)

            keys = [r["dedup_key"] for r in rows]
            key_filter = (Position.device_id == session.device_id, Position.dedup_key.in_(keys))
            existing = set((await db.scalars(select(Position.dedup_key).where(*key_filter))).all())

            stmt = insert(Position).values(rows)
            # Duplicado → no se modifica nada (id = id). La retransmisión se confirma igual.
            await db.execute(stmt.on_duplicate_key_update(id=Position.__table__.c.id))

            # dict(Result) no sirve: Result tiene .keys() y dict() lo trata como mapeo.
            result = await db.execute(select(Position.dedup_key, Position.id).where(*key_filter))
            ids = {key: position_id for key, position_id in result}
            new_rows: list[dict] = []
            seen: set[bytes] = set(existing)
            for row in rows:
                row["id"] = ids[row["dedup_key"]]
                if row["dedup_key"] not in seen:
                    seen.add(row["dedup_key"])
                    new_rows.append(row)

            state.online = True
            await self._communication(db, state, session.last_seen)
            self._apply_rows_to_state(state, rows)
            await self._engine.process(db, session.device_id, new_rows, previous)
            if self.commands is not None and new_rows:
                await self.commands.verify_from_rows(db, session.device_id, new_rows)
        return len(packet.records)

    async def handle_command_response(self, session: DeviceSession, response: CommandResponse, raw: bytes) -> None:
        async with self._session_factory.begin() as db:
            result = await db.execute(
                insert(RawPacket).values(
                    _raw_packet_values(session, raw, codec=CODEC_12, records=0, status=ParseStatus.OK, error=None)
                )
            )
            state = await self._lock_state(db, session.device_id)
            await self._communication(db, state, session.last_seen)
            if self.commands is not None:
                await self.commands.on_response(db, session, response, result.inserted_primary_key[0])
            else:
                logger.info("IMEI %s | respuesta Codec 12 sin despachador: %r", session.imei, response.text)

    async def packet_rejected(self, session: DeviceSession, raw: bytes, error: ProtocolError) -> None:
        if isinstance(error, CrcError):
            status = ParseStatus.CRC_ERROR
        elif isinstance(error, UnsupportedCodecError):
            status = ParseStatus.UNSUPPORTED
        else:
            status = ParseStatus.INVALID
        codec = raw[8] if len(raw) > 8 else None
        async with self._session_factory.begin() as db:
            await db.execute(
                insert(RawPacket).values(
                    _raw_packet_values(session, raw, codec=codec, records=0, status=status, error=str(error))
                )
            )

    # ------------------------------------------------------------- estado actual

    @staticmethod
    async def _lock_state(db: AsyncSession, device_id: int) -> DeviceState:
        """Devuelve la fila de estado bloqueada (FOR UPDATE), creándola si no existe."""
        stmt = insert(DeviceState).values(device_id=device_id)
        # No se usa INSERT IGNORE: ocultaría errores reales (p. ej. FK inexistente).
        await db.execute(stmt.on_duplicate_key_update(device_id=DeviceState.__table__.c.device_id))
        state = await db.get(DeviceState, device_id, with_for_update=True, populate_existing=True)
        assert state is not None
        return state

    @staticmethod
    async def _communication(db: AsyncSession, state: DeviceState, at: datetime) -> None:
        """Cualquier comunicación: actualiza last_seen y cierra un aviso de OFFLINE previo."""
        if state.reported_offline:
            state.reported_offline = False
            await connectivity_event(
                db,
                state.device_id,
                EventType.DEVICE_ONLINE,
                at,
                {"last_seen": state.last_seen.isoformat() if state.last_seen else None},
            )
        if state.last_seen is None or at > state.last_seen:
            state.last_seen = at

    @staticmethod
    def _apply_rows_to_state(state: DeviceState, rows: list[dict]) -> None:
        newest = max(rows, key=lambda r: r["gps_time"])
        if state.last_gps_time is None or newest["gps_time"] >= state.last_gps_time:
            state.last_gps_time = newest["gps_time"]
            state.last_position_id = newest["id"]
            for field in TELEMETRY_FIELDS:
                if newest[field] is not None:
                    setattr(state, field, newest[field])

        valid_rows = [r for r in rows if r["valid"]]
        if valid_rows:
            fix = max(valid_rows, key=lambda r: r["gps_time"])
            if state.fix_time is None or fix["gps_time"] >= state.fix_time:
                state.fix_time = fix["gps_time"]
                state.fix_position_id = fix["id"]
                state.latitude = fix["latitude"]
                state.longitude = fix["longitude"]
                state.speed = fix["speed"]
                state.course = fix["course"]
