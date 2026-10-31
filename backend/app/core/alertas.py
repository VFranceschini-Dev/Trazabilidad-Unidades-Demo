"""Alta y cierre de alertas sin duplicar una abierta del mismo tipo y referencia."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.tablas_generales.models import Alerta, valor_parametro


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
        try:
            with sesion.begin_nested():
                sesion.add(alerta)
                sesion.flush()
        except IntegrityError:  # otro proceso la creo al mismo tiempo: la unica abierta es esa
            return _abierta(sesion, tipo, id_unidad, id_infraccion)
    else:
        alerta.mensaje = mensaje[:200]
    sesion.flush()
    return alerta


def verificar_service_proximo(sesion: Session, unidad: Any) -> None:
    """HU-13.3: se llama cada vez que cambia el kilometraje."""
    if unidad.km_proximo_service is None:
        return
    restantes = unidad.km_proximo_service - unidad.km_actual
    if restantes < int(valor_parametro(sesion, "aviso_service_km", "500")):
        detalle = f"está a {restantes} km del service" if restantes >= 0 else f"tiene el service vencido hace {-restantes} km"
        generar(sesion, "SERVICE_PROXIMO", f"{unidad.patente} {detalle}.", id_unidad=unidad.id)


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
