"""Servidor TCP asyncio para equipos Teltonika.

Ciclo de una conexión:
1. El equipo envía el IMEI → se autoriza → respuesta 0x01 / 0x00.
2. El equipo envía tramas AVL → se decodifican → se entregan al sink →
   ACK de 4 bytes con la cantidad aceptada (solo si el sink terminó bien).
3. Ping 0xFF: solo renueva last_seen.
4. Cualquier error de protocolo (CRC, estructura, codec desconocido) cierra
   la conexión SIN ACK: el equipo reconecta y reenvía los mismos datos.

Referencia Traccar: TrackerServer.java, ServerManager.java,
handler/network/AcknowledgementHandler.java
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from .config import GpsServerConfig
from .pipeline import DeviceAuthorizer, RecordSink
from .protocol.base import AvlPacket, DataFrame, Frame, ImeiFrame, PingFrame, ProtocolError
from .protocol.teltonika import (
    TeltonikaFrameDecoder,
    decode_data_frame,
    encode_imei_response,
    encode_records_ack,
)
from .session import ConnectionManager, DeviceSession

logger = logging.getLogger(__name__)

READ_CHUNK = 4096


class GpsServer:
    def __init__(
        self,
        config: GpsServerConfig,
        authorizer: DeviceAuthorizer,
        sink: RecordSink,
        connections: ConnectionManager | None = None,
    ) -> None:
        self.config = config
        self.authorizer = authorizer
        self.sink = sink
        self.connections = connections or ConnectionManager()
        self._server: asyncio.Server | None = None
        self._open_sockets = 0

    @property
    def port(self) -> int:
        """Puerto real (útil cuando se configura 0 en pruebas)."""
        if self._server is None or not self._server.sockets:
            raise RuntimeError("servidor no iniciado")
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.config.host, self.config.port)
        logger.info("Servidor GPS escuchando en %s:%d", self.config.host, self.port)

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    # ------------------------------------------------------------------ conexión

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = _peer_name(writer)
        if self._open_sockets >= self.config.max_connections:
            logger.warning("Límite de conexiones alcanzado; se rechaza %s", peer)
            await _close(writer)
            return

        self._open_sockets += 1
        session: DeviceSession | None = None
        decoder = TeltonikaFrameDecoder(self.config.max_frame_bytes)
        try:
            session = await self._handshake(reader, writer, peer, decoder)
            if session is not None:
                await self._receive_loop(reader, session, decoder)
        except TimeoutError:
            logger.info("Timeout de inactividad: %s", session.imei if session else peer)
        except ProtocolError as exc:
            logger.warning("Error de protocolo desde %s: %s", session.imei if session else peer, exc)
        except (ConnectionError, asyncio.IncompleteReadError):
            logger.info("Conexión cerrada por el equipo: %s", session.imei if session else peer)
        except Exception:
            logger.exception("Error procesando datos de %s; se cierra sin ACK", session.imei if session else peer)
        finally:
            self._open_sockets -= 1
            if session is not None:
                self.connections.unregister(session)
                logger.info("Sesión finalizada: IMEI %s (%d registros)", session.imei, session.records_received)
            await _close(writer)

    async def _handshake(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        peer: str,
        decoder: TeltonikaFrameDecoder,
    ) -> DeviceSession | None:
        frames: list[Frame] = []
        while not frames:
            chunk = await asyncio.wait_for(reader.read(READ_CHUNK), self.config.handshake_timeout_s)
            if not chunk:
                return None
            frames = decoder.feed(chunk)

        first = frames[0]
        if not isinstance(first, ImeiFrame):
            raise ProtocolError("la primera trama no es un IMEI")

        accepted = await self.authorizer.is_authorized(first.imei)
        writer.write(encode_imei_response(accepted))
        await writer.drain()
        if not accepted:
            logger.warning("IMEI no autorizado %s desde %s", first.imei, peer)
            return None

        session = DeviceSession(imei=first.imei, peer=peer, writer=writer)
        self.connections.register(session)
        logger.info("IMEI %s autenticado desde %s", first.imei, peer)

        # El equipo pudo enviar datos en el mismo segmento TCP que el IMEI.
        for frame in frames[1:]:
            await self._handle_frame(session, frame)
        return session

    async def _receive_loop(
        self, reader: asyncio.StreamReader, session: DeviceSession, decoder: TeltonikaFrameDecoder
    ) -> None:
        while True:
            chunk = await asyncio.wait_for(reader.read(READ_CHUNK), self.config.idle_timeout_s)
            if not chunk:
                return
            for frame in decoder.feed(chunk):
                await self._handle_frame(session, frame)

    async def _handle_frame(self, session: DeviceSession, frame: Frame) -> None:
        session.touch()
        if isinstance(frame, PingFrame):
            return
        if isinstance(frame, ImeiFrame):
            raise ProtocolError("IMEI repetido dentro de una sesión")
        if not isinstance(frame, DataFrame):
            raise ProtocolError(f"trama inesperada: {frame!r}")

        message = decode_data_frame(frame.raw)
        session.packets_received += 1
        if isinstance(message, AvlPacket):
            accepted = await self.sink.handle_packet(session, message)
            await session.send(encode_records_ack(accepted))
            session.records_received += accepted
        else:
            await self.sink.handle_command_response(session, message)


def _peer_name(writer: asyncio.StreamWriter) -> str:
    peer = writer.get_extra_info("peername")
    return f"{peer[0]}:{peer[1]}" if isinstance(peer, tuple) else str(peer)


async def _close(writer: asyncio.StreamWriter) -> None:
    if not writer.is_closing():
        writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()
