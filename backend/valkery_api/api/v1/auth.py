"""Inicio de sesión, usuario actual y cambio de contraseña.

Referencia Traccar: api/resource/SessionResource.java
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from valkery_core.db.base import utcnow
from valkery_core.models import User

from ...core.deps import Authenticated, DbSession, Settings
from ...core.security import create_access_token, hash_password, verify_password
from ...schemas import ChangePasswordRequest, LoginRequest, TokenOut, UserOut
from ...services.audit import audit
from ...services.users import user_out

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginRequest, request: Request, db: DbSession, settings: Settings) -> TokenOut:
    guard = request.app.state.login_guard
    key = body.username.lower()
    if guard.is_locked(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Espera {settings.login_lockout_min} minutos.",
        )

    user = await db.scalar(select(User).where(User.username == body.username))
    valid = verify_password(body.password, user.password_hash if user else None)
    if not valid or user is None or not user.enabled:
        guard.failure(key)
        audit(
            db,
            actor_id=user.id if user else None,
            action="login_failed",
            request=request,
            details={"username": body.username[:50], "reason": "disabled" if valid and user else "bad_credentials"},
        )
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos")

    guard.success(key)
    user.last_login_at = utcnow()
    audit(db, actor_id=user.id, action="login", request=request)
    await db.commit()
    token, expires = create_access_token(user.id, user.token_version, settings)
    return TokenOut(access_token=token, expires_at=expires)


@router.get("/me", response_model=UserOut)
async def me(current: Authenticated, db: DbSession) -> UserOut:
    return await user_out(db, current.user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: ChangePasswordRequest, current: Authenticated, db: DbSession, request: Request) -> None:
    user = current.user
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="La contraseña actual no es correcta")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # cierra todas las sesiones abiertas
    audit(db, actor_id=user.id, action="password_changed", request=request, target_type="user", target_id=user.id)
    await db.commit()
