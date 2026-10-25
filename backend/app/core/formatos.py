"""Utilidades de formato: errores comunes y fechas mostrables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from zoneinfo import ZoneInfo

from app.core.config import settings


def cuerpo_error(codigo: str, mensaje: str, detalle: Any = None) -> dict[str, Any]:
    return {"codigo": codigo, "mensaje": mensaje, "detalle": detalle}


def para_mostrar(instante: datetime | None) -> str:
    """UTC -> America/Argentina/Buenos_Aires en formato legible."""
    if instante is None:
        return "—"
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=ZoneInfo("UTC"))
    local = instante.astimezone(ZoneInfo(settings.timezone_display))
    return local.strftime("%d/%m/%Y %H:%M")
