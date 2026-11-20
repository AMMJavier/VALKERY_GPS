"""Configuración común leída de variables de entorno y del archivo .env de la raíz.

Referencia Traccar: config/Config.java, config/Keys.java
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VALKERY_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_url: str = "mysql+aiomysql://valkery:CAMBIAR@127.0.0.1:3306/valkery_gps"
    db_echo: bool = False
    db_pool_size: int = 5
    raw_packet_retention_days: int = 30


@lru_cache
def get_core_settings() -> CoreSettings:
    return CoreSettings()
