"""Persistencia en MySQL: tramas, posiciones, estado actual y sesiones.

Cada paquete AVL se guarda en UNA transacción (raw_packets + positions +
device_states). Solo si el commit termina bien el servidor envía el ACK
(ADR 0003). Las posiciones se insertan con ON DUPLICATE KEY sobre
(device_id, dedup_key): una retransmisión del equipo no crea duplicados y se
vuelve a confirmar con el mismo ACK.

Referencia Traccar: handler/DatabaseHandler.java, database/DeviceLookupService.java
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from valkery_core.enums import ParseStatus
from valkery_core.models import Device, DeviceSessionRecord, DeviceState, Position, RawPacket

from ..protocol.base import AvlPacket, CommandResponse, CrcError, ProtocolError, UnsupportedCodecError
from ..protocol.teltonika.decoder import CODEC_12
from ..session.device_session import DeviceSession
from .normalize import position_row

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
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

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
            await self._upsert_state(db, session.device_id, online=True, last_seen=session.connected_at)

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
            values: dict = {"last_seen": session.last_seen}
            if not device_still_online:
                values["online"] = False
            await self._upsert_state(db, session.device_id, **values)

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
            stmt = insert(Position).values(rows)
            # Duplicado → no se modifica nada (id = id). La retransmisión se confirma igual.
            await db.execute(stmt.on_duplicate_key_update(id=Position.__table__.c.id))

            await self._update_state_from_rows(db, session, rows)
        return len(packet.records)

    async def handle_command_response(self, session: DeviceSession, response: CommandResponse, raw: bytes) -> None:
        # La relación con commands/command_responses se implementa en la fase 6.
        async with self._session_factory.begin() as db:
            await db.execute(
                insert(RawPacket).values(
                    _raw_packet_values(session, raw, codec=CODEC_12, records=0, status=ParseStatus.OK, error=None)
                )
            )
        logger.info("IMEI %s | respuesta Codec 12: %r", session.imei, response.text)

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

    async def _update_state_from_rows(self, db: AsyncSession, session: DeviceSession, rows: list[dict]) -> None:
        state = await db.get(DeviceState, session.device_id, with_for_update=True)
        if state is None:
            state = DeviceState(device_id=session.device_id, online=True)
            db.add(state)
        state.online = True
        state.last_seen = session.last_seen

        newest = max(rows, key=lambda r: r["gps_time"])
        if state.last_gps_time is None or newest["gps_time"] >= state.last_gps_time:
            state.last_gps_time = newest["gps_time"]
            state.last_position_id = await self._position_id(db, session.device_id, newest["dedup_key"])
            for field in TELEMETRY_FIELDS:
                if newest[field] is not None:
                    setattr(state, field, newest[field])

        valid_rows = [r for r in rows if r["valid"]]
        if valid_rows:
            fix = max(valid_rows, key=lambda r: r["gps_time"])
            if state.fix_time is None or fix["gps_time"] >= state.fix_time:
                state.fix_time = fix["gps_time"]
                state.fix_position_id = await self._position_id(db, session.device_id, fix["dedup_key"])
                state.latitude = fix["latitude"]
                state.longitude = fix["longitude"]
                state.speed = fix["speed"]
                state.course = fix["course"]
        await db.flush()

    @staticmethod
    async def _position_id(db: AsyncSession, device_id: int, key: bytes) -> int | None:
        return await db.scalar(select(Position.id).where(Position.device_id == device_id, Position.dedup_key == key))

    @staticmethod
    async def _upsert_state(db: AsyncSession, device_id: int, **values) -> None:
        stmt = insert(DeviceState).values(device_id=device_id, **values)
        await db.execute(stmt.on_duplicate_key_update(**{k: stmt.inserted[k] for k in values}))
