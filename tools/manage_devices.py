"""Registro de vehículos y dispositivos en la base de datos.

Solo los IMEIs registrados y habilitados pueden conectarse al servidor GPS.
El IMEI real se carga con esta herramienta y nunca se guarda en el repositorio.

Ejemplos (desde la raíz, con el venv activo):
    python tools/manage_devices.py add --imei 356307042441013 --name "Simulador" --vehicle "Moto de prueba"
    python tools/manage_devices.py list
    python tools/manage_devices.py disable --imei 356307042441013
    python tools/manage_devices.py enable --imei 356307042441013
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

from sqlalchemy import select  # noqa: E402

from valkery_core.db import create_engine, create_session_factory  # noqa: E402
from valkery_core.models import Device, DeviceState, Vehicle  # noqa: E402


async def add(args: argparse.Namespace, factory) -> None:
    if not args.imei.isdigit() or not 14 <= len(args.imei) <= 17:
        raise SystemExit("IMEI inválido: deben ser 14 a 17 dígitos")
    async with factory.begin() as db:
        if await db.scalar(select(Device.id).where(Device.imei == args.imei)):
            raise SystemExit("Ese IMEI ya está registrado")
        vehicle = None
        if args.vehicle:
            vehicle = Vehicle(alias=args.vehicle, vehicle_type=args.vehicle_type, plate=args.plate)
            db.add(vehicle)
            await db.flush()
        device = Device(
            imei=args.imei,
            name=args.name,
            model=args.model,
            vehicle_id=vehicle.id if vehicle else None,
            enabled=True,
        )
        db.add(device)
        await db.flush()
        print(f"Dispositivo {device.id} registrado ({args.model}, IMEI ...{args.imei[-4:]})")


async def set_enabled(args: argparse.Namespace, factory, enabled: bool) -> None:
    async with factory.begin() as db:
        device = await db.scalar(select(Device).where(Device.imei == args.imei))
        if device is None:
            raise SystemExit("IMEI no registrado")
        device.enabled = enabled
        print(f"Dispositivo {device.id} {'habilitado' if enabled else 'deshabilitado'}")


async def list_devices(factory) -> None:
    async with factory() as db:
        rows = (
            await db.execute(
                select(Device, Vehicle.alias, DeviceState)
                .outerjoin(Vehicle, Vehicle.id == Device.vehicle_id)
                .outerjoin(DeviceState, DeviceState.device_id == Device.id)
                .order_by(Device.id)
            )
        ).all()
    if not rows:
        print("No hay dispositivos registrados")
    for device, alias, state in rows:
        online = "en línea" if state and state.online else "desconectado"
        seen = state.last_seen.isoformat(timespec="seconds") if state and state.last_seen else "nunca"
        print(
            f"{device.id:>3}  IMEI ...{device.imei[-4:]}  {device.name:<20} {device.model:<8} "
            f"{'habilitado' if device.enabled else 'DESHABILITADO':<13} vehículo={alias or '-':<15} "
            f"{online}, visto: {seen}"
        )


async def main_async(args: argparse.Namespace) -> None:
    engine = create_engine()
    factory = create_session_factory(engine)
    try:
        if args.command == "add":
            await add(args, factory)
        elif args.command == "list":
            await list_devices(factory)
        else:
            await set_enabled(args, factory, args.command == "enable")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestión de dispositivos VALKERY GPS")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="registrar un dispositivo")
    p_add.add_argument("--imei", required=True)
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--model", default="FMC920")
    p_add.add_argument("--vehicle", help="alias del vehículo (lo crea)")
    p_add.add_argument("--vehicle-type", default="motorcycle")
    p_add.add_argument("--plate")

    sub.add_parser("list", help="listar dispositivos")
    for name in ("enable", "disable"):
        p = sub.add_parser(name)
        p.add_argument("--imei", required=True)

    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
