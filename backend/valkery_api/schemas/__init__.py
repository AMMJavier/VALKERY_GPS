"""Contratos Pydantic de la API (entrada validada y salida explícita).

Las fechas se reciben y devuelven en ISO 8601 con zona horaria (UTC).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from valkery_core.enums import EventType, GeofenceType, Permission, Severity
from valkery_core.geo import validate_polygon

T = TypeVar("T")


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("la fecha debe incluir zona horaria (p. ej. 2026-11-20T12:00:00Z)")
    return value


AwareDatetime = Annotated[datetime, AfterValidator(_aware)]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(ApiModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = Field(description="Pasar como ?cursor= para la página siguiente; null = no hay más")


# --------------------------------------------------------------------- auth


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


# --------------------------------------------------------------------- usuarios


class UserOut(ApiModel):
    id: int
    username: str
    full_name: str
    email: str | None
    enabled: bool
    roles: list[str] = []
    permissions: list[str] = []
    last_login_at: datetime | None
    created_at: datetime


Username = Annotated[str, Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")]


class UserCreate(BaseModel):
    username: Username
    full_name: str = Field(default="", max_length=100)
    email: str | None = Field(default=None, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=256)
    roles: list[str] = Field(min_length=1)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    enabled: bool | None = None
    roles: list[str] | None = Field(default=None, min_length=1)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=10, max_length=256)


class RoleOut(ApiModel):
    id: int
    name: str
    description: str
    permissions: list[Permission]


# --------------------------------------------------------------------- vehículos y dispositivos


class VehicleIn(BaseModel):
    alias: str = Field(min_length=1, max_length=100)
    vehicle_type: str = Field(default="motorcycle", max_length=30)
    plate: str | None = Field(default=None, max_length=20)


class VehicleOut(ApiModel):
    id: int
    alias: str
    vehicle_type: str
    plate: str | None


class DeviceStateOut(ApiModel):
    online: bool
    reported_offline: bool
    last_seen: datetime | None
    last_gps_time: datetime | None
    fix_time: datetime | None
    latitude: float | None
    longitude: float | None
    speed: int | None
    course: int | None
    ignition: bool | None
    movement: bool | None
    dout1: bool | None
    gnss_status: int | None
    gsm_signal: int | None
    external_voltage_mv: int | None
    battery_voltage_mv: int | None
    odometer_m: int | None


class DeviceOut(ApiModel):
    id: int
    imei: str
    name: str
    brand: str
    model: str
    fw_version: str | None
    vehicle_id: int | None
    enabled: bool
    state: DeviceStateOut | None = None


class DeviceCreate(BaseModel):
    imei: str = Field(pattern=r"^\d{14,17}$")
    name: str = Field(min_length=1, max_length=100)
    model: str = Field(default="FMC920", max_length=50)
    fw_version: str | None = Field(default=None, max_length=50)
    vehicle_id: int | None = None


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    fw_version: str | None = Field(default=None, max_length=50)
    vehicle_id: int | None = None
    enabled: bool | None = None


# --------------------------------------------------------------------- posiciones


class PositionOut(ApiModel):
    id: int
    gps_time: datetime
    received_at: datetime
    valid: bool
    latitude: float
    longitude: float
    altitude: int
    speed: int
    course: int
    satellites: int
    ignition: bool | None
    movement: bool | None
    dout1: bool | None
    external_voltage_mv: int | None
    odometer_m: int | None
    event_io_id: int
    io: dict[str, Any] | None = None


# --------------------------------------------------------------------- eventos y reglas


class EventOut(ApiModel):
    id: int
    device_id: int
    position_id: int | None
    geofence_id: int | None
    event_type: str
    severity: str
    source: str
    occurred_at: datetime
    created_at: datetime
    attributes: dict[str, Any]


class EventRuleIn(BaseModel):
    event_type: EventType
    device_id: int | None = None
    enabled: bool = True
    severity: Severity | None = None


class EventRuleOut(ApiModel):
    id: int
    event_type: str
    device_id: int | None
    enabled: bool
    severity: str | None


# --------------------------------------------------------------------- geocercas


class GeofenceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    geofence_type: GeofenceType
    center_lat: float | None = Field(default=None, ge=-90, le=90)
    center_lon: float | None = Field(default=None, ge=-180, le=180)
    radius_m: int | None = Field(default=None, gt=0, le=100_000)
    points: list[list[float]] | None = Field(default=None, max_length=500)
    device_id: int | None = None
    enabled: bool = True

    @field_validator("points")
    @classmethod
    def _points_pairs(cls, value: list[list[float]] | None) -> list[list[float]] | None:
        if value is not None and any(len(p) != 2 for p in value):
            raise ValueError("cada punto debe ser [lat, lon]")
        return value

    @model_validator(mode="after")
    def _shape(self) -> GeofenceIn:
        if self.geofence_type == GeofenceType.CIRCLE:
            if self.center_lat is None or self.center_lon is None or self.radius_m is None:
                raise ValueError("un círculo requiere center_lat, center_lon y radius_m")
            self.points = None
        else:
            if not self.points:
                raise ValueError("un polígono requiere points")
            self.points = [list(p) for p in validate_polygon(self.points)]
            self.center_lat = self.center_lon = self.radius_m = None
        return self


class GeofenceOut(ApiModel):
    id: int
    name: str
    geofence_type: str
    center_lat: float | None
    center_lon: float | None
    radius_m: int | None
    points: list[list[float]] | None
    device_id: int | None
    enabled: bool


# --------------------------------------------------------------------- auditoría


class AuditOut(ApiModel):
    id: int
    actor_id: int | None
    action: str
    target_type: str | None
    target_id: int | None
    ip: str | None
    details: dict[str, Any]
    created_at: datetime


# --------------------------------------------------------------------- comandos


class CommandTypeOut(BaseModel):
    command_type: str
    label: str
    description: str
    relay: bool
    requires_confirmation: bool
    permissions: list[str]
    allowed: bool = Field(description="El usuario tiene los permisos y la configuración lo habilita")
    unavailable_reason: str | None = None


class CommandCreate(BaseModel):
    command_type: str = Field(max_length=30)


class CommandConfirm(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    acknowledge_safety: bool = Field(
        description="El usuario declara que verificó que la moto está detenida y es seguro ejecutar el comando"
    )


class CommandResponseOut(ApiModel):
    received_at: datetime
    response_text: str
    result: str
    detail: str | None


class CommandOut(ApiModel):
    id: int
    device_id: int
    command_type: str
    command_text: str
    status: str
    expected_dout1: bool | None
    requested_by: int | None
    confirmed_by: int | None
    requested_at: datetime
    expires_at: datetime
    confirmed_at: datetime | None
    sent_at: datetime | None
    responded_at: datetime | None
    verified_at: datetime | None
    finished_at: datetime | None
    preconditions: list[dict[str, Any]]
    verification: dict[str, Any] | None
    failure_reason: str | None
    responses: list[CommandResponseOut] = []
