"""Alta y cierre de alertas sin duplicar una abierta del mismo tipo y referencia."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tablas_generales.models import Alerta


def _abierta(sesion: Session, tipo: str, id_unidad: Optional[int], id_infraccion: Optional[int]) -> Optional[Alerta]:
    return sesion.scalar(
        select(Alerta).where(
            Alerta.tipo_alerta == tipo,
            Alerta.estado == "ABIERTA",
            Alerta.id_unidad.is_not_distinct_from(id_unidad),
            Alerta.id_infraccion.is_not_distinct_from(id_infraccion),
        )
    )


def generar(
    sesion: Session, tipo: str, mensaje: str, *, id_unidad: Optional[int] = None, id_infraccion: Optional[int] = None
) -> Alerta:
    """Si ya hay una abierta con esa referencia, actualiza su mensaje en lugar de duplicarla."""
    alerta = _abierta(sesion, tipo, id_unidad, id_infraccion)
    if alerta is None:
        alerta = Alerta(tipo_alerta=tipo, id_unidad=id_unidad, id_infraccion=id_infraccion, mensaje=mensaje[:200])
        sesion.add(alerta)
    else:
        alerta.mensaje = mensaje[:200]
    sesion.flush()
    return alerta


def cerrar(
    sesion: Session, tipo: str, usuario: Any, accion: str, *, id_unidad: Optional[int] = None, id_infraccion: Optional[int] = None
) -> None:
    alerta = _abierta(sesion, tipo, id_unidad, id_infraccion)
    if alerta is not None:
        alerta.estado = "CERRADA"
        alerta.id_usuario_cierre = usuario.id
        alerta.fecha_cierre = datetime.now(timezone.utc)
        alerta.accion_realizada = accion
        sesion.flush()
