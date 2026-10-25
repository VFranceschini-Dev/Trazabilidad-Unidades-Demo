"""Registro de auditoría: ingresos, intentos fallidos y operaciones (sin datos personales)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.tablas_generales.models import Auditoria


def registrar(
    sesion: Session,
    *,
    id_usuario: int | None,
    accion: str,
    recurso: str,
    ip: str | None,
    resultado: str,
) -> None:
    """Inserta una fila de auditoria; nunca lanza excepciones al llamador."""
    sesion.add(
        Auditoria(
            id_usuario=id_usuario,
            accion=accion,
            recurso=recurso,
            ip=ip,
            resultado=resultado,
        )
    )
    sesion.flush()


def ip_desde_request(request: Any) -> str | None:
    """IP real considerando el proxy inverso Nginx."""
    if request is None:
        return None
    cabecera = request.headers.get("x-forwarded-for")
    if cabecera:
        return cabecera.split(",")[0].strip()
    return request.client.host if request.client else None
