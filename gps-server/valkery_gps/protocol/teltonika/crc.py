"""CRC-16/IBM (también llamado CRC-16/ARC) usado por Teltonika.

Polinomio 0x8005 reflejado (0xA001), valor inicial 0x0000, sin XOR final.
Se calcula sobre [codec id .. número de datos 2] y se transmite en 4 bytes
cuyo par alto es siempre cero.

Referencia Traccar: helper/Checksum.java (CRC16_IBM)
"""

from __future__ import annotations


def _build_table() -> tuple[int, ...]:
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        table.append(crc)
    return tuple(table)


_TABLE = _build_table()


def crc16_ibm(data: bytes | bytearray | memoryview) -> int:
    crc = 0
    for byte in data:
        crc = (crc >> 8) ^ _TABLE[(crc ^ byte) & 0xFF]
    return crc
