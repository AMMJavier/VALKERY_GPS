"""Crea el primer usuario administrador (o uno adicional).

La contraseña se pide por teclado (no se muestra ni queda en el historial).

    python tools/create_admin.py --username admin --name "Tu nombre"
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "shared"), str(ROOT / "backend")]

from fastapi import HTTPException  # noqa: E402

from valkery_api.core.security import MIN_PASSWORD_LENGTH  # noqa: E402
from valkery_api.services.audit import audit  # noqa: E402
from valkery_api.services.users import create_user  # noqa: E402
from valkery_core.db import create_engine, create_session_factory  # noqa: E402


def ask_password() -> str:
    while True:
        first = getpass.getpass("Contraseña: ")
        if len(first) < MIN_PASSWORD_LENGTH:
            print(f"Mínimo {MIN_PASSWORD_LENGTH} caracteres.")
            continue
        if getpass.getpass("Repite la contraseña: ") != first:
            print("No coinciden.")
            continue
        return first


async def main_async(args: argparse.Namespace, password: str) -> None:
    engine = create_engine()
    factory = create_session_factory(engine)
    try:
        async with factory.begin() as db:
            try:
                user = await create_user(
                    db, username=args.username, password=password, roles=["admin"], full_name=args.name, email=args.email
                )
            except HTTPException as exc:
                raise SystemExit(f"No se pudo crear: {exc.detail}") from exc
            audit(db, actor_id=None, action="user_created", target_type="user", target_id=user.id,
                  details={"username": user.username, "roles": ["admin"], "via": "create_admin.py"})
        print(f"Administrador '{args.username}' creado (id {user.id}).")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Crear usuario administrador")
    parser.add_argument("--username", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--email")
    args = parser.parse_args()
    asyncio.run(main_async(args, ask_password()))


if __name__ == "__main__":
    main()
