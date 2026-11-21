"""Registro de auditoría de acciones sensibles."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from valkery_core.models import AuditLog

from ..core.deps import client_ip


def audit(
    db: AsyncSession,
    *,
    actor_id: int | None,
    action: str,
    request: Request | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Agrega la entrada a la sesión; se guarda con el commit de la operación."""
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            ip=client_ip(request) if request else None,
            details=details or {},
        )
    )
