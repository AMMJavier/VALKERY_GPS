"""Persistencia en MySQL (fase 2).

Criterio de aceptación: posiciones consultables y retransmisiones sin duplicados.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import func, select, update

from valkery_core.models import Device, DeviceSessionRecord, DeviceState, Position, RawPacket
from valkery_gps.config import GpsServerConfig
from valkery_gps.handlers.database import DatabaseDeviceRegistry, DatabaseSink
from valkery_gps.protocol.base import AvlRecord, CrcError
from valkery_gps.protocol.teltonika.avl_builder import build_avl_frame, build_imei_frame
from valkery_gps.protocol.teltonika.decoder import CODEC_8_EXT, decode_data_frame
from valkery_gps.schedule.retention import purge_raw_packets
from valkery_gps.server import GpsServer
from valkery_gps.session.device_session import DeviceSession

from ..conftest import TEST_IMEI
from .conftest import alembic_config


class _FakeWriter:
    def is_closing(self) -> bool:
        return False

    def close(self) -> None:
        pass


def _session(device: Device) -> DeviceSession:
    return DeviceSession(imei=device.imei, device_id=device.id, peer="127.0.0.1:5000", writer=_FakeWriter())


def _record(second: int, **kw) -> AvlRecord:
    base = dict(
        timestamp=datetime(2026, 11, 20, 12, 0, second, tzinfo=UTC),
        priority=0,
        longitude=25.26 + second / 10000,
        latitude=54.69,
        altitude=120,
        angle=45,
        satellites=10,
        speed=35,
        event_io_id=0,
        io={239: 1, 240: 1, 179: 0, 69: 1, 66: 12700, 16: 1000 + second},
    )
    base.update(kw)
    return AvlRecord(**base)


async def _count(factory, model) -> int:
    async with factory() as db:
        return await db.scalar(select(func.count()).select_from(model))


# --------------------------------------------------------------------- esquema


def test_models_match_migration(migrated_db):
    """alembic check: falla si los modelos tienen cambios sin migración."""
    command.check(alembic_config(migrated_db))


# --------------------------------------------------------------------- registro


async def test_registry_authorizes_only_enabled_devices(session_factory, device):
    registry = DatabaseDeviceRegistry(session_factory)
    assert await registry.authorize(TEST_IMEI) == device.id
    assert await registry.authorize("000000000000000") is None

    async with session_factory.begin() as db:
        await db.execute(update(Device).values(enabled=False))
    assert await registry.authorize(TEST_IMEI) is None


# --------------------------------------------------------------------- paquetes


async def test_packet_persisted_and_retransmission_not_duplicated(session_factory, device):
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)

    raw = build_avl_frame([_record(0), _record(10), _record(20)], CODEC_8_EXT)
    packet = decode_data_frame(raw)

    assert await sink.handle_packet(session, packet, raw) == 3
    # El equipo no recibió el ACK y reenvía el mismo paquete.
    assert await sink.handle_packet(session, packet, raw) == 3

    assert await _count(session_factory, Position) == 3
    assert await _count(session_factory, RawPacket) == 2  # las dos recepciones quedan trazadas

    async with session_factory() as db:
        positions = (await db.scalars(select(Position).order_by(Position.gps_time))).all()
        state = await db.get(DeviceState, device.id)

    p = positions[-1]
    assert p.gps_time == datetime(2026, 11, 20, 12, 0, 20, tzinfo=UTC)
    assert p.gps_time.tzinfo is not None
    assert p.valid and p.ignition and p.dout1 is False
    assert p.external_voltage_mv == 12700
    assert p.io["239"] == 1
    assert p.latitude == pytest.approx(54.69)

    assert state.online is True
    assert state.last_position_id == p.id
    assert state.fix_position_id == p.id
    assert state.odometer_m == 1020


async def test_pdf_example_persisted(session_factory, device, pdf_example):
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)
    await sink.handle_packet(session, decode_data_frame(pdf_example), pdf_example)

    async with session_factory() as db:
        p = await db.scalar(select(Position))
        raw = await db.scalar(select(RawPacket))
    assert p.gps_time == datetime(2013, 7, 17, 6, 34, 9, 140000, tzinfo=UTC)
    assert p.satellites == 18
    assert p.io["22"] == 1  # I/O desconocido conservado
    assert p.external_voltage_mv == 0x2E9F
    assert raw.payload == pdf_example and raw.parse_status == "ok" and raw.record_count == 1


async def test_old_records_do_not_regress_state(session_factory, device):
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)

    new = build_avl_frame([_record(30, io={239: 0, 69: 1})])
    await sink.handle_packet(session, decode_data_frame(new), new)
    # Registros más antiguos que el equipo tenía en memoria llegan después.
    old = build_avl_frame([_record(5, io={239: 1, 69: 1})])
    await sink.handle_packet(session, decode_data_frame(old), old)

    async with session_factory() as db:
        state = await db.get(DeviceState, device.id)
    assert state.last_gps_time == datetime(2026, 11, 20, 12, 0, 30, tzinfo=UTC)
    assert state.ignition is False
    assert state.fix_time == datetime(2026, 11, 20, 12, 0, 30, tzinfo=UTC)
    assert await _count(session_factory, Position) == 2


async def test_invalid_position_keeps_last_fix(session_factory, device):
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)

    good = build_avl_frame([_record(0)])
    await sink.handle_packet(session, decode_data_frame(good), good)
    no_fix = build_avl_frame([_record(10, satellites=0, speed=0, angle=0, io={69: 2, 239: 0})])
    await sink.handle_packet(session, decode_data_frame(no_fix), no_fix)

    async with session_factory() as db:
        state = await db.get(DeviceState, device.id)
        invalid = await db.scalar(select(Position).where(Position.valid.is_(False)))
    assert invalid is not None
    assert state.fix_time == datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)
    assert state.last_gps_time == datetime(2026, 11, 20, 12, 0, 10, tzinfo=UTC)
    assert state.ignition is False and state.gnss_status == 2


async def test_rejected_packet_stored_for_diagnosis(session_factory, device, pdf_example):
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)
    await sink.packet_rejected(session, pdf_example, CrcError("CRC"))

    async with session_factory() as db:
        raw = await db.scalar(select(RawPacket))
    assert raw.parse_status == "crc_error" and raw.codec == 8 and raw.record_count == 0
    assert await _count(session_factory, Position) == 0


# --------------------------------------------------------------------- sesiones


async def test_session_lifecycle(session_factory, device):
    sink = DatabaseSink(session_factory)
    first, second = _session(device), _session(device)
    await sink.session_opened(first)
    await sink.session_opened(second)
    first.packets_received, first.records_received = 2, 5
    await sink.session_closed(first, "replaced", device_still_online=True)

    async with session_factory() as db:
        state = await db.get(DeviceState, device.id)
        record = await db.get(DeviceSessionRecord, first.record_id)
    assert state.online is True
    assert record.close_reason == "replaced" and record.records == 5 and record.disconnected_at is not None

    await sink.session_closed(second, "idle_timeout", device_still_online=False)
    async with session_factory() as db:
        assert (await db.get(DeviceState, device.id)).online is False


async def test_mark_all_offline_on_startup(session_factory, device):
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)
    await sink.mark_all_offline()
    async with session_factory() as db:
        state = await db.get(DeviceState, device.id)
        record = await db.get(DeviceSessionRecord, session.record_id)
    assert state.online is False
    assert record.close_reason == "server_restart"


# --------------------------------------------------------------------- retención


async def test_retention_purges_only_old_raw_packets(session_factory, device):
    sink = DatabaseSink(session_factory)
    session = _session(device)
    await sink.session_opened(session)
    for second in (0, 1):
        raw = build_avl_frame([_record(second)])
        await sink.handle_packet(session, decode_data_frame(raw), raw)

    async with session_factory.begin() as db:
        oldest = await db.scalar(select(RawPacket.id).order_by(RawPacket.id).limit(1))
        await db.execute(
            update(RawPacket)
            .where(RawPacket.id == oldest)
            .values(received_at=datetime.now(UTC) - timedelta(days=31))
        )

    assert await purge_raw_packets(session_factory, retention_days=30) == 1
    assert await _count(session_factory, RawPacket) == 1
    assert await _count(session_factory, Position) == 2  # las posiciones se conservan
    async with session_factory() as db:
        orphan = await db.scalar(select(func.count()).select_from(Position).where(Position.raw_packet_id.is_(None)))
    assert orphan == 1


# --------------------------------------------------------------------- de punta a punta


async def test_end_to_end_tcp_to_mysql(session_factory, device):
    sink = DatabaseSink(session_factory)
    cfg = GpsServerConfig(host="127.0.0.1", port=0, handshake_timeout_s=2, idle_timeout_s=2)
    server = GpsServer(cfg, DatabaseDeviceRegistry(session_factory), sink)
    await server.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        frame = build_avl_frame([_record(0), _record(10)], CODEC_8_EXT)
        writer.write(build_imei_frame(TEST_IMEI))
        await writer.drain()
        assert await reader.readexactly(1) == b"\x01"
        for i in range(0, len(frame), 5):
            writer.write(frame[i : i + 5])
            await writer.drain()
        assert await asyncio.wait_for(reader.readexactly(4), 5) == (2).to_bytes(4, "big")
        # Retransmisión del mismo paquete
        writer.write(frame)
        await writer.drain()
        assert await asyncio.wait_for(reader.readexactly(4), 5) == (2).to_bytes(4, "big")
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.2)
    finally:
        await server.stop()

    assert await _count(session_factory, Position) == 2
    async with session_factory() as db:
        record = await db.scalar(select(DeviceSessionRecord))
        state = await db.get(DeviceState, device.id)
    assert record.packets == 2 and record.records == 4 and record.close_reason == "device_closed"
    assert state.online is False
