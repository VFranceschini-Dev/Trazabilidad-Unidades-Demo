"""Soporte comun de pruebas: fabricas de unidades y recorridos por el motor de estados."""

from __future__ import annotations

import itertools
from typing import Any

from sqlalchemy.orm import Session

from app.core import estados
from app.unidades import service
from app.unidades.models import Circuito, UnidadDemo

_contador = itertools.count(1)


def _n() -> int:
    return next(_contador)


def alta_unidad(
    sesion: Session,
    base: Any,
    *,
    circuito: Circuito = Circuito.COMERCIAL,
    id_sucursal: str = "SC01",
    usuario: Any | None = None,
    **extra: Any,
) -> UnidadDemo:
    """Alta con VIN y patente unicos por corrida (el motor registra el evento ALTA)."""
    n = _n()
    return service.alta_unidad(
        sesion,
        vin=f"1FTFW1E80PFA{n:05d}",
        patente=f"PT{n:04d}A",
        modelo="Ranger",
        version="XLS 4x4",
        circuito=circuito,
        id_sucursal=id_sucursal,
        km_inicial=extra.pop("km_inicial", 1000),
        usuario=usuario or base.mkt,
        origen=estados.Origen.WEB,
        **extra,
    )


def transicionar(
    sesion: Session,
    unidad: UnidadDemo,
    evento: estados.TipoEvento,
    usuario: Any,
    datos: dict[str, Any] | None = None,
    fecha_hora: Any | None = None,
) -> Any:
    return estados.transicionar(
        sesion, unidad, evento, usuario, estados.Origen.WEB, datos=datos or {}, fecha_hora=fecha_hora
    )


_RUTAS: dict[estados.EstadoUnidad, tuple[estados.TipoEvento, ...]] = {
    estados.EstadoUnidad.DISPONIBLE: (),
    estados.EstadoUnidad.ASIGNADA: (estados.TipoEvento.ASIGNACION,),
    estados.EstadoUnidad.EN_USO: (estados.TipoEvento.ASIGNACION, estados.TipoEvento.SALIDA),
    estados.EstadoUnidad.EN_PRESTAMO: (estados.TipoEvento.PRESTAMO,),
    estados.EstadoUnidad.EN_SERVICE: (estados.TipoEvento.INGRESO_SERVICE,),
    estados.EstadoUnidad.EN_VENTA: (estados.TipoEvento.PASE_VENTA,),
    estados.EstadoUnidad.BAJA: (estados.TipoEvento.PASE_VENTA, estados.TipoEvento.BAJA),
}


def llevar_a(
    sesion: Session,
    base: Any,
    unidad: UnidadDemo,
    estado: estados.EstadoUnidad,
    usuario: Any | None = None,
) -> UnidadDemo:
    """Lleva la unidad al estado indicado aplicando transiciones del motor."""
    actor = usuario or base.mkt
    for evento in _RUTAS[estado]:
        datos: dict[str, Any] = {}
        if evento in (estados.TipoEvento.ASIGNACION, estados.TipoEvento.REASIGNACION):
            datos = {"id_responsable": base.asesor.id, "id_sucursal": unidad.id_sucursal}
        if evento is estados.TipoEvento.PRESTAMO:
            datos = {"id_cliente": 1, "nombre_cliente": "Cliente Prueba"}
        if evento is estados.TipoEvento.BAJA:
            datos = {"motivo": "venta como usado"}
        transicionar(sesion, unidad, evento, actor, datos)
    sesion.flush()
    sesion.refresh(unidad)
    return unidad


def ultimo_evento(sesion: Session, unidad: UnidadDemo) -> Any:
    return service.historial_eventos(sesion, unidad.id)[0]
