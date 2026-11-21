"""Router v1: /api/v1/..."""

from fastapi import APIRouter

from . import audit, auth, commands, devices, events, geofences, positions, users, vehicles, ws

router = APIRouter(prefix="/api/v1")
for module in (auth, users, vehicles, devices, positions, events, geofences, commands, audit, ws):
    router.include_router(module.router)

__all__ = ["router"]
