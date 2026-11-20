"""Pruebas de integración del servidor TCP con un cliente real sobre localhost."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from valkery_gps.config import GpsServerConfig
from valkery_gps.pipeline import AllowListAuthorizer
from valkery_gps.protocol.base import AvlPacket, AvlRecord, CommandResponse
from valkery_gps.protocol.teltonika.avl_builder import build_avl_frame, build_imei_frame
from valkery_gps.protocol.teltonika.crc import crc16_ibm
from valkery_gps.protocol.teltonika.decoder import CODEC_8_EXT
from valkery_gps.server import GpsServer
from valkery_gps.session.device_session import DeviceSession

from .conftest import TEST_IMEI


class RecordingSink:
    def __init__(self, fail: bool = False) -> None:
        self.packets: list[AvlPacket] = []
        self.responses: list[CommandResponse] = []
        self.fail = fail

    async def handle_packet(self, session: DeviceSession, packet: AvlPacket) -> int:
        if self.fail:
            raise RuntimeError("base de datos caída")
        self.packets.append(packet)
        return len(packet.records)

    async def handle_command_response(self, session: DeviceSession, response: CommandResponse) -> None:
        self.responses.append(response)


@contextlib.asynccontextmanager
async def running_server(sink: RecordingSink, **config):
    settings = {"host": "127.0.0.1", "port": 0, "handshake_timeout_s": 2, "idle_timeout_s": 2, **config}
    cfg = GpsServerConfig(**settings)
    server = GpsServer(cfg, AllowListAuthorizer(frozenset({TEST_IMEI})), sink)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


async def connect(server: GpsServer):
    return await asyncio.open_connection("127.0.0.1", server.port)


async def read_eof(reader: asyncio.StreamReader) -> bytes:
    return await asyncio.wait_for(reader.read(), 3)


def _records(n: int) -> list[AvlRecord]:
    return [
        AvlRecord(
            timestamp=datetime(2026, 11, 20, 12, 0, i, tzinfo=UTC),
            priority=0,
            longitude=25.0 + i / 1000,
            latitude=54.0,
            altitude=100,
            angle=90,
            satellites=10,
            speed=30,
            event_io_id=0,
            io={239: 1, 240: 1},
        )
        for i in range(n)
    ]


async def test_handshake_and_ack_fragmented(pdf_example):
    sink = RecordingSink()
    async with running_server(sink) as server:
        reader, writer = await connect(server)
        for chunk in (b"\x00", build_imei_frame(TEST_IMEI)[1:]):
            writer.write(chunk)
            await writer.drain()
        assert await asyncio.wait_for(reader.readexactly(1), 3) == b"\x01"

        for i in range(0, len(pdf_example), 7):
            writer.write(pdf_example[i : i + 7])
            await writer.drain()
            await asyncio.sleep(0)
        assert await asyncio.wait_for(reader.readexactly(4), 3) == b"\x00\x00\x00\x01"
        assert server.connections.is_online(TEST_IMEI)

        writer.close()
        await writer.wait_closed()
    assert len(sink.packets) == 1


async def test_imei_and_data_in_same_segment_and_multiple_packets():
    sink = RecordingSink()
    async with running_server(sink) as server:
        reader, writer = await connect(server)
        frame3 = build_avl_frame(_records(3), CODEC_8_EXT)
        frame2 = build_avl_frame(_records(2))
        writer.write(build_imei_frame(TEST_IMEI) + frame3 + b"\xff" + frame2)
        await writer.drain()
        assert await asyncio.wait_for(reader.readexactly(9), 3) == b"\x01" + (3).to_bytes(4, "big") + (2).to_bytes(4, "big")
        writer.close()
        await writer.wait_closed()
    assert [len(p.records) for p in sink.packets] == [3, 2]


async def test_unknown_imei_rejected():
    async with running_server(RecordingSink()) as server:
        reader, writer = await connect(server)
        writer.write(build_imei_frame("123456789012345"))
        await writer.drain()
        assert await read_eof(reader) == b"\x00"
        assert len(server.connections) == 0


async def test_data_before_imei_closes_connection(pdf_example):
    sink = RecordingSink()
    async with running_server(sink) as server:
        reader, writer = await connect(server)
        writer.write(pdf_example)
        await writer.drain()
        assert await read_eof(reader) == b""
    assert sink.packets == []


async def test_crc_error_closes_without_ack(pdf_example):
    sink = RecordingSink()
    async with running_server(sink) as server:
        reader, writer = await connect(server)
        corrupted = bytearray(pdf_example)
        corrupted[40] ^= 0x01
        writer.write(build_imei_frame(TEST_IMEI) + bytes(corrupted))
        await writer.drain()
        assert await read_eof(reader) == b"\x01"  # solo la aceptación del IMEI
    assert sink.packets == []


async def test_sink_failure_means_no_ack(pdf_example):
    async with running_server(RecordingSink(fail=True)) as server:
        reader, writer = await connect(server)
        writer.write(build_imei_frame(TEST_IMEI) + pdf_example)
        await writer.drain()
        assert await read_eof(reader) == b"\x01"


async def test_idle_timeout_closes_session():
    async with running_server(RecordingSink(), idle_timeout_s=1) as server:
        reader, writer = await connect(server)
        writer.write(build_imei_frame(TEST_IMEI))
        await writer.drain()
        assert await read_eof(reader) == b"\x01"
        await asyncio.sleep(0.05)
        assert not server.connections.is_online(TEST_IMEI)


async def test_reconnect_replaces_previous_session():
    async with running_server(RecordingSink()) as server:
        r1, w1 = await connect(server)
        w1.write(build_imei_frame(TEST_IMEI))
        await w1.drain()
        assert await r1.readexactly(1) == b"\x01"
        first = server.connections.get(TEST_IMEI)

        r2, w2 = await connect(server)
        w2.write(build_imei_frame(TEST_IMEI))
        await w2.drain()
        assert await r2.readexactly(1) == b"\x01"

        assert await read_eof(r1) == b""  # la sesión vieja se cerró
        await asyncio.sleep(0.05)
        current = server.connections.get(TEST_IMEI)
        assert current is not None and current is not first
        w2.close()
        await w2.wait_closed()


async def test_codec12_response_routed_to_sink():
    sink = RecordingSink()
    async with running_server(sink) as server:
        reader, writer = await connect(server)
        text = b"DOUT1:0"
        body = bytes([0x0C, 1, 0x06]) + len(text).to_bytes(4, "big") + text + b"\x01"
        frame = b"\x00" * 4 + len(body).to_bytes(4, "big") + body + crc16_ibm(body).to_bytes(4, "big")
        writer.write(build_imei_frame(TEST_IMEI) + frame)
        await writer.drain()
        assert await reader.readexactly(1) == b"\x01"
        for _ in range(50):
            if sink.responses:
                break
            await asyncio.sleep(0.02)
        writer.close()
        await writer.wait_closed()
    assert sink.responses[0].text == "DOUT1:0"


async def test_connection_limit():
    async with running_server(RecordingSink(), max_connections=1) as server:
        r1, w1 = await connect(server)
        w1.write(build_imei_frame(TEST_IMEI))
        await w1.drain()
        assert await r1.readexactly(1) == b"\x01"

        r2, _ = await connect(server)
        assert await read_eof(r2) == b""
        w1.close()
        await w1.wait_closed()
