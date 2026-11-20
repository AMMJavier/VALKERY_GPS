"""Fábrica de AsyncEngine / AsyncSession (aiomysql).

Referencia Traccar: storage/DatabaseStorage.java
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..config import get_core_settings


def create_engine(url: str | None = None, *, echo: bool | None = None) -> AsyncEngine:
    settings = get_core_settings()
    return create_async_engine(
        url or settings.db_url,
        echo=settings.db_echo if echo is None else echo,
        pool_size=settings.db_pool_size,
        pool_pre_ping=True,
        pool_recycle=3600,
        # La conexión trabaja en UTC; las columnas DATETIME no guardan zona.
        connect_args={"init_command": "SET time_zone = '+00:00'"},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
