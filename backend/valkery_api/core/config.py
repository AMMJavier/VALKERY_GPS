"""Configuración de la API (variables VALKERY_API_* en .env o en el entorno).

Referencia Traccar: config/Keys.java
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from valkery_core.config import ENV_FILE


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VALKERY_API_", env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expire_min: int = Field(default=60, ge=5, le=24 * 60)
    cors_origins: str = "http://localhost:5173"

    login_max_attempts: int = 5
    login_lockout_min: int = 15

    positions_max_range_days: int = 31
    page_max: int = 1000
    ws_poll_s: float = 1.5

    @field_validator("jwt_secret")
    @classmethod
    def _not_placeholder(cls, value: str) -> str:
        if "CAMBIAR" in value.upper():
            raise ValueError("VALKERY_API_JWT_SECRET sigue con el valor de ejemplo")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
