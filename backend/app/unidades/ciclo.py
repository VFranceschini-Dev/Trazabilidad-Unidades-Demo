"""Fin del ciclo de vida (HU-14), ubicacion (HU-11) e indicadores (HU-12) de las unidades."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import estados
from app.core.auditoria import registrar as auditar
from app.core.excepciones import ErrorDominio
from app.infracciones.models import EstadoActa, Infraccion
from app.integraciones.traccar import ErrorTraccar, Posicion, TraccarPosiciones
from app.unidades.models import Circuito, PosicionCache, UnidadDemo
from app.unidades.service import (
    _cerrar_asignaciones_abiertas,
    filtrar_por_perfil,
    listar_unidades,
    obtener_unidad_bloqueada,
    responsable_en,
)

MOTIVOS_BAJA = {"VENTA_USADO": "Venta como usado", "DEVOLUCION_TERMINAL": "Devolución a la terminal"}
ESTADOS_SIN_RESOLVER = (EstadoActa.PENDIENTE_VALIDACION, EstadoActa.VALIDADA, EstadoActa.IMPUTADA)
ESTADOS_BLOQUEAN_VENTA = (EstadoActa.PENDIENTE_VALIDACION, EstadoActa.VALIDADA)


def _de_la_unidad(unidad: UnidadDemo) -> Any:
    # Un acta sin validar todavia no tiene id_unidad: se reconoce por la patente leida
    return or_(Infraccion.id_unidad == unidad.id, Infraccion.patente_leida == unidad.patente)


def actas_pendientes(sesion: Session, unidad: UnidadDemo) -> list[Infraccion]:
    """HU-14.2: actas sin validar o validadas sin imputar."""
    return list(
        sesion.scalars(
            select(Infraccion)
            .where(_de_la_unidad(unidad), Infraccion.estado.in_([e.value for e in ESTADOS_BLOQUEAN_VENTA]))
            .order_by(Infraccion.fecha_recepcion)
        )
    )


def pasar_a_venta(
    sesion: Session, id_unidad: int, *, motivo: str, usuario: Any, id_sucursal: Optional[str] = None, ip: Optional[str] = None
) -> UnidadDemo:
    """HU-14.1 y HU-14.2: desde DISPONIBLE o ASIGNADA; las actas pendientes lo impiden y se listan."""
    unidad = obtener_unidad_bloqueada(sesion, id_unidad)
    pendientes = actas_pendientes(sesion, unidad)
    if pendientes:
        raise ErrorDominio(
            codigo="ACTAS_PENDIENTES",
            mensaje=f"La unidad tiene {len(pendientes)} acta(s) pendiente(s) de validación o imputación.",
            detalle={
                "actas": [
                    {"id_infraccion": a.id_infraccion, "nro_acta": a.nro_acta, "estado": a.estado} for a in pendientes
                ]
            },
            estado_http=409,
        )
    evento = estados.transicionar(
        sesion, unidad, estados.TipoEvento.PASE_VENTA, usuario, estados.Origen.WEB,
        datos={"motivo": motivo, **({"id_sucursal": id_sucursal} if id_sucursal else {})},
    )
    _cerrar_asignaciones_abiertas(sesion, unidad.id, evento.fecha_hora)
    if id_sucursal:
        unidad.id_sucursal = id_sucursal
    auditar(sesion, id_usuario=usuario.id, accion="PASE_VENTA", recurso=f"unidad:{unidad.id}", ip=ip, resultado="EXITO")
    sesion.flush()
    return unidad


def dar_de_baja(sesion: Session, id_unidad: int, *, motivo: str, usuario: Any, ip: Optional[str] = None) -> UnidadDemo:
    """HU-14.3: EN_VENTA -> BAJA; la unidad conserva todo su historial."""
    unidad = obtener_unidad_bloqueada(sesion, id_unidad)
    if motivo not in MOTIVOS_BAJA:
        raise ErrorDominio(
            codigo="MOTIVO_BAJA_INVALIDO",
            mensaje="El motivo debe ser venta como usado o devolución a la terminal.",
            detalle={"motivos": list(MOTIVOS_BAJA)},
            estado_http=422,
        )
    estados.transicionar(
        sesion, unidad, estados.TipoEvento.BAJA, usuario, estados.Origen.WEB, datos={"motivo": MOTIVOS_BAJA[motivo]}
    )
    auditar(sesion, id_usuario=usuario.id, accion="BAJA", recurso=f"unidad:{unidad.id}", ip=ip, resultado="EXITO")
    sesion.flush()
    return unidad


@dataclass(frozen=True)
class Ubicacion:
    estado: str  # VIGENTE | CACHE | SIN_DISPOSITIVO | SIN_DATOS
    posicion: Optional[Posicion] = None


def _guardar_en_cache(sesion: Session, unidad: UnidadDemo, posicion: Posicion) -> None:
    fila = sesion.get(PosicionCache, unidad.id)
    if fila is None:
        sesion.add(
            PosicionCache(id_unidad=unidad.id, latitud=posicion.latitud, longitud=posicion.longitud, fecha_hora=posicion.fecha_hora)
        )
    elif posicion.fecha_hora > fila.fecha_hora:  # una posicion atrasada no pisa a la mas reciente
        fila.latitud, fila.longitud, fila.fecha_hora = posicion.latitud, posicion.longitud, posicion.fecha_hora
    sesion.flush()


def ubicacion(sesion: Session, unidad: UnidadDemo, adaptador: Optional[TraccarPosiciones] = None) -> Ubicacion:
    """HU-11: ultima posicion; si Traccar no responde, la guardada; sin dispositivo no hay datos."""
    if unidad.id_dispositivo_traccar is None:
        return Ubicacion("SIN_DISPOSITIVO")
    try:
        posicion = (adaptador or TraccarPosiciones()).ultima(unidad.id_dispositivo_traccar)
    except ErrorTraccar:
        fila = sesion.get(PosicionCache, unidad.id)
        if fila is None:
            return Ubicacion("SIN_DATOS")
        return Ubicacion("CACHE", Posicion(fila.latitud, fila.longitud, fila.fecha_hora))
    if posicion is None:
        return Ubicacion("SIN_DATOS")
    _guardar_en_cache(sesion, unidad, posicion)
    sesion.commit()
    return Ubicacion("VIGENTE", posicion)


@dataclass(frozen=True)
class FilaTablero:
    unidad: UnidadDemo
    responsable: Optional[str]


@dataclass(frozen=True)
class Indicadores:
    activas: int
    por_estado: dict[str, int]
    multas_pendientes: int
    filas: list[FilaTablero]


def indicadores(
    sesion: Session, usuario: Any, *, id_sucursal: Optional[str] = None, circuito: Optional[Circuito] = None
) -> Indicadores:
    """HU-12: indicadores y tabla recalculados con los filtros y segun el perfil."""
    unidades = filtrar_por_perfil(sesion, usuario, listar_unidades(sesion, circuito=circuito))
    if id_sucursal:
        unidades = [u for u in unidades if u.id_sucursal == id_sucursal]
    por_estado: dict[str, int] = {}
    for u in unidades:
        por_estado[u.estado_actual] = por_estado.get(u.estado_actual, 0) + 1
    ahora = datetime.now(timezone.utc)
    filas = []
    for u in unidades:
        responsable = responsable_en(sesion, u.id, ahora)
        filas.append(FilaTablero(u, responsable.nombre if responsable else None))

    sin_resolver = list(
        sesion.scalars(select(Infraccion).where(Infraccion.estado.in_([e.value for e in ESTADOS_SIN_RESOLVER])))
    )
    ids = {u.id for u in unidades}
    patentes = {u.patente for u in unidades}
    from app.identidad.models import Rol

    alcance_total = not id_sucursal and circuito is None and usuario.rol is not Rol.RESP_POSVENTA
    multas = [
        a for a in sin_resolver if a.id_unidad in ids or a.patente_leida in patentes or (alcance_total and a.id_unidad is None)
    ]
    return Indicadores(
        activas=sum(1 for u in unidades if u.estado_actual != estados.EstadoUnidad.BAJA.value),
        por_estado=por_estado,
        multas_pendientes=len(multas),
        filas=filas,
    )
