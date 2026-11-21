"""Comandos remotos con salvaguardas (fase 6, ADR 0006).

Flujo:
    POST /devices/{id}/commands {command_type}
        - consultas (getver…): quedan AUTORIZADO de inmediato;
        - relé (IMMOBILIZE / RELEASE): quedan CREADO y vencen en VALKERY_COMMAND_TTL_S.
    POST /commands/{id}/confirm {password, acknowledge_safety: true}
        - el MISMO usuario reingresa su contraseña; se re-validan las precondiciones → AUTORIZADO.
    El servidor GPS envía los AUTORIZADO, vuelve a validar y sigue la respuesta y la verificación.
    POST /commands/{id}/cancel  → RECHAZADO (solo CREADO / AUTORIZADO).

Los comandos no se encolan: si el equipo no está conectado, se rechazan.

Referencia Traccar: api/resource/CommandResource.java
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from valkery_core.commands import SPECS, CommandSpec, CommandType, check_preconditions, expires_at, failed
from valkery_core.config import CoreSettings
from valkery_core.enums import ACTIVE_COMMAND_STATUSES, CommandStatus, Permission
from valkery_core.models import Command, CommandResponse, Device, DeviceState

from ...core.deps import CurrentUser, DbSession, require
from ...core.security import verify_password
from ...schemas import CommandConfirm, CommandCreate, CommandOut, CommandResponseOut, CommandTypeOut
from ...services.audit import audit

router = APIRouter(tags=["commands"])
Sender = Annotated[CurrentUser, Depends(require(Permission.COMMANDS_SEND))]

IN_PROGRESS = [s.value for s in ACTIVE_COMMAND_STATUSES] + [CommandStatus.RESPUESTA_RECIBIDA.value]


def _core(request: Request) -> CoreSettings:
    return request.app.state.core_settings


def _now() -> datetime:
    return datetime.now(UTC)


def _spec(command_type: str) -> CommandSpec:
    try:
        return SPECS[CommandType(command_type)]
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Tipo de comando desconocido") from None


def _unavailable(spec: CommandSpec, current: CurrentUser, core: CoreSettings) -> str | None:
    if not core.commands_enabled:
        return "Comandos deshabilitados (VALKERY_COMMANDS_ENABLED=false)"
    if spec.relay and not core.commands_relay_enabled:
        return "Comandos de relé deshabilitados hasta completar la prueba física (VALKERY_COMMANDS_RELAY_ENABLED=false)"
    missing = [p.value for p in spec.permissions if not current.has(p)]
    if missing:
        return f"Falta el permiso: {', '.join(missing)}"
    return None


async def _out(db: AsyncSession, cmd: Command) -> CommandOut:
    responses = (
        await db.scalars(
            select(CommandResponse).where(CommandResponse.command_id == cmd.id).order_by(CommandResponse.id)
        )
    ).all()
    out = CommandOut.model_validate(cmd)
    out.responses = [CommandResponseOut.model_validate(r) for r in responses]
    return out


async def _lock_state(db: AsyncSession, device_id: int) -> DeviceState:
    """Bloquea la fila de estado: serializa la creación de comandos del mismo equipo."""
    stmt = insert(DeviceState).values(device_id=device_id)
    await db.execute(stmt.on_duplicate_key_update(device_id=DeviceState.__table__.c.device_id))
    return await db.get(DeviceState, device_id, with_for_update=True, populate_existing=True)


def _evaluate(spec: CommandSpec, core: CoreSettings, device: Device, state: DeviceState, stage: str) -> list[dict]:
    checks = check_preconditions(
        spec, settings=core, device_enabled=device.enabled, online=bool(state.online), state=state, now=_now()
    )
    problems = failed(checks)
    results = [{"stage": stage, **c.as_dict()} for c in checks]
    if problems:
        raise _PreconditionError(results, "; ".join(c.detail for c in problems))
    return results


class _PreconditionError(Exception):
    def __init__(self, checks: list[dict], message: str) -> None:
        self.checks = checks
        self.message = message


@router.get("/commands/types", response_model=list[CommandTypeOut])
async def command_types(current: Sender, request: Request) -> list[CommandTypeOut]:
    core = _core(request)
    result = []
    for spec in SPECS.values():
        reason = _unavailable(spec, current, core)
        result.append(
            CommandTypeOut(
                command_type=spec.type.value,
                label=spec.label,
                description=spec.description,
                relay=spec.relay,
                requires_confirmation=spec.requires_confirmation,
                permissions=[p.value for p in spec.permissions],
                allowed=reason is None,
                unavailable_reason=reason,
            )
        )
    return result


@router.get("/devices/{device_id}/commands", response_model=list[CommandOut])
async def list_commands(
    device_id: int, _: Sender, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[CommandOut]:
    commands = (
        await db.scalars(
            select(Command).where(Command.device_id == device_id).order_by(Command.id.desc()).limit(limit)
        )
    ).all()
    return [await _out(db, c) for c in commands]


@router.get("/commands/{command_id}", response_model=CommandOut)
async def get_command(command_id: int, _: Sender, db: DbSession) -> CommandOut:
    cmd = await db.get(Command, command_id)
    if cmd is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Comando inexistente")
    return await _out(db, cmd)


@router.post("/devices/{device_id}/commands", response_model=CommandOut, status_code=status.HTTP_201_CREATED)
async def create_command(
    device_id: int, body: CommandCreate, current: Sender, db: DbSession, request: Request
) -> CommandOut:
    core = _core(request)
    spec = _spec(body.command_type)
    reason = _unavailable(spec, current, core)
    if reason:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=reason)

    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dispositivo inexistente")
    state = await _lock_state(db, device_id)

    busy = await db.scalar(
        select(Command.id).where(
            Command.device_id == device_id, Command.status.in_(IN_PROGRESS), Command.finished_at.is_(None)
        )
    )
    if busy:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Ya hay un comando en curso para este equipo (#{busy})")

    try:
        checks = _evaluate(spec, core, device, state, "request")
    except _PreconditionError as exc:
        audit(
            db,
            actor_id=current.id,
            action="command_blocked",
            request=request,
            target_type="device",
            target_id=device_id,
            details={"command_type": spec.type.value, "reason": exc.message[:500]},
        )
        await db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"message": f"Precondiciones no cumplidas: {exc.message}", "checks": exc.checks}
        ) from None

    now = _now()
    cmd = Command(
        device_id=device_id,
        command_type=spec.type.value,
        command_text=spec.text(core),
        status=(CommandStatus.CREADO if spec.requires_confirmation else CommandStatus.AUTORIZADO).value,
        expected_dout1=spec.expected_dout1,
        requested_by=current.id,
        requested_at=now,
        expires_at=expires_at(now, core),
        preconditions=checks,
    )
    if not spec.requires_confirmation:
        cmd.confirmed_by, cmd.confirmed_at = current.id, now
    db.add(cmd)
    await db.flush()
    audit(
        db,
        actor_id=current.id,
        action="command_requested",
        request=request,
        target_type="command",
        target_id=cmd.id,
        details={"device_id": device_id, "command_type": spec.type.value, "text": cmd.command_text},
    )
    await db.commit()
    return await _out(db, cmd)


async def _locked_command(db: AsyncSession, command_id: int) -> Command:
    cmd = await db.get(Command, command_id, with_for_update=True, populate_existing=True)
    if cmd is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Comando inexistente")
    return cmd


@router.post("/commands/{command_id}/confirm", response_model=CommandOut)
async def confirm_command(
    command_id: int, body: CommandConfirm, current: Sender, db: DbSession, request: Request
) -> CommandOut:
    core = _core(request)
    guard = request.app.state.login_guard
    guard_key = f"confirm:{current.user.username.lower()}"
    if guard.is_locked(guard_key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Demasiadas confirmaciones fallidas")
    if not body.acknowledge_safety:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Debes confirmar que es seguro ejecutar el comando")

    cmd = await _locked_command(db, command_id)
    spec = _spec(cmd.command_type)
    reason = _unavailable(spec, current, core)
    if reason:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=reason)
    if cmd.requested_by != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Solo quien solicitó el comando puede confirmarlo")
    if cmd.status != CommandStatus.CREADO.value:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"El comando está en estado {cmd.status}")

    now = _now()
    if cmd.expires_at <= now:
        cmd.status, cmd.finished_at, cmd.failure_reason = CommandStatus.EXPIRADO.value, now, "no se confirmó a tiempo"
        await db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="El comando venció; solicítalo de nuevo")

    if not verify_password(body.password, current.user.password_hash):
        guard.failure(guard_key)
        audit(db, actor_id=current.id, action="command_confirm_failed", request=request, target_type="command", target_id=cmd.id)
        await db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Contraseña incorrecta")
    guard.success(guard_key)

    device = await db.get(Device, cmd.device_id)
    state = await _lock_state(db, cmd.device_id)
    try:
        checks = _evaluate(spec, core, device, state, "confirm")
    except _PreconditionError as exc:
        cmd.preconditions = [*cmd.preconditions, *exc.checks]
        cmd.status, cmd.finished_at = CommandStatus.RECHAZADO.value, now
        cmd.failure_reason = f"al confirmar: {exc.message}"[:255]
        audit(db, actor_id=current.id, action="command_rejected", request=request, target_type="command", target_id=cmd.id,
              details={"reason": exc.message[:500]})
        await db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"message": f"Precondiciones no cumplidas: {exc.message}", "checks": exc.checks}
        ) from None

    cmd.preconditions = [*cmd.preconditions, *checks]
    cmd.status = CommandStatus.AUTORIZADO.value
    cmd.confirmed_by, cmd.confirmed_at = current.id, now
    audit(
        db,
        actor_id=current.id,
        action="command_confirmed",
        request=request,
        target_type="command",
        target_id=cmd.id,
        details={"command_type": cmd.command_type, "device_id": cmd.device_id, "acknowledge_safety": True},
    )
    await db.commit()
    return await _out(db, cmd)


@router.post("/commands/{command_id}/cancel", response_model=CommandOut)
async def cancel_command(command_id: int, current: Sender, db: DbSession, request: Request) -> CommandOut:
    cmd = await _locked_command(db, command_id)
    if cmd.status not in (CommandStatus.CREADO.value, CommandStatus.AUTORIZADO.value):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"No se puede cancelar en estado {cmd.status}")
    cmd.status, cmd.finished_at, cmd.failure_reason = CommandStatus.RECHAZADO.value, _now(), "cancelado por el usuario"
    audit(db, actor_id=current.id, action="command_cancelled", request=request, target_type="command", target_id=cmd.id)
    await db.commit()
    return await _out(db, cmd)
