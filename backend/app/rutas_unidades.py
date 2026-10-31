"""Rutas del núcleo de trazabilidad (HU-02, HU-03, HU-07).

Lectura: cualquier rol autenticado con permiso de perfil. Escritura: Resp. Marketing y
Ventas (COMERCIAL) o Resp. Posventa (POSVENTA), segun la tabla de la especificacion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import auditoria, estados
from app.core.db import get_session
from app.core.excepciones import ErrorDominio
from app.core.seguridad import obtener_usuario, requerir_rol
from app.identidad.models import Rol, Usuario
from app.tablas_generales.models import Sucursal, valor_parametro
from app.unidades import service
from app.unidades.esquemas import (
    AltaRecienteOut,
    AltaUnidadIn,
    AsignacionHistorialOut,
    AsignacionIn,
    EventoOut,
    FichaUnidadOut,
    HistorialOut,
    LiberacionIn,
    LimiteRotacionOut,
    MovimientoOut,
    ResponsableOut,
    ServiceFinIn,
    ServiceIngresoIn,
    UnidadOut,
)
from app.unidades.models import Circuito, UnidadDemo

router = APIRouter(prefix="/unidades", tags=["unidades"])


def _out(sesion: Session, unidad: UnidadDemo) -> UnidadOut:
    fila = UnidadOut.model_validate(unidad)
    sucursal = sesion.scalar(select(Sucursal).where(Sucursal.codigo == unidad.id_sucursal))
    fila.sucursal_nombre = sucursal.nombre if sucursal is not None else None
    return fila


@router.post("", response_model=MovimientoOut, status_code=201)
def crear_unidad(
    datos: AltaUnidadIn,
    request: Request,
    usuario: Any = Depends(obtener_usuario),
    sesion: Session = Depends(get_session),
) -> MovimientoOut:
    """HU-02: alta de unidad demo. El circuito determina el rol que puede operar."""
    if usuario.rol is Rol.RESP_MKT_VENTAS and datos.circuito is not Circuito.COMERCIAL:
        raise ErrorDominio(
            codigo="SIN_PERMISO",
            mensaje="Resp. Marketing y Ventas solo da de alta unidades del circuito COMERCIAL.",
            estado_http=403,
        )
    if usuario.rol is Rol.RESP_POSVENTA and datos.circuito is not Circuito.POSVENTA:
        raise ErrorDominio(
            codigo="SIN_PERMISO",
            mensaje="Resp. Posventa solo da de alta unidades del circuito POSVENTA.",
            estado_http=403,
        )
    if usuario.rol not in (Rol.RESP_MKT_VENTAS, Rol.RESP_POSVENTA):
        raise ErrorDominio(codigo="SIN_PERMISO", mensaje="El rol no puede dar de alta unidades.", estado_http=403)

    with sesion.begin_nested():
        unidad = service.alta_unidad(
            sesion,
            vin=datos.vin,
            patente=datos.patente,
            modelo=datos.modelo,
            version=datos.version,
            circuito=datos.circuito,
            id_sucursal=datos.id_sucursal,
            km_inicial=datos.km_inicial,
            km_proximo_service=datos.km_proximo_service,
            usuario=usuario,
            origen=estados.Origen.WEB,
            fecha_hora=datos.fecha_hora,
            ip=auditoria.ip_desde_request(request),
        )
    sesion.commit()  # sin commit, get_session cierra la sesion y descarta la operacion
    ultimo = service.historial_eventos(sesion, unidad.id)[0]
    return MovimientoOut(unidad=_out(sesion, unidad), evento=_evento_out(sesion, ultimo))


def _evento_out(sesion: Session, evento: Any) -> EventoOut:
    fila = EventoOut.model_validate(evento)
    if evento.id_usuario is not None:
        u = sesion.get(Usuario, evento.id_usuario)
        fila.usuario_nombre = u.nombre if u is not None else None
    return fila


@router.get("", response_model=list[UnidadOut])
def listar(
    estado: Optional[list[str]] = Query(default=None, description="Uno o varios estados"),
    circuito: Optional[Circuito] = None,
    q: Optional[str] = Query(default=None, description="Patente o VIN (parcial)"),
    usuario: Any = Depends(obtener_usuario),
    sesion: Session = Depends(get_session),
) -> list[UnidadOut]:
    unidades = service.listar_unidades(sesion, estados_unidad=estado, circuito=circuito, texto=q)
    return [_out(sesion, u) for u in service.filtrar_por_perfil(sesion, usuario, unidades)]


@router.get("/recientes", response_model=list[AltaRecienteOut])
def recientes(
    limite: int = Query(default=5, ge=1, le=50),
    usuario: Any = Depends(obtener_usuario),
    sesion: Session = Depends(get_session),
) -> list[AltaRecienteOut]:
    return [
        AltaRecienteOut(id=u.id, patente=u.patente, fecha_hora=e.fecha_hora, origen=e.origen)
        for u, e in service.altas_recientes(sesion, limite)
        if service.filtrar_por_perfil(sesion, usuario, [u])
    ]


@router.get("/limite-rotacion", response_model=LimiteRotacionOut)
def limite_rotacion(
    circuito: Circuito,
    usuario: Any = Depends(obtener_usuario),
    sesion: Session = Depends(get_session),
) -> LimiteRotacionOut:
    """HU-02.4: limite que tendria una unidad dada de alta ahora en ese circuito."""
    ahora = datetime.now(timezone.utc)
    por_defecto = "6" if circuito is Circuito.COMERCIAL else "12"
    return LimiteRotacionOut(
        circuito=circuito,
        meses=int(valor_parametro(sesion, "plazo_rotacion_meses", por_defecto, circuito=circuito.value)),
        fecha_limite=service.fecha_limite_rotacion(sesion, circuito, ahora),
    )


@router.get("/{id_unidad}/asignaciones", response_model=list[AsignacionHistorialOut])
def asignaciones(
    id_unidad: int,
    usuario: Any = Depends(obtener_usuario),
    sesion: Session = Depends(get_session),
) -> list[AsignacionHistorialOut]:
    service.verificar_acceso(sesion, usuario, service.obtener_unidad(sesion, id_unidad))
    filas = []
    for a in service.asignaciones_de(sesion, id_unidad):
        responsable = sesion.get(Usuario, a.id_responsable)
        sucursal = sesion.scalar(select(Sucursal).where(Sucursal.codigo == a.id_sucursal))
        filas.append(
            AsignacionHistorialOut(
                id_sucursal=a.id_sucursal,
                sucursal_nombre=sucursal.nombre if sucursal is not None else None,
                responsable_nombre=responsable.nombre if responsable is not None else None,
                fecha_desde=a.fecha_desde,
                fecha_hasta=a.fecha_hasta,
            )
        )
    return filas


@router.get("/{id_unidad}", response_model=FichaUnidadOut)
def ficha(
    id_unidad: int,
    usuario: Any = Depends(obtener_usuario),
    sesion: Session = Depends(get_session),
) -> FichaUnidadOut:
    """HU-07.1: estado, responsable actual, kilometraje, proximo service y limite de rotacion."""
    unidad = service.obtener_unidad(sesion, id_unidad)
    service.verificar_acceso(sesion, usuario, unidad)
    resp = service.responsable_en(sesion, id_unidad, None)
    return FichaUnidadOut(
        unidad=_out(sesion, unidad),
        responsable_actual=(
            ResponsableOut(
                tipo=resp.tipo, identificador=resp.identificador, nombre=resp.nombre,
                evento_id=resp.evento_id, desde=resp.desde, hasta=resp.hasta,
            )
            if resp
            else None
        ),
        acciones_permitidas=estados.acciones_permitidas_desde(estados.EstadoUnidad(unidad.estado_actual)),
    )


@router.get("/{id_unidad}/historial", response_model=HistorialOut)
def historial(
    id_unidad: int,
    usuario: Any = Depends(obtener_usuario),
    sesion: Session = Depends(get_session),
) -> HistorialOut:
    """HU-07.2: eventos en orden cronologico inverso con fecha, hora, usuario y origen."""
    service.verificar_acceso(sesion, usuario, service.obtener_unidad(sesion, id_unidad))
    eventos = service.historial_eventos(sesion, id_unidad)
    return HistorialOut(id_unidad=id_unidad, eventos=[_evento_out(sesion, e) for e in eventos])


@router.get("/{id_unidad}/responsable", response_model=Optional[ResponsableOut])
def responsable(
    id_unidad: int,
    en: Optional[datetime] = Query(default=None, description="Instante de consulta (ISO 8601)"),
    usuario: Any = Depends(obtener_usuario),
    sesion: Session = Depends(get_session),
) -> Optional[ResponsableOut]:
    """HU-07.4: responsable vigente en una fecha y hora; null si no hay ninguno."""
    service.verificar_acceso(sesion, usuario, service.obtener_unidad(sesion, id_unidad))
    resp = service.responsable_en(sesion, id_unidad, en)
    if resp is None:
        return None
    return ResponsableOut(
        tipo=resp.tipo, identificador=resp.identificador, nombre=resp.nombre,
        evento_id=resp.evento_id, desde=resp.desde, hasta=resp.hasta,
    )


@router.post("/{id_unidad}/asignaciones", response_model=MovimientoOut)
def asignar(
    id_unidad: int,
    datos: AsignacionIn,
    request: Request,
    usuario: Any = Depends(requerir_rol(Rol.RESP_MKT_VENTAS.value)),
    sesion: Session = Depends(get_session),
) -> MovimientoOut:
    """HU-03.1: DISPONIBLE -> ASIGNADA."""
    with sesion.begin_nested():
        unidad, evento = service.asignar(
            sesion, id_unidad,
            id_responsable=datos.id_responsable, id_sucursal=datos.id_sucursal, motivo=datos.motivo,
            usuario=usuario, reasignacion=False, fecha_hora=datos.fecha_hora,
            ip=auditoria.ip_desde_request(request),
        )
    sesion.commit()
    return MovimientoOut(unidad=_out(sesion, unidad), evento=_evento_out(sesion, evento))


@router.post("/{id_unidad}/reasignar", response_model=MovimientoOut)
def reasignar(
    id_unidad: int,
    datos: AsignacionIn,
    request: Request,
    usuario: Any = Depends(requerir_rol(Rol.RESP_MKT_VENTAS.value)),
    sesion: Session = Depends(get_session),
) -> MovimientoOut:
    """HU-03.4: cierra la asignacion vigente y abre otra (ASIGNADA -> ASIGNADA)."""
    with sesion.begin_nested():
        unidad, evento = service.asignar(
            sesion, id_unidad,
            id_responsable=datos.id_responsable, id_sucursal=datos.id_sucursal, motivo=datos.motivo,
            usuario=usuario, reasignacion=True, fecha_hora=datos.fecha_hora,
            ip=auditoria.ip_desde_request(request),
        )
    sesion.commit()
    return MovimientoOut(unidad=_out(sesion, unidad), evento=_evento_out(sesion, evento))


@router.post("/{id_unidad}/liberar", response_model=MovimientoOut)
def liberar(
    id_unidad: int,
    datos: LiberacionIn,
    request: Request,
    usuario: Any = Depends(requerir_rol(Rol.RESP_MKT_VENTAS.value)),
    sesion: Session = Depends(get_session),
) -> MovimientoOut:
    """HU-03.5: cierra la asignacion vigente y vuelve a DISPONIBLE."""
    with sesion.begin_nested():
        unidad, evento = service.liberar(
            sesion, id_unidad, usuario=usuario, motivo=datos.motivo, fecha_hora=datos.fecha_hora,
            ip=auditoria.ip_desde_request(request),
        )
    sesion.commit()
    return MovimientoOut(unidad=_out(sesion, unidad), evento=_evento_out(sesion, evento))


@router.post("/{id_unidad}/service/ingreso", response_model=MovimientoOut)
def service_ingreso(
    id_unidad: int,
    datos: ServiceIngresoIn,
    request: Request,
    usuario: Any = Depends(requerir_rol(Rol.RESP_POSVENTA.value, Rol.RESP_MKT_VENTAS.value)),
    sesion: Session = Depends(get_session),
) -> MovimientoOut:
    """HU-07.5: DISPONIBLE -> EN_SERVICE."""
    with sesion.begin_nested():
        unidad, evento = service.service_ingreso(
            sesion, id_unidad, usuario=usuario, observaciones=datos.observaciones, fecha_hora=datos.fecha_hora,
            ip=auditoria.ip_desde_request(request),
        )
    sesion.commit()
    return MovimientoOut(unidad=_out(sesion, unidad), evento=_evento_out(sesion, evento))


@router.post("/{id_unidad}/service/fin", response_model=MovimientoOut)
def service_fin(
    id_unidad: int,
    datos: ServiceFinIn,
    request: Request,
    usuario: Any = Depends(requerir_rol(Rol.RESP_POSVENTA.value, Rol.RESP_MKT_VENTAS.value)),
    sesion: Session = Depends(get_session),
) -> MovimientoOut:
    """HU-07.5: EN_SERVICE -> DISPONIBLE con km y proximo service actualizados."""
    with sesion.begin_nested():
        unidad, evento = service.service_fin(
            sesion, id_unidad, km=datos.km, proximo_service_km=datos.proximo_service_km,
            usuario=usuario, fecha_hora=datos.fecha_hora,
            ip=auditoria.ip_desde_request(request),
        )
    sesion.commit()
    return MovimientoOut(unidad=_out(sesion, unidad), evento=_evento_out(sesion, evento))
