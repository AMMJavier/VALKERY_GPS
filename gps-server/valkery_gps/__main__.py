"""Punto de entrada: python -m valkery_gps (desde la carpeta gps-server).

Lee la configuración de .env (raíz del repo) y variables de entorno.

Referencia Traccar: Main.java
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from dotenv import load_dotenv

from valkery_core.config import ENV_FILE, get_core_settings
from valkery_core.db import create_engine, create_session_factory

from .config import GpsServerConfig
from .handlers.database import DatabaseDeviceRegistry, DatabaseSink
from .schedule.retention import retention_loop
from .server import GpsServer

logger = logging.getLogger("valkery_gps")


async def run() -> None:
    settings = get_core_settings()
    engine = create_engine()
    session_factory = create_session_factory(engine)
    sink = DatabaseSink(session_factory)
    server = GpsServer(GpsServerConfig.from_env(), DatabaseDeviceRegistry(session_factory), sink)

    await sink.mark_all_offline()
    retention = asyncio.create_task(retention_loop(session_factory, settings.raw_packet_retention_days))
    try:
        await server.serve_forever()
    finally:
        retention.cancel()
        await server.stop()
        await engine.dispose()
        logger.info("Servidor detenido")


def main() -> None:
    load_dotenv(ENV_FILE)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
