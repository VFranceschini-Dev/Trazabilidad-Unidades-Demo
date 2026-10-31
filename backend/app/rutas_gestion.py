"""Rutas de ubicacion, ciclo de vida, tablero y alertas (HU-11 a HU-14)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import auditoria, control_alertas
from app.core.db import get_session
from app.core.seguridad import requerir_rol
from app.core.seguridad import obtener_usuario
from app.identidad.models import Rol, Usuario
from app.rutas_unidades import _out
from app.tablas_generales.models import Sucursal
from app.unidades import ciclo, service
from app.unidades.esquemas import UnidadOut
from app.unidades.models import Circuito

router = APIRouter(tags=["gestion"])

ROLES_TABLERO = (Rol.ADMIN, Rol.GERENCIA, Rol.RESP_MKT_VENTAS, Rol.RESP_POSVENTA, Rol.ADMINISTRACION)


class PaseVentaIn(BaseModel):
    motivo: str = Field(min_length=1, max_length=120)
    id_sucursal: Optional[str] = None


class BajaIn(BaseModel):
    motivo: str


class CerrarAlertaIn(BaseModel):
    accion: str = Field(min_length=1, max_length=500)


class ActaPendienteOut(BaseModel):
    id_infraccion: int
    nro_acta: Optional[str] = None
    fecha_hora_infraccion: Optional[datetime] = None
    estado: str


class UbicacionOut(BaseModel):
    estado: str
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    fecha_hora: Optional[datetime] = None
    localidad: Optional[str] = None


class FilaTableroOut(BaseModel):
    id: int
    patente: str
    modelo: str
    sucursal: Optional[str] = None
    circuito: str
    estado: str
    responsable: Optional[str] = None


class IndicadoresOut(BaseModel):
    activas: int
    disponibles: int
    asignadas: int
    en_uso: int
    en_prestamo: int
    en_service: int
    en_venta: int
    multas_pendientes: int
    filas: list[FilaTableroOut]


class AlertaOut(BaseModel):
    id_alerta: int
    tipo_alerta: str
    mensaje: str
    estado: str
    fecha_creacion: datetime
    id_unidad: Optional[int] = None
    id_infraccion: Optional[int] = None
    id_sucursal: Optional[str] = None
    circuito: Optional[str] = None
    cerrada_por: Optional[str] = None
    fecha_cierre: Optional[datetime] = None
    accion_realizada: Optional[str] = None
    puede_cerrar: bool = False


class AlertasOut(BaseModel):
    ultimo_control: Optional[str] = None
    alertas: list[AlertaOut]


@router.get("/unidades/{id_unidad}/ubicacion", response_model=UbicacionOut)
def ubicacion(id_unidad: int, usuario: Any = Depends(obtener_usuario), sesion: Session = Depends(get_session)) -> UbicacionOut:
    """HU-11: ultima posicion, la guardada si Traccar no responde, o sin datos."""
    from app.integraciones.traccar import localidad_cercana

    unidad = service.obtener_unidad(sesion, id_unidad)
    service.verificar_acceso(sesion, usuario, unidad)
    resultado = ciclo.ubicacion(sesion, unidad)
    p = resultado.posicion
    return UbicacionOut(
        estado=resultado.estado,
        latitud=p.latitud if p else None,
        longitud=p.longitud if p else None,
        fecha_hora=p.fecha_hora if p else None,
        localidad=localidad_cercana(p.latitud, p.longitud) if p else None,
    )


@router.get("/unidades/{id_unidad}/actas-pendientes", response_model=list[ActaPendienteOut])
def actas_pendientes(
    id_unidad: int,
    usuario: Any = Depends(requerir_rol(Rol.RESP_MKT_VENTAS.value)),
    sesion: Session = Depends(get_session),
) -> list[ActaPendienteOut]:
    return [
        ActaPendienteOut(
            id_infraccion=a.id_infraccion, nro_acta=a.nro_acta, fecha_hora_infraccion=a.fecha_hora_infraccion, estado=a.estado
        )
        for a in ciclo.actas_pendientes(sesion, service.obtener_unidad(sesion, id_unidad))
    ]


@router.post("/unidades/{id_unidad}/pase-venta", response_model=UnidadOut)
def pase_venta(
    id_unidad: int,
    datos: PaseVentaIn,
    request: Request,
    usuario: Any = Depends(requerir_rol(Rol.RESP_MKT_VENTAS.value)),
    sesion: Session = Depends(get_session),
) -> UnidadOut:
    """HU-14.1 y HU-14.2."""
    unidad = ciclo.pasar_a_venta(
        sesion, id_unidad, motivo=datos.motivo, id_sucursal=datos.id_sucursal, usuario=usuario,
        ip=auditoria.ip_desde_request(request),
    )
    sesion.commit()
    return _out(sesion, unidad)


@router.post("/unidades/{id_unidad}/baja", response_model=UnidadOut)
def baja(
    id_unidad: int,
    datos: BajaIn,
    request: Request,
    usuario: Any = Depends(requerir_rol(Rol.RESP_MKT_VENTAS.value)),
    sesion: Session = Depends(get_session),
) -> UnidadOut:
    """HU-14.3."""
    unidad = ciclo.dar_de_baja(sesion, id_unidad, motivo=datos.motivo, usuario=usuario, ip=auditoria.ip_desde_request(request))
    sesion.commit()
    return _out(sesion, unidad)


@router.get("/tablero/indicadores", response_model=IndicadoresOut)
def tablero(
    id_sucursal: Optional[str] = None,
    circuito: Optional[Circuito] = None,
    usuario: Any = Depends(requerir_rol(*(r.value for r in ROLES_TABLERO))),
    sesion: Session = Depends(get_session),
) -> IndicadoresOut:
    """HU-12.1 y HU-12.2."""
    datos = ciclo.indicadores(sesion, usuario, id_sucursal=id_sucursal, circuito=circuito)
    nombres = {s.codigo: s.nombre for s in sesion.scalars(select(Sucursal))}
    e = datos.por_estado
    return IndicadoresOut(
        activas=datos.activas,
        disponibles=e.get("DISPONIBLE", 0),
        asignadas=e.get("ASIGNADA", 0),
        en_uso=e.get("EN_USO", 0),
        en_prestamo=e.get("EN_PRESTAMO", 0),
        en_service=e.get("EN_SERVICE", 0),
        en_venta=e.get("EN_VENTA", 0),
        multas_pendientes=datos.multas_pendientes,
        filas=[
            FilaTableroOut(
                id=f.unidad.id, patente=f.unidad.patente, modelo=f.unidad.modelo,
                sucursal=nombres.get(f.unidad.id_sucursal), circuito=f.unidad.circuito.value,
                estado=f.unidad.estado_actual, responsable=f.responsable,
            )
            for f in datos.filas
        ],
    )


@router.get("/alertas", response_model=AlertasOut)
def listar_alertas(
    usuario: Any = Depends(requerir_rol(*(r.value for r in ROLES_TABLERO))),
    sesion: Session = Depends(get_session),
) -> AlertasOut:
    filas = []
    for v in control_alertas.listar(sesion, usuario):
        a = v.alerta
        cerrador = sesion.get(Usuario, a.id_usuario_cierre) if a.id_usuario_cierre else None
        filas.append(
            AlertaOut(
                id_alerta=a.id_alerta, tipo_alerta=a.tipo_alerta, mensaje=a.mensaje, estado=a.estado,
                fecha_creacion=a.fecha_creacion, id_unidad=a.id_unidad, id_infraccion=a.id_infraccion,
                id_sucursal=v.unidad.id_sucursal if v.unidad else None,
                circuito=v.unidad.circuito.value if v.unidad else None,
                cerrada_por=cerrador.nombre if cerrador else None,
                fecha_cierre=a.fecha_cierre, accion_realizada=a.accion_realizada, puede_cerrar=v.puede_cerrar,
            )
        )
    return AlertasOut(ultimo_control=control_alertas.ultimo_control(sesion), alertas=filas)


@router.post("/alertas/ejecutar-control")
def ejecutar_control(
    usuario: Any = Depends(requerir_rol(Rol.ADMIN.value)), sesion: Session = Depends(get_session)
) -> dict[str, int]:
    abiertas = control_alertas.ejecutar_control(sesion)
    sesion.commit()
    return {"alertas_abiertas": abiertas}


@router.post("/alertas/{id_alerta}/cerrar")
def cerrar_alerta(
    id_alerta: int,
    datos: CerrarAlertaIn,
    usuario: Any = Depends(requerir_rol(*(r.value for r in ROLES_TABLERO))),
    sesion: Session = Depends(get_session),
) -> dict[str, str]:
    control_alertas.cerrar(sesion, id_alerta, datos.accion, usuario)
    sesion.commit()
    return {"estado": "CERRADA"}
