"""Simulador de un Teltonika FMC920 para probar el servidor sin hardware.

Envía el IMEI, espera la aceptación y luego manda paquetes AVL, verificando
el ACK de cada uno.

Ejemplos (desde la raíz del repo, con el servidor corriendo):
    python tools/device_simulator.py --imei 356307042441013
    python tools/device_simulator.py --codec 8e --records 3 --packets 5 --fragment 7
    python tools/device_simulator.py --pdf-example
    python tools/device_simulator.py --scenario trip --records 4
    python tools/device_simulator.py --scenario parked --respond-commands 120

Escenario "parked" + --respond-commands (fase 6): moto detenida con contacto
apagado y datos actuales; la conexión queda abierta y el simulador responde a
los comandos Codec 12 como el FMC920 ("setdigout N" → "DOUT1:N ...") y luego
envía un registro con DOUT1 (I/O 179) para que el servidor pueda verificarlo.

Escenario "trip" (para probar eventos, fase 3): moto estacionada con
contacto apagado → enciende → se aleja ~600 m hacia el norte → se detiene y
apaga → alarma de remolque (I/O 246). Con una geocerca circular de 150 m en
el punto de partida produce: IGNITION_ON, GEOFENCE_EXIT, IGNITION_OFF, TOWING.

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
from valkery_gps.protocol.teltonika.avl_builder import (  # noqa: E402
    build_avl_frame,
    build_codec12_response,
    build_imei_frame,
    parse_codec12_command,
)
from valkery_gps.protocol.teltonika.frame_decoder import TeltonikaFrameDecoder  # noqa: E402
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


def make_trip(start: datetime, lat: float, lon: float) -> list[AvlRecord]:
    """Recorrido determinista: 3 parado, encendido, 12 en marcha, parada, apagado, remolque."""
    step_deg = 50 / 111_320  # ~50 m hacia el norte por registro
    records: list[AvlRecord] = []

    def add(ignition: int, speed: int, moved: int, event_io_id: int = 0, extra: dict | None = None) -> None:
        io = {239: ignition, 240: 1 if speed else 0, 21: 4, 69: 1, 179: 0, 66: 12800 if ignition else 12400}
        io.update(extra or {})
        records.append(
            AvlRecord(
                timestamp=start + timedelta(seconds=10 * len(records)),
                priority=1 if event_io_id else 0,
                longitude=round(lon, 7),
                latitude=round(lat + moved * step_deg, 7),
                altitude=20,
                angle=0,
                satellites=10,
                speed=speed,
                event_io_id=event_io_id,
                io=io,
            )
        )

    for _ in range(3):
        add(ignition=0, speed=0, moved=0)
    add(ignition=1, speed=0, moved=0, event_io_id=239)
    for i in range(1, 13):
        add(ignition=1, speed=30, moved=i)
    add(ignition=1, speed=0, moved=12)
    add(ignition=0, speed=0, moved=12, event_io_id=239)
    add(ignition=0, speed=0, moved=12, event_io_id=246, extra={246: 1})
    return records


def parked_record(lat: float, lon: float, dout1: int, event_io_id: int = 0) -> AvlRecord:
    """Registro actual de la moto estacionada: contacto apagado, velocidad 0, sin movimiento."""
    return AvlRecord(
        timestamp=datetime.now(UTC).replace(microsecond=0),
        priority=1 if event_io_id else 0,
        longitude=lon,
        latitude=lat,
        altitude=2850,
        angle=0,
        satellites=11,
        speed=0,
        event_io_id=event_io_id,
        io={239: 0, 240: 0, 21: 4, 69: 1, 179: dout1, 66: 12500, 67: 4100},
    )


def command_reply(text: str, dout1: int) -> tuple[str, int]:
    """Imita las respuestas del FMC920 a los comandos de la plataforma."""
    parts = text.strip().split()
    if parts and parts[0] == "setdigout" and len(parts) > 1 and parts[1][:1] in "01":
        dout1 = int(parts[1][0])
        return f"DOUT1:{dout1} Timeout:INFINITY", dout1
    replies = {
        "getver": "Code Ver:03.28.07 Rev:00 Device:FMC920 (simulador)",
        "getstatus": "Data Link: 1 GPRS: 1 Phone: 0 SIM: 0 OP: 74000 Signal: 4",
        "getinfo": "INI:2026/11/20 RTC:2026/11/20 RST:0 ERR:0 SR:0 BR:0 CF:0 FG:0 FL:0 TU:0/0 UT:0 SMS:0 NOGPS:0:0 GPS:3 SAT:11",
    }
    return replies.get(text.strip(), f"Unknown command: {text.strip()}"), dout1


async def respond_commands(reader, writer, args, lat: float, lon: float) -> None:
    decoder = TeltonikaFrameDecoder()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + args.respond_commands
    dout1 = args.dout1
    print(f"Esperando comandos durante {args.respond_commands:.0f} s…")
    while (remaining := deadline - loop.time()) > 0:
        try:
            chunk = await asyncio.wait_for(reader.read(4096), min(remaining, 20))
        except TimeoutError:
            # mantener la conexión y el estado "reciente" con un registro periódico
            await send(writer, build_avl_frame([parked_record(lat, lon, dout1)]), 0)
            await asyncio.wait_for(reader.readexactly(4), 10)
            continue
        if not chunk:
            print("El servidor cerró la conexión")
            return
        for frame in decoder.feed(chunk):
            raw = getattr(frame, "raw", None)
            if raw is None:
                continue
            text = parse_codec12_command(raw)
            reply, dout1 = command_reply(text, dout1)
            print(f"Comando recibido: {text!r} → respuesta {reply!r}")
            await send(writer, build_codec12_response(reply), 0)
            if text.startswith("setdigout"):
                await asyncio.sleep(1)
                await send(writer, build_avl_frame([parked_record(lat, lon, dout1, event_io_id=179)]), 0)
                ack = int.from_bytes(await asyncio.wait_for(reader.readexactly(4), 10), "big")
                print(f"Registro con DOUT1={dout1} enviado (ACK={ack})")


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
        if args.scenario == "parked":
            args.packets = 1
        if args.scenario == "trip":
            trip = make_trip(datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=5), lat, lon)
            chunks = [trip[i : i + args.records] for i in range(0, len(trip), args.records)]
            args.packets = len(chunks)
        for n in range(args.packets):
            if args.pdf_example:
                frame, expected = PDF_EXAMPLE, 1
            elif args.scenario == "parked":
                frame, expected = build_avl_frame([parked_record(lat, lon, args.dout1)], codec), 1
            elif args.scenario == "trip":
                frame, expected = build_avl_frame(chunks[n], codec), len(chunks[n])
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
        if args.respond_commands > 0:
            await respond_commands(reader, writer, args, lat, lon)
        return 0
    except (ConnectionError, asyncio.IncompleteReadError):
        print("La conexión con el servidor se cerró")
        return 1
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass


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
    p.add_argument("--scenario", choices=["random", "trip", "parked"], default="random", help="trip: recorrido; parked: detenida")
    p.add_argument("--respond-commands", type=float, default=0, help="segundos esperando y respondiendo comandos Codec 12")
    p.add_argument("--dout1", type=int, choices=[0, 1], default=0, help="estado inicial simulado de DOUT1")
    p.add_argument("--lat", type=float, default=54.6990336, help="latitud inicial (por defecto, la del PDF)")
    p.add_argument("--lon", type=float, default=25.2618832, help="longitud inicial (por defecto, la del PDF)")
    raise SystemExit(asyncio.run(run(p.parse_args())))


if __name__ == "__main__":
    main()
