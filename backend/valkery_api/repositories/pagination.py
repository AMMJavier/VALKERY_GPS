"""Paginación por cursor (keyset) sobre (fecha, id).

A diferencia de OFFSET, el cursor no se degrada con tablas grandes y no
salta ni repite filas si llegan datos nuevos entre páginas.
"""

from __future__ import annotations

import base64
from datetime import datetime

from fastapi import HTTPException, status


def encode_cursor(at: datetime, row_id: int) -> str:
    raw = f"{at.isoformat()}|{row_id}".encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        at, row_id = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii").split("|")
        parsed = datetime.fromisoformat(at)
        if parsed.tzinfo is None:
            raise ValueError("sin zona horaria")
        return parsed, int(row_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="cursor inválido") from exc
