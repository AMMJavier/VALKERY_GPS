"""Servidor TCP asyncio para equipos Teltonika.

Ciclo de una conexión:
1. El equipo envía el IMEI → se autoriza contra el registro → 0x01 / 0x00.
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

from valkery_core.enums import CloseReason

from .config import GpsServerConfig
from .pipeline import DeviceRegistry, RecordSink
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
SHUTDOWN_GRACE_S = 5


class GpsServer:
    def __init__(
        self,
        config: GpsServerConfig,
        registry: DeviceRegistry,
        sink: RecordSink,
        connections: ConnectionManager | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.sink = sink
        # `or` no sirve: un ConnectionManager vacío es falso (define __len__).
        self.connections = connections if connections is not None else ConnectionManager()
        self._server: asyncio.Server | None = None
        self._open_sockets = 0
        self._tasks: set[asyncio.Task] = set()

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
        await self._server.serve_forever()

    async def stop(self) -> None:
        """Deja de aceptar conexiones y cierra las sesiones abiertas registrándolas."""
        if self._server is not None:
            self._server.close()
        for session in self.connections.all():
            session.close(CloseReason.SERVER_SHUTDOWN)
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=SHUTDOWN_GRACE_S)
        if self._server is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._server.wait_closed(), SHUTDOWN_GRACE_S)

    # ------------------------------------------------------------------ conexión

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        peer = _peer_name(writer)
        if self._open_sockets >= self.config.max_connections:
            logger.warning("Límite de conexiones alcanzado; se rechaza %s", peer)
            await _close(writer)
            return

        self._open_sockets += 1
        session: DeviceSession | None = None
        reason = CloseReason.DEVICE_CLOSED.value
        decoder = TeltonikaFrameDecoder(self.config.max_frame_bytes)
        try:
            session, pending = await self._handshake(reader, writer, peer, decoder)
            if session is not None:
                # El equipo pudo enviar datos en el mismo segmento TCP que el IMEI.
                # Se procesan aquí (no dentro del handshake) para que un error
                # en ellos cierre la sesión ya registrada.
                for frame in pending:
                    await self._handle_frame(session, frame)
                await self._receive_loop(reader, session, decoder)
        except TimeoutError:
            reason = CloseReason.IDLE_TIMEOUT.value
            logger.info("Timeout de inactividad: %s", session.imei if session else peer)
        except ProtocolError as exc:
            reason = f"{CloseReason.PROTOCOL_ERROR.value}: {exc}"
            logger.warning("Error de protocolo desde %s: %s", session.imei if session else peer, exc)
        except (ConnectionError, asyncio.IncompleteReadError):
            logger.info("Conexión cerrada por el equipo: %s", session.imei if session else peer)
        except Exception as exc:
            reason = f"{CloseReason.PROCESSING_ERROR.value}: {type(exc).__name__}"
            logger.exception("Error procesando datos de %s; se cierra sin ACK", session.imei if session else peer)
        finally:
            self._open_sockets -= 1
            await _close(writer)
            if session is not None:
                await self._finish_session(session, session.close_reason or reason)

    async def _finish_session(self, session: DeviceSession, reason: str) -> None:
        self.connections.unregister(session)
        still_online = self.connections.get(session.imei) is not None
        try:
            await self.sink.session_closed(session, reason[:255], still_online)
        except Exception:
            logger.exception("No se pudo registrar el cierre de sesión de %s", session.imei)
        logger.info(
            "Sesión finalizada: IMEI %s (%d registros, motivo: %s)", session.imei, session.records_received, reason
        )

    async def _handshake(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        peer: str,
        decoder: TeltonikaFrameDecoder,
    ) -> tuple[DeviceSession | None, list[Frame]]:
        frames: list[Frame] = []
        while not frames:
            chunk = await asyncio.wait_for(reader.read(READ_CHUNK), self.config.handshake_timeout_s)
            if not chunk:
                return None, []
            frames = decoder.feed(chunk)

        first = frames[0]
        if not isinstance(first, ImeiFrame):
            raise ProtocolError("la primera trama no es un IMEI")

        device_id = await self.registry.authorize(first.imei)
        writer.write(encode_imei_response(device_id is not None))
        await writer.drain()
        if device_id is None:
            logger.warning("IMEI no autorizado %s desde %s", first.imei, peer)
            return None, []

        session = DeviceSession(imei=first.imei, device_id=device_id, peer=peer, writer=writer)
        self.connections.register(session)
        logger.info("IMEI %s autenticado desde %s", first.imei, peer)
        try:
            await self.sink.session_opened(session)
        except Exception:
            self.connections.unregister(session)
            raise
        return session, frames[1:]

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

        try:
            message = decode_data_frame(frame.raw)
        except ProtocolError as exc:
            try:
                await self.sink.packet_rejected(session, frame.raw, exc)
            except Exception:
                logger.exception("No se pudo guardar la trama rechazada de %s", session.imei)
            raise

        session.packets_received += 1
        if isinstance(message, AvlPacket):
            accepted = await self.sink.handle_packet(session, message, frame.raw)
            await session.send(encode_records_ack(accepted))
            session.records_received += accepted
        else:
            await self.sink.handle_command_response(session, message, frame.raw)


def _peer_name(writer: asyncio.StreamWriter) -> str:
    peer = writer.get_extra_info("peername")
    return f"{peer[0]}:{peer[1]}" if isinstance(peer, tuple) else str(peer)


async def _close(writer: asyncio.StreamWriter) -> None:
    if not writer.is_closing():
        writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()
