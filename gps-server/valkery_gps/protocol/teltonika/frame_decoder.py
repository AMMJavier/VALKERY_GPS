"""Reconstruye tramas Teltonika a partir del flujo TCP.

TCP entrega bytes, no mensajes: una lectura puede traer media trama o varias.
Este decodificador acumula bytes y devuelve solo tramas completas.

Tipos de trama (se distinguen por los primeros bytes):
- Ping:  un único byte 0xFF.
- IMEI:  longitud en 2 bytes (> 0) + IMEI en ASCII.
- Datos: 4 bytes en cero + longitud en 4 bytes + datos + CRC en 4 bytes
         (tamaño total = longitud + 12). Sirve para AVL y Codec 12.

Referencia Traccar: protocol/TeltonikaFrameDecoder.java
"""

from __future__ import annotations

from ..base import DataFrame, Frame, FrameTooLargeError, ImeiFrame, PingFrame, ProtocolError

PING_BYTE = 0xFF
IMEI_MAX_LENGTH = 17  # IMEI estándar = 15 dígitos; margen para variantes
DATA_HEADER_LENGTH = 8  # preámbulo + longitud
DATA_OVERHEAD = 12  # cabecera + CRC
DEFAULT_MAX_FRAME_BYTES = 64 * 1024


class TeltonikaFrameDecoder:
    def __init__(self, max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES) -> None:
        self._buffer = bytearray()
        self._max_frame_bytes = max_frame_bytes

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, data: bytes) -> list[Frame]:
        """Agrega bytes recibidos y devuelve las tramas completas disponibles."""
        self._buffer.extend(data)
        frames: list[Frame] = []
        while True:
            frame = self._next_frame()
            if frame is None:
                return frames
            frames.append(frame)

    def _next_frame(self) -> Frame | None:
        buf = self._buffer
        if not buf:
            return None

        if buf[0] == PING_BYTE:
            del buf[:1]
            return PingFrame()

        if len(buf) < 2:
            return None

        imei_length = int.from_bytes(buf[0:2], "big")
        if imei_length > 0:
            return self._take_imei(imei_length)
        return self._take_data()

    def _take_imei(self, length: int) -> ImeiFrame | None:
        if length > IMEI_MAX_LENGTH:
            raise ProtocolError(f"longitud de IMEI inválida: {length}")
        total = 2 + length
        if len(self._buffer) < total:
            return None
        raw = bytes(self._buffer[2:total])
        del self._buffer[:total]
        if not raw.isdigit():
            raise ProtocolError("el IMEI contiene caracteres no numéricos")
        return ImeiFrame(imei=raw.decode("ascii"))

    def _take_data(self) -> DataFrame | None:
        buf = self._buffer
        if len(buf) < DATA_HEADER_LENGTH:
            return None
        if any(buf[0:4]):
            raise ProtocolError("preámbulo de datos distinto de 4 ceros")
        data_length = int.from_bytes(buf[4:8], "big")
        total = data_length + DATA_OVERHEAD
        if data_length == 0 or total > self._max_frame_bytes:
            raise FrameTooLargeError(f"longitud de datos inválida: {data_length}")
        if len(buf) < total:
            return None
        raw = bytes(buf[:total])
        del buf[:total]
        return DataFrame(raw=raw)
