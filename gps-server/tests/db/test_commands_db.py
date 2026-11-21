"""Despachador de comandos contra MySQL (fase 6).

Criterio: pruebas simuladas primero; confirmación diferenciada de ejecución física
(la respuesta del equipo no basta, VERIFICADO exige DOUT1 observado).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from valkery_core.commands import SPECS, CommandType
from valkery_core.config import CoreSettings
from valkery_core.enums import CommandStatus
from valkery_core.models import Command, CommandResponse, DeviceState, Event
from valkery_gps.commands.dispatcher import CommandDispatcher
from valkery_gps.config import GpsServerConfig
from valkery_gps.handlers.database import DatabaseDeviceRegistry, DatabaseSink
from valkery_gps.protocol.base import AvlRecord
from valkery_gps.protocol.base import CommandResponse as Codec12Response
from valkery_gps.protocol.teltonika.avl_builder import (
    build_avl_frame,
    build_codec12_response,
    build_imei_frame,
    parse_codec12_command,
)
from valkery_gps.protocol.teltonika.decoder import decode_data_frame
from valkery_gps.protocol.teltonika.encoder import encode_codec12_command
from valkery_gps.protocol.teltonika.frame_decoder import TeltonikaFrameDecoder
from valkery_gps.server import GpsServer
from valkery_gps.session import ConnectionManager, DeviceSession

from ..conftest import TEST_IMEI

SETTINGS = CoreSettings(_env_file=None, commands_enabled=True, commands_relay_enabled=True)


def now() -> datetime:
    return datetime.now(UTC)


class FakeWriter:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[bytes] = []
        self.fail = fail

    def write(self, data: bytes) -> None:
        if self.fail:
            raise ConnectionResetError("socket cerrado")
        self.sent.append(data)

    async def drain(self) -> None:
        pass

    def is_closing(self) -> bool:
        return False

    def close(self) -> None:
        pass


def parked_record(dout1: int, at: datetime | None = None, ignition: int = 0) -> AvlRecord:
    return AvlRecord(
        timestamp=(at or now()).replace(microsecond=0),
        priority=0,
        longitude=-78.4678,
        latitude=-0.1807,
        altitude=2850,
        angle=0,
        satellites=10,
        speed=0,
        event_io_id=0,
        io={239: ignition, 240: 0, 69: 1, 179: dout1},
    )


async def setup(session_factory, device, *, online: bool = True, writer: FakeWriter | None = None):
    """Sesión conectada + estado de moto estacionada (vía el sink real)."""
    connections = ConnectionManager()
    dispatcher = CommandDispatcher(session_factory, connections, SETTINGS)
    sink = DatabaseSink(session_factory, commands=dispatcher)
    session = DeviceSession(imei=device.imei, device_id=device.id, peer="127.0.0.1:1", writer=writer or FakeWriter())
    await sink.session_opened(session)
    raw = build_avl_frame([parked_record(0)])
    await sink.handle_packet(session, decode_data_frame(raw), raw)
    if online:
        connections.register(session)
    return dispatcher, sink, session


async def add_command(session_factory, device, command_type: CommandType, **overrides) -> int:
    spec = SPECS[command_type]
    values = dict(
        device_id=device.id,
        command_type=command_type.value,
        command_text=spec.text(SETTINGS),
        status=CommandStatus.AUTORIZADO.value,
        expected_dout1=spec.expected_dout1,
        requested_at=now(),
        confirmed_at=now(),
        expires_at=now() + timedelta(seconds=60),
        preconditions=[],
    )
    values.update(overrides)
    async with session_factory.begin() as db:
        cmd = Command(**values)
        db.add(cmd)
        await db.flush()
        return cmd.id


async def get(session_factory, command_id: int) -> Command:
    async with session_factory() as db:
        return await db.get(Command, command_id)


async def respond(sink: DatabaseSink, session: DeviceSession, text: str) -> None:
    raw = build_codec12_response(text)
    await sink.handle_command_response(session, decode_data_frame(raw), raw)


async def event_types(session_factory) -> list[str]:
    async with session_factory() as db:
        return list((await db.scalars(select(Event.event_type).order_by(Event.id))).all())


# --------------------------------------------------------------------- consultas


async def test_diagnostic_command_roundtrip(session_factory, device):
    writer = FakeWriter()
    dispatcher, sink, session = await setup(session_factory, device, writer=writer)
    cid = await add_command(session_factory, device, CommandType.GET_VERSION)

    assert await dispatcher.dispatch_once() == 1
    assert writer.sent == [encode_codec12_command("getver")]
    cmd = await get(session_factory, cid)
    assert cmd.status == "ENVIADO" and cmd.sent_at and cmd.sent_frame == writer.sent[0]
    assert [p["stage"] for p in cmd.preconditions] == ["dispatch"] * len(cmd.preconditions)

    await respond(sink, session, "Code Ver:03.28.07")
    cmd = await get(session_factory, cid)
    assert cmd.status == "RESPUESTA_RECIBIDA" and cmd.finished_at is not None
    assert await event_types(session_factory) == []  # las consultas no generan eventos


# --------------------------------------------------------------------- relé


async def test_immobilize_verified_only_by_observed_dout1(session_factory, device):
    writer = FakeWriter()
    dispatcher, sink, session = await setup(session_factory, device, writer=writer)
    cid = await add_command(session_factory, device, CommandType.IMMOBILIZE)

    await dispatcher.dispatch_once()
    assert parse_codec12_command(writer.sent[0]) == "setdigout 1"

    await respond(sink, session, "DOUT1:1 Timeout:INFINITY")
    cmd = await get(session_factory, cid)
    assert cmd.status == "RESPUESTA_RECIBIDA" and cmd.finished_at is None  # la respuesta no basta

    # Registro antiguo (memoria del equipo) con DOUT1=1 anterior al envío: no verifica.
    old = build_avl_frame([parked_record(1, at=now() - timedelta(minutes=5))])
    await sink.handle_packet(session, decode_data_frame(old), old)
    assert (await get(session_factory, cid)).status == "RESPUESTA_RECIBIDA"

    fresh = build_avl_frame([parked_record(1, at=now() + timedelta(seconds=2))])
    await sink.handle_packet(session, decode_data_frame(fresh), fresh)
    cmd = await get(session_factory, cid)
    assert cmd.status == "VERIFICADO" and cmd.verification["dout1"] is True and cmd.verified_at
    assert await event_types(session_factory) == ["COMMAND_SENT", "COMMAND_RESPONSE", "COMMAND_VERIFIED"]
    async with session_factory() as db:
        assert (await db.get(DeviceState, device.id)).dout1 is True


async def test_offline_device_fails_instead_of_queueing(session_factory, device):
    dispatcher, _, _ = await setup(session_factory, device, online=False)
    cid = await add_command(session_factory, device, CommandType.IMMOBILIZE)
    assert await dispatcher.dispatch_once() == 0
    cmd = await get(session_factory, cid)
    assert cmd.status == "FALLIDO" and "Equipo conectado" in cmd.failure_reason
    # No queda nada pendiente para cuando el equipo vuelva.
    assert await dispatcher.dispatch_once() == 0


async def test_expired_command_is_not_sent(session_factory, device):
    writer = FakeWriter()
    dispatcher, _, _ = await setup(session_factory, device, writer=writer)
    cid = await add_command(session_factory, device, CommandType.IMMOBILIZE, expires_at=now() - timedelta(seconds=1))
    await dispatcher.dispatch_once()
    assert (await get(session_factory, cid)).status == "EXPIRADO" and writer.sent == []


async def test_state_changed_after_confirmation_rejects(session_factory, device):
    writer = FakeWriter()
    dispatcher, sink, session = await setup(session_factory, device, writer=writer)
    cid = await add_command(session_factory, device, CommandType.IMMOBILIZE)
    # Entre la confirmación y el envío, alguien enciende la moto.
    raw = build_avl_frame([parked_record(0, ignition=1, at=now() + timedelta(seconds=1))])
    await sink.handle_packet(session, decode_data_frame(raw), raw)

    await dispatcher.dispatch_once()
    cmd = await get(session_factory, cid)
    assert cmd.status == "RECHAZADO" and "Contacto apagado" in cmd.failure_reason
    assert writer.sent == []
    assert await event_types(session_factory) == ["IGNITION_ON", "COMMAND_FAILED"]


async def test_socket_error_marks_failed(session_factory, device):
    dispatcher, _, _ = await setup(session_factory, device, writer=FakeWriter(fail=True))
    cid = await add_command(session_factory, device, CommandType.GET_STATUS)
    await dispatcher.dispatch_once()
    assert (await get(session_factory, cid)).status == "FALLIDO"


async def test_error_response_fails(session_factory, device):
    dispatcher, sink, session = await setup(session_factory, device)
    cid = await add_command(session_factory, device, CommandType.IMMOBILIZE)
    await dispatcher.dispatch_once()
    await respond(sink, session, "Unknown command")
    cmd = await get(session_factory, cid)
    assert cmd.status == "FALLIDO" and "error" in cmd.failure_reason


async def test_timeouts_become_uncertain(session_factory, device):
    dispatcher, sink, session = await setup(session_factory, device)
    no_answer = await add_command(session_factory, device, CommandType.IMMOBILIZE)
    await dispatcher.dispatch_once()
    async with session_factory.begin() as db:
        cmd = await db.get(Command, no_answer)
        cmd.sent_at = now() - timedelta(minutes=5)
    assert await dispatcher.expire_once() == 1
    cmd = await get(session_factory, no_answer)
    assert cmd.status == "RESULTADO_INCIERTO" and "sin respuesta" in cmd.failure_reason

    unverified = await add_command(session_factory, device, CommandType.RELEASE)
    await dispatcher.dispatch_once()
    await respond(sink, session, "DOUT1:0 Timeout:INFINITY")
    async with session_factory.begin() as db:
        cmd = await db.get(Command, unverified)
        cmd.responded_at = now() - timedelta(minutes=10)
    await dispatcher.expire_once()
    cmd = await get(session_factory, unverified)
    assert cmd.status == "RESULTADO_INCIERTO" and "verificar en sitio" in cmd.failure_reason


async def test_unmatched_response_is_stored(session_factory, device):
    _, sink, session = await setup(session_factory, device)
    await respond(sink, session, "DOUT1:1 Timeout:INFINITY")
    async with session_factory() as db:
        row = await db.scalar(select(CommandResponse))
    assert row.result == "unmatched" and row.command_id is None


# --------------------------------------------------------------------- de punta a punta


async def test_end_to_end_immobilize_over_tcp(session_factory, device):
    """Servidor real + despachador + un cliente que actúa como el FMC920."""
    connections = ConnectionManager()
    dispatcher = CommandDispatcher(session_factory, connections, SETTINGS)
    sink = DatabaseSink(session_factory, commands=dispatcher)
    server = GpsServer(
        GpsServerConfig(host="127.0.0.1", port=0, handshake_timeout_s=2, idle_timeout_s=5),
        DatabaseDeviceRegistry(session_factory),
        sink,
        connections,
    )
    await server.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        writer.write(build_imei_frame(TEST_IMEI) + build_avl_frame([parked_record(0)]))
        await writer.drain()
        assert await reader.readexactly(5) == b"\x01" + (1).to_bytes(4, "big")

        cid = await add_command(session_factory, device, CommandType.IMMOBILIZE)
        assert await dispatcher.dispatch_once() == 1

        decoder = TeltonikaFrameDecoder()
        frames = []
        while not frames:
            frames = decoder.feed(await asyncio.wait_for(reader.read(4096), 5))
        assert parse_codec12_command(frames[0].raw) == "setdigout 1"

        writer.write(build_codec12_response("DOUT1:1 Timeout:INFINITY"))
        writer.write(build_avl_frame([parked_record(1, at=now() + timedelta(seconds=1))]))
        await writer.drain()
        assert int.from_bytes(await asyncio.wait_for(reader.readexactly(4), 5), "big") == 1

        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.2)
    finally:
        await server.stop()

    cmd = await get(session_factory, cid)
    assert cmd.status == "VERIFICADO"
    async with session_factory() as db:
        response = await db.scalar(select(CommandResponse).where(CommandResponse.command_id == cid))
    assert response.result == "ok" and response.raw_packet_id is not None


def test_codec12_response_type(pdf_example):
    assert isinstance(decode_data_frame(build_codec12_response("x")), Codec12Response)
