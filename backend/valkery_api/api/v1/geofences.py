"""Geocercas.

Referencia Traccar: api/resource/GeofenceResource.java
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from valkery_core.enums import Permission
from valkery_core.models import Device, Geofence

from ...core.deps import CurrentUser, DbSession, require
from ...schemas import GeofenceIn, GeofenceOut
from ...services.audit import audit

router = APIRouter(prefix="/geofences", tags=["geofences"])
Reader = Annotated[CurrentUser, Depends(require(Permission.DEVICES_READ))]
Manager = Annotated[CurrentUser, Depends(require(Permission.GEOFENCES_MANAGE))]


async def _get(db: DbSession, geofence_id: int) -> Geofence:
    fence = await db.get(Geofence, geofence_id)
    if fence is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Geocerca inexistente")
    return fence


async def _check_device(db: DbSession, device_id: int | None) -> None:
    if device_id is not None and await db.get(Device, device_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="device_id inexistente")


@router.get("", response_model=list[GeofenceOut])
async def list_geofences(_: Reader, db: DbSession) -> list[Geofence]:
    return list((await db.scalars(select(Geofence).order_by(Geofence.id))).all())


@router.post("", response_model=GeofenceOut, status_code=status.HTTP_201_CREATED)
async def create_geofence(body: GeofenceIn, current: Manager, db: DbSession, request: Request) -> Geofence:
    await _check_device(db, body.device_id)
    fence = Geofence(**body.model_dump(mode="json"))
    db.add(fence)
    await db.flush()
    audit(
        db,
        actor_id=current.id,
        action="geofence_created",
        request=request,
        target_type="geofence",
        target_id=fence.id,
        details={"name": fence.name, "type": fence.geofence_type},
    )
    await db.commit()
    return fence


@router.put("/{geofence_id}", response_model=GeofenceOut)
async def update_geofence(
    geofence_id: int, body: GeofenceIn, current: Manager, db: DbSession, request: Request
) -> Geofence:
    fence = await _get(db, geofence_id)
    await _check_device(db, body.device_id)
    for field, value in body.model_dump(mode="json").items():
        setattr(fence, field, value)
    audit(
        db, actor_id=current.id, action="geofence_updated", request=request, target_type="geofence", target_id=fence.id
    )
    await db.commit()
    return fence


@router.delete("/{geofence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_geofence(geofence_id: int, current: Manager, db: DbSession, request: Request) -> None:
    fence = await _get(db, geofence_id)
    await db.delete(fence)
    audit(
        db,
        actor_id=current.id,
        action="geofence_deleted",
        request=request,
        target_type="geofence",
        target_id=geofence_id,
        details={"name": fence.name},
    )
    await db.commit()
