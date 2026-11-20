"""Simulador de un Teltonika FMC920 para probar el servidor sin hardware.

Envía el IMEI, espera la aceptación y luego manda paquetes AVL, verificando
el ACK de cada uno.

Ejemplos (desde la raíz del repo, con el servidor corriendo):
    python tools/device_simulator.py --imei 356307042441013
    python tools/device_simulator.py --codec 8e --records 3 --packets 5 --fragment 7
    python tools/device_simulator.py --pdf-example

Referencia Traccar: tools/test-generator.py
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gps-server"))

from valkery_gps.protocol.base import AvlRecord  # noqa: E402
from valkery_gps.protocol.teltonika.avl_builder import build_avl_frame, build_imei_frame  # noqa: E402
from valkery_gps.protocol.teltonika.decoder import CODEC_8, CODEC_8_EXT  # noqa: E402

# Ejemplo de la pág. 20 del PDF «FMB1YX Protocols V0.15» (IMEI de ejemplo del PDF, pág. 23).
PDF_EXAMPLE = bytes.fromhex(
    "000000000000008c08010000013feb55ff74000f0ea850209a690000940000120000001e09010002000300040016014703f0001504c8000c0900730a00460b00501300464306d7440000b5000bb60007422e9f180000cd0386ce000107c700000000f10000601a46000001344800000bb84900000bb84a00000bb84c00000000024e0000000000000000cf00000000000000000100003fca"
)


def make_records(count: int, start: datetime, lat: float, lon: float) -> list[AvlRecord]:
    records = []
    heading = random.randint(0, 359)
    for i in range(count):
        heading = (heading + random.randint(-20, 20)) % 360
        step = 0.0003
        lat += step * math.cos(math.radians(heading))
        lon += step * math.sin(math.radians(heading))
        records.append(
            AvlRecord(
                timestamp=start + timedelta(seconds=10 * i),
                priority=0,
                longitude=round(lon, 7),
                latitude=round(lat, 7),
                altitude=random.randint(5, 60),
                angle=heading,
                satellites=random.randint(7, 14),
                speed=random.randint(20, 60),
                event_io_id=0,
                io={239: 1, 240: 1, 21: 4, 69: 1, 179: 0, 66: 12600 + random.randint(0, 900), 67: 4000, 16: 1_000_000 + i * 80},
            )
        )
    return records


async def send(writer: asyncio.StreamWriter, data: bytes, fragment: int) -> None:
    if fragment <= 0:
        writer.write(data)
        await writer.drain()
        return
    for i in range(0, len(data), fragment):
        writer.write(data[i : i + fragment])
        await writer.drain()
        await asyncio.sleep(0.01)


async def run(args: argparse.Namespace) -> int:
    reader, writer = await asyncio.open_connection(args.host, args.port)
    try:
        await send(writer, build_imei_frame(args.imei), args.fragment)
        reply = await asyncio.wait_for(reader.readexactly(1), 10)
        if reply != b"\x01":
            print(f"IMEI rechazado por el servidor (respuesta {reply.hex()})")
            return 1
        print(f"IMEI {args.imei} aceptado")

        codec = CODEC_8_EXT if args.codec == "8e" else CODEC_8
        lat, lon = args.lat, args.lon
        start = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=10 * args.records * args.packets)
        for n in range(args.packets):
            if args.pdf_example:
                frame, expected = PDF_EXAMPLE, 1
            else:
                records = make_records(args.records, start + timedelta(seconds=10 * args.records * n), lat, lon)
                lat, lon = records[-1].latitude, records[-1].longitude
                frame, expected = build_avl_frame(records, codec), len(records)
            await send(writer, frame, args.fragment)
            ack = int.from_bytes(await asyncio.wait_for(reader.readexactly(4), 10), "big")
            status = "OK" if ack == expected else "DISCREPANCIA"
            print(f"paquete {n + 1}: {len(frame)} bytes, {expected} registros, ACK={ack} {status}")
            if ack != expected:
                return 1
            if args.ping:
                await send(writer, b"\xff", 0)
            await asyncio.sleep(args.interval)
        return 0
    finally:
        writer.close()
        await writer.wait_closed()


def main() -> None:
    p = argparse.ArgumentParser(description="Simulador FMC920 (Teltonika Codec 8/8E)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5027)
    p.add_argument("--imei", default="356307042441013", help="IMEI de prueba (no usar el real)")
    p.add_argument("--codec", choices=["8", "8e"], default="8e")
    p.add_argument("--records", type=int, default=2, help="registros por paquete")
    p.add_argument("--packets", type=int, default=3)
    p.add_argument("--interval", type=float, default=1.0, help="segundos entre paquetes")
    p.add_argument("--fragment", type=int, default=0, help="enviar en trozos de N bytes (0 = entero)")
    p.add_argument("--ping", action="store_true", help="enviar 0xFF tras cada paquete")
    p.add_argument("--pdf-example", action="store_true", help="enviar la trama de ejemplo del PDF")
    p.add_argument("--lat", type=float, default=54.6990336, help="latitud inicial (por defecto, la del PDF)")
    p.add_argument("--lon", type=float, default=25.2618832, help="longitud inicial (por defecto, la del PDF)")
    raise SystemExit(asyncio.run(run(p.parse_args())))


if __name__ == "__main__":
    main()
