"""Rutas de prestamos por garantia (HU-05 y HU-06): solo el Resp. Posventa."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.db import get_session
from app.core.seguridad import requerir_rol
from app.identidad.models import Rol
from app.posventa import service
from app.posventa.esquemas import DevolucionIn, PrestamoIn, PrestamoOut
from app.posventa.models import Prestamo
from app.tablas_generales.models import Cliente
from app.unidades.models import UnidadDemo

router = APIRouter(prefix="/prestamos", tags=["prestamos"])


def _out(prestamo: Prestamo, unidad: UnidadDemo, cliente: Cliente, demorado: bool = False) -> PrestamoOut:
    return PrestamoOut(
        id_prestamo=prestamo.id_prestamo,
        id_unidad=prestamo.id_unidad,
        unidad_patente=unidad.patente,
        unidad_modelo=unidad.modelo,
        id_cliente=prestamo.id_cliente,
        cliente_nombre=cliente.nombre,
        nro_orden_reparacion=prestamo.nro_orden_reparacion,
        fecha_hora_entrega=prestamo.fecha_hora_entrega,
        fecha_hora_devolucion=prestamo.fecha_hora_devolucion,
        fecha_devolucion_prevista=prestamo.fecha_devolucion_prevista,
        km_entrega=prestamo.km_entrega,
        km_devolucion=prestamo.km_devolucion,
        combustible_entrega=prestamo.combustible_entrega,
        combustible_devolucion=prestamo.combustible_devolucion,
        control_previo=prestamo.control_previo,
        estado_entrega=prestamo.estado_entrega,
        estado_devolucion=prestamo.estado_devolucion,
        demorado=demorado,
    )


@router.get("", response_model=list[PrestamoOut])
def listar(
    activos: bool = Query(default=True),
    usuario: Any = Depends(requerir_rol(Rol.RESP_POSVENTA.value)),
    sesion: Session = Depends(get_session),
) -> list[PrestamoOut]:
    """HU-06.3: los activos con fecha prevista vencida aparecen marcados como demorados."""
    return [_out(p, u, c, demorado) for p, u, c, demorado in service.listar_prestamos(sesion, activos=activos)]


@router.post("", response_model=PrestamoOut, status_code=201)
def entregar(
    datos: PrestamoIn,
    request: Request,
    usuario: Any = Depends(requerir_rol(Rol.RESP_POSVENTA.value)),
    sesion: Session = Depends(get_session),
) -> PrestamoOut:
    """HU-05: DISPONIBLE -> EN_PRESTAMO."""
    with sesion.begin_nested():
        unidad, prestamo = service.registrar_entrega(
            sesion, datos.id_unidad,
            nro_orden_reparacion=datos.nro_orden_reparacion,
            cliente_documento=datos.cliente_documento, cliente_nombre=datos.cliente_nombre,
            fecha_devolucion_prevista=datos.fecha_devolucion_prevista,
            km_entrega=datos.km_entrega, combustible_entrega=datos.combustible_entrega,
            control_previo=datos.control_previo, observaciones=datos.observaciones,
            usuario=usuario, fecha_hora=datos.fecha_hora,
            ip=auditoria.ip_desde_request(request),
        )
    sesion.commit()
    return _out(prestamo, unidad, sesion.get(Cliente, prestamo.id_cliente))


@router.post("/{id_prestamo}/devolucion", response_model=PrestamoOut)
def devolver(
    id_prestamo: int,
    datos: DevolucionIn,
    request: Request,
    usuario: Any = Depends(requerir_rol(Rol.RESP_POSVENTA.value)),
    sesion: Session = Depends(get_session),
) -> PrestamoOut:
    """HU-06: EN_PRESTAMO -> DISPONIBLE; con danos genera una alerta para Posventa."""
    with sesion.begin_nested():
        unidad, prestamo = service.registrar_devolucion(
            sesion, id_prestamo,
            km_devolucion=datos.km_devolucion, combustible_devolucion=datos.combustible_devolucion,
            estado_devolucion=datos.estado_devolucion, con_danos=datos.con_danos,
            usuario=usuario, fecha_hora=datos.fecha_hora,
            ip=auditoria.ip_desde_request(request),
        )
    sesion.commit()
    return _out(prestamo, unidad, sesion.get(Cliente, prestamo.id_cliente))
