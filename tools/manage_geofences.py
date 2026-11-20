"""Gestión de geocercas (hasta que exista la interfaz web en la fase 5).

Ejemplos (desde la raíz, con el venv activo):
    python tools/manage_geofences.py add-circle --name "Casa" --lat 54.6990 --lon 25.2618 --radius 150
    python tools/manage_geofences.py add-polygon --name "Barrio" --points "54.70,25.26;54.70,25.27;54.69,25.27;54.69,25.26"
    python tools/manage_geofences.py list
    python tools/manage_geofences.py disable --id 1
    python tools/manage_geofences.py enable --id 1

Por defecto la geocerca aplica a todos los dispositivos; usa --imei para limitarla a uno.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

from sqlalchemy import select  # noqa: E402

from valkery_core.db import create_engine, create_session_factory  # noqa: E402
from valkery_core.enums import GeofenceType  # noqa: E402
from valkery_core.geo import validate_polygon  # noqa: E402
from valkery_core.models import Device, DeviceGeofence, Geofence  # noqa: E402


async def _device_id(db, imei: str | None) -> int | None:
    if not imei:
        return None
    device_id = await db.scalar(select(Device.id).where(Device.imei == imei))
    if device_id is None:
        raise SystemExit("IMEI no registrado")
    return device_id


async def add(args: argparse.Namespace, factory) -> None:
    async with factory.begin() as db:
        device_id = await _device_id(db, args.imei)
        if args.command == "add-circle":
            if not (-90 <= args.lat <= 90 and -180 <= args.lon <= 180) or args.radius <= 0:
                raise SystemExit("Centro o radio inválido")
            fence = Geofence(
                name=args.name,
                geofence_type=GeofenceType.CIRCLE.value,
                center_lat=args.lat,
                center_lon=args.lon,
                radius_m=args.radius,
                device_id=device_id,
            )
        else:
            try:
                raw = [[float(v) for v in pair.split(",")] for pair in args.points.split(";") if pair.strip()]
                polygon = validate_polygon(raw)
            except ValueError as exc:
                raise SystemExit(f"Polígono inválido: {exc}") from exc
            fence = Geofence(
                name=args.name,
                geofence_type=GeofenceType.POLYGON.value,
                points=[list(p) for p in polygon],
                device_id=device_id,
            )
        db.add(fence)
        await db.flush()
        print(f"Geocerca {fence.id} '{fence.name}' creada ({fence.geofence_type})")


async def list_fences(factory) -> None:
    async with factory() as db:
        fences = (await db.scalars(select(Geofence).order_by(Geofence.id))).all()
        states = (await db.scalars(select(DeviceGeofence))).all()
    if not fences:
        print("No hay geocercas")
    inside = {}
    for s in states:
        inside.setdefault(s.geofence_id, []).append(f"disp.{s.device_id}={'dentro' if s.inside else 'fuera'}")
    for f in fences:
        shape = (
            f"círculo r={f.radius_m} m en {f.center_lat:.6f},{f.center_lon:.6f}"
            if f.geofence_type == GeofenceType.CIRCLE
            else f"polígono de {len(f.points or [])} vértices"
        )
        scope = f"disp.{f.device_id}" if f.device_id else "todos"
        status = "habilitada" if f.enabled else "DESHABILITADA"
        print(f"{f.id:>3}  {f.name:<20} {shape:<45} {scope:<8} {status:<13} {' '.join(inside.get(f.id, []))}")


async def set_enabled(args: argparse.Namespace, factory, enabled: bool) -> None:
    async with factory.begin() as db:
        fence = await db.get(Geofence, args.id)
        if fence is None:
            raise SystemExit("Geocerca inexistente")
        fence.enabled = enabled
        print(f"Geocerca {fence.id} {'habilitada' if enabled else 'deshabilitada'}")


async def main_async(args: argparse.Namespace) -> None:
    engine = create_engine()
    factory = create_session_factory(engine)
    try:
        if args.command in ("add-circle", "add-polygon"):
            await add(args, factory)
        elif args.command == "list":
            await list_fences(factory)
        else:
            await set_enabled(args, factory, args.command == "enable")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocercas VALKERY GPS")
    sub = parser.add_subparsers(dest="command", required=True)

    circle = sub.add_parser("add-circle")
    circle.add_argument("--name", required=True)
    circle.add_argument("--lat", type=float, required=True)
    circle.add_argument("--lon", type=float, required=True)
    circle.add_argument("--radius", type=int, required=True, help="metros")
    circle.add_argument("--imei", help="limitar a un dispositivo")

    polygon = sub.add_parser("add-polygon")
    polygon.add_argument("--name", required=True)
    polygon.add_argument("--points", required=True, help='"lat,lon;lat,lon;lat,lon"')
    polygon.add_argument("--imei", help="limitar a un dispositivo")

    sub.add_parser("list")
    for name in ("enable", "disable"):
        p = sub.add_parser(name)
        p.add_argument("--id", type=int, required=True)

    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
