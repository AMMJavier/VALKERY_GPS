"""Vehículos."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from valkery_core.enums import Permission
from valkery_core.models import Vehicle

from ...core.deps import CurrentUser, DbSession, require
from ...schemas import VehicleIn, VehicleOut
from ...services.audit import audit

router = APIRouter(prefix="/vehicles", tags=["vehicles"])
Reader = Annotated[CurrentUser, Depends(require(Permission.DEVICES_READ))]
Manager = Annotated[CurrentUser, Depends(require(Permission.DEVICES_MANAGE))]


@router.get("", response_model=list[VehicleOut])
async def list_vehicles(_: Reader, db: DbSession) -> list[Vehicle]:
    return list((await db.scalars(select(Vehicle).order_by(Vehicle.id))).all())


@router.post("", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
async def create_vehicle(body: VehicleIn, current: Manager, db: DbSession, request: Request) -> Vehicle:
    vehicle = Vehicle(**body.model_dump())
    db.add(vehicle)
    await db.flush()
    audit(db, actor_id=current.id, action="vehicle_created", request=request, target_type="vehicle", target_id=vehicle.id)
    await db.commit()
    return vehicle


@router.put("/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(vehicle_id: int, body: VehicleIn, current: Manager, db: DbSession, request: Request) -> Vehicle:
    vehicle = await db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Vehículo inexistente")
    for field, value in body.model_dump().items():
        setattr(vehicle, field, value)
    audit(db, actor_id=current.id, action="vehicle_updated", request=request, target_type="vehicle", target_id=vehicle.id)
    await db.commit()
    return vehicle
