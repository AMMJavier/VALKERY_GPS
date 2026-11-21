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

    # --- Comandos (fase 6). Ambos interruptores están apagados por defecto.
    commands_enabled: bool = False  # todos los comandos
    commands_relay_enabled: bool = False  # IMMOBILIZE / RELEASE: solo tras la prueba física del relé
    command_ttl_s: int = 60  # vencimiento desde la creación (no se envían tarde)
    command_response_timeout_s: int = 60  # sin respuesta Codec 12 → RESULTADO_INCIERTO
    command_verify_timeout_s: int = 180  # sin DOUT1 observado → RESULTADO_INCIERTO
    command_state_max_age_s: int = 120  # antigüedad máxima del estado para validar precondiciones
    # Texto exacto enviado al FMC920. VERIFICAR con el firmware y el cableado reales.
    command_immobilize_text: str = "setdigout 1"
    command_release_text: str = "setdigout 0"


@lru_cache
def get_core_settings() -> CoreSettings:
    return CoreSettings()
