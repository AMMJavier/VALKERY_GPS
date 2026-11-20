"""Punto de entrada: python -m valkery_gps (desde la carpeta gps-server).

Referencia Traccar: Main.java
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from .config import GpsServerConfig
from .pipeline import AllowListAuthorizer, LoggingSink
from .server import GpsServer


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = GpsServerConfig.from_env()
    if not config.allowed_imeis:
        logging.warning("VALKERY_GPS_ALLOWED_IMEIS vacío: se rechazarán todos los equipos")
    server = GpsServer(config, AllowListAuthorizer(config.allowed_imeis), LoggingSink())
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(server.serve_forever())


if __name__ == "__main__":
    main()
