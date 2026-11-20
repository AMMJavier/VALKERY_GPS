"""Consulta de eventos y configuración de reglas.

Ejemplos (desde la raíz, con el venv activo):
    python tools/manage_events.py list --limit 30
    python tools/manage_events.py list --type IGNITION_ON
    python tools/manage_events.py rules
    python tools/manage_events.py set-rule --type GEOFENCE_ENTER --disable
    python tools/manage_events.py set-rule --type GEOFENCE_EXIT --severity critical
    python tools/manage_events.py set-rule --type DEVICE_OFFLINE --enable --imei 356307042441013
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

from sqlalchemy import select  # noqa: E402

from valkery_core.db import create_engine, create_session_factory  # noqa: E402
from valkery_core.enums import DEFAULT_SEVERITY, EventType, Severity  # noqa: E402
from valkery_core.models import Device, Event, EventRule  # noqa: E402


async def list_events(args: argparse.Namespace, factory) -> None:
    query = select(Event).order_by(Event.occurred_at.desc(), Event.id.desc()).limit(args.limit)
    if args.type:
        query = query.where(Event.event_type == args.type)
    async with factory() as db:
        events = (await db.scalars(query)).all()
    if not events:
        print("No hay eventos")
    for e in reversed(events):
        extra = {k: v for k, v in e.attributes.items() if k not in ("latitude", "longitude")}
        where = (
            f"{e.attributes['latitude']:.6f},{e.attributes['longitude']:.6f}" if "latitude" in e.attributes else ""
        )
        print(
            f"{e.occurred_at.isoformat(timespec='seconds')}  disp.{e.device_id}  {e.event_type:<15} "
            f"{e.severity:<8} {e.source:<8} {where:<22} {extra or ''}"
        )


async def list_rules(factory) -> None:
    async with factory() as db:
        rules = {(r.event_type, r.device_id): r for r in (await db.scalars(select(EventRule))).all()}
    print(f"{'tipo':<16} {'por defecto':<12} reglas")
    for event_type in EventType:
        applied = [
            f"{'global' if dev is None else f'disp.{dev}'}: "
            f"{'ON' if r.enabled else 'OFF'}{f' ({r.severity})' if r.severity else ''}"
            for (t, dev), r in rules.items()
            if t == event_type.value
        ]
        print(f"{event_type.value:<16} {DEFAULT_SEVERITY[event_type].value:<12} {', '.join(applied) or '-'}")


async def set_rule(args: argparse.Namespace, factory) -> None:
    async with factory.begin() as db:
        device_id = None
        if args.imei:
            device_id = await db.scalar(select(Device.id).where(Device.imei == args.imei))
            if device_id is None:
                raise SystemExit("IMEI no registrado")
        condition = EventRule.device_id.is_(None) if device_id is None else EventRule.device_id == device_id
        rule = await db.scalar(select(EventRule).where(EventRule.event_type == args.type, condition))
        if rule is None:
            rule = EventRule(event_type=args.type, device_id=device_id, enabled=True)
            db.add(rule)
        if args.enable:
            rule.enabled = True
        if args.disable:
            rule.enabled = False
        if args.severity:
            rule.severity = args.severity
        await db.flush()
        print(f"Regla {args.type} ({'global' if device_id is None else f'disp.{device_id}'}): "
              f"{'habilitado' if rule.enabled else 'deshabilitado'}, severidad={rule.severity or 'por defecto'}")


async def main_async(args: argparse.Namespace) -> None:
    engine = create_engine()
    factory = create_session_factory(engine)
    try:
        if args.command == "list":
            await list_events(args, factory)
        elif args.command == "rules":
            await list_rules(factory)
        else:
            await set_rule(args, factory)
    finally:
        await engine.dispose()


def main() -> None:
    types = [t.value for t in EventType]
    parser = argparse.ArgumentParser(description="Eventos VALKERY GPS")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="últimos eventos")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--type", choices=types)

    sub.add_parser("rules", help="reglas por tipo de evento")

    p_rule = sub.add_parser("set-rule", help="habilitar/deshabilitar o cambiar severidad")
    p_rule.add_argument("--type", required=True, choices=types)
    group = p_rule.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true")
    group.add_argument("--disable", action="store_true")
    p_rule.add_argument("--severity", choices=[s.value for s in Severity])
    p_rule.add_argument("--imei", help="regla solo para este dispositivo")

    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
