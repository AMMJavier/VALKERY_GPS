"""Dispositivos con su estado actual.

Referencia Traccar: api/resource/DeviceResource.java
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from valkery_core.enums import Permission
from valkery_core.models import Device, DeviceState, Vehicle

from ...core.deps import CurrentUser, DbSession, require
from ...schemas import DeviceCreate, DeviceOut, DeviceStateOut, DeviceUpdate
from ...services.audit import audit

router = APIRouter(prefix="/devices", tags=["devices"])
Reader = Annotated[CurrentUser, Depends(require(Permission.DEVICES_READ))]
Manager = Annotated[CurrentUser, Depends(require(Permission.DEVICES_MANAGE))]


def _out(device: Device, state: DeviceState | None) -> DeviceOut:
    out = DeviceOut.model_validate(device)
    out.state = DeviceStateOut.model_validate(state) if state else None
    return out


async def get_device_or_404(db: DbSession, device_id: int) -> Device:
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dispositivo inexistente")
    return device


async def _check_vehicle(db: DbSession, vehicle_id: int | None) -> None:
    if vehicle_id is not None and await db.get(Vehicle, vehicle_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="vehicle_id inexistente")


@router.get("", response_model=list[DeviceOut])
async def list_devices(_: Reader, db: DbSession) -> list[DeviceOut]:
    rows = (
        await db.execute(
            select(Device, DeviceState).outerjoin(DeviceState, DeviceState.device_id == Device.id).order_by(Device.id)
        )
    ).all()
    return [_out(d, s) for d, s in rows]


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: int, _: Reader, db: DbSession) -> DeviceOut:
    device = await get_device_or_404(db, device_id)
    return _out(device, await db.get(DeviceState, device_id))


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def create_device(body: DeviceCreate, current: Manager, db: DbSession, request: Request) -> DeviceOut:
    if await db.scalar(select(Device.id).where(Device.imei == body.imei)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Ese IMEI ya está registrado")
    await _check_vehicle(db, body.vehicle_id)
    device = Device(**body.model_dump(), enabled=True)
    db.add(device)
    await db.flush()
    audit(
        db,
        actor_id=current.id,
        action="device_created",
        request=request,
        target_type="device",
        target_id=device.id,
        details={"imei_suffix": body.imei[-4:], "name": body.name},
    )
    await db.commit()
    return _out(device, None)


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: int, body: DeviceUpdate, current: Manager, db: DbSession, request: Request
) -> DeviceOut:
    device = await get_device_or_404(db, device_id)
    changes = body.model_dump(exclude_unset=True)
    if "vehicle_id" in changes:
        await _check_vehicle(db, changes["vehicle_id"])
    for field, value in changes.items():
        if value is not None or field == "vehicle_id":
            setattr(device, field, value)
    audit(
        db,
        actor_id=current.id,
        action="device_updated",
        request=request,
        target_type="device",
        target_id=device.id,
        details=changes,
    )
    await db.commit()
    return _out(device, await db.get(DeviceState, device_id))
