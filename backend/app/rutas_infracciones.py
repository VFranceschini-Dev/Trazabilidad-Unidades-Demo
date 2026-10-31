"""Rutas del circuito de actas: ingesta con API key de n8n y gestion por Administracion."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core import auditoria
from app.core.db import get_session
from app.core.excepciones import ErrorDominio
from app.core.seguridad import requerir_rol, verificar_api_key_n8n
from app.identidad.models import Rol, Usuario
from app.infracciones import service
from app.infracciones.esquemas import ActaOut, LecturaIn, RechazarIn, SugerenciaOut, ValidarIn
from app.infracciones.models import EstadoActa, Infraccion
from app.integraciones.vista_pdf import vista_previa

router = APIRouter(prefix="/infracciones", tags=["infracciones"])

solo_administracion = requerir_rol(Rol.ADMINISTRACION.value)


def _out(sesion: Session, acta: Infraccion) -> ActaOut:
    validador = sesion.get(Usuario, acta.id_usuario_validacion) if acta.id_usuario_validacion else None
    return ActaOut(
        id_infraccion=acta.id_infraccion,
        nro_acta=acta.nro_acta,
        patente_leida=acta.patente_leida,
        fecha_hora_infraccion=acta.fecha_hora_infraccion,
        jurisdiccion=acta.jurisdiccion,
        monto=acta.monto,
        fecha_vencimiento=acta.fecha_vencimiento,
        confianza_ocr=acta.confianza_ocr,
        confianza_campos=acta.confianza_campos,
        estado=EstadoActa(acta.estado),
        fecha_recepcion=acta.fecha_recepcion,
        id_unidad=acta.id_unidad,
        unidad_existente=service.unidad_existente(sesion, acta),
        responsable_nombre=service.nombre_responsable(sesion, acta),
        validada_por=validador.nombre if validador else None,
        fecha_validacion=acta.fecha_validacion,
        motivo_rechazo=acta.motivo_rechazo,
        umbral_confianza=service.umbral_confianza(sesion),
    )


@router.post("/ingesta", response_model=ActaOut, status_code=201, dependencies=[Depends(verificar_api_key_n8n)])
def ingesta(lectura: LecturaIn, sesion: Session = Depends(get_session)) -> Any:
    """HU-08: n8n envia los datos que leyo y el nombre del PDF que guardo. 201 si es nueva; 200 con
    la existente si el numero de acta ya estaba registrado."""
    acta, creada = service.ingresar(sesion, lectura)
    sesion.commit()
    salida = _out(sesion, acta)
    return salida if creada else JSONResponse(status_code=200, content=salida.model_dump(mode="json"))


@router.get("", response_model=list[ActaOut])
def listar(
    estado: Optional[EstadoActa] = None,
    usuario: Any = Depends(solo_administracion),
    sesion: Session = Depends(get_session),
) -> list[ActaOut]:
    return [_out(sesion, a) for a in service.listar(sesion, estado)]


@router.get("/{id_infraccion}", response_model=ActaOut)
def detalle(id_infraccion: int, usuario: Any = Depends(solo_administracion), sesion: Session = Depends(get_session)) -> ActaOut:
    return _out(sesion, service.obtener(sesion, id_infraccion))


def _archivo(sesion: Session, id_infraccion: int) -> Any:
    ruta = service.ruta_pdf(service.obtener(sesion, id_infraccion))
    if not ruta.exists():
        raise ErrorDominio(codigo="PDF_NO_DISPONIBLE", mensaje="No se encuentra el PDF del acta.", estado_http=404)
    return ruta


@router.get("/{id_infraccion}/pdf")
def pdf(id_infraccion: int, usuario: Any = Depends(solo_administracion), sesion: Session = Depends(get_session)) -> FileResponse:
    return FileResponse(_archivo(sesion, id_infraccion), media_type="application/pdf", filename=f"acta-{id_infraccion}.pdf")


@router.get("/{id_infraccion}/vista")
def vista(id_infraccion: int, usuario: Any = Depends(solo_administracion), sesion: Session = Depends(get_session)) -> Response:
    """HU-09.1: primera pagina como imagen, para mostrarla junto a los datos."""
    try:
        imagen = vista_previa(_archivo(sesion, id_infraccion).read_bytes())
    except ErrorDominio:
        raise
    except Exception as exc:  # PDF danado: la pantalla sigue permitiendo descargarlo
        raise ErrorDominio(codigo="VISTA_NO_DISPONIBLE", mensaje="No se pudo generar la vista del PDF.", estado_http=422) from exc
    return Response(content=imagen, media_type="image/png")


@router.put("/{id_infraccion}/validar", response_model=ActaOut)
def validar(
    id_infraccion: int,
    datos: ValidarIn,
    request: Request,
    usuario: Any = Depends(solo_administracion),
    sesion: Session = Depends(get_session),
) -> ActaOut:
    acta = service.validar(sesion, id_infraccion, datos, usuario, auditoria.ip_desde_request(request))
    sesion.commit()
    return _out(sesion, acta)


@router.put("/{id_infraccion}/rechazar", response_model=ActaOut)
def rechazar(
    id_infraccion: int,
    datos: RechazarIn,
    request: Request,
    usuario: Any = Depends(solo_administracion),
    sesion: Session = Depends(get_session),
) -> ActaOut:
    acta = service.rechazar(sesion, id_infraccion, datos.motivo, usuario, auditoria.ip_desde_request(request))
    sesion.commit()
    return _out(sesion, acta)


@router.get("/{id_infraccion}/sugerencia", response_model=SugerenciaOut)
def sugerencia(
    id_infraccion: int, usuario: Any = Depends(solo_administracion), sesion: Session = Depends(get_session)
) -> SugerenciaOut:
    s = service.sugerir(sesion, id_infraccion)
    return SugerenciaOut(
        tipo=s.tipo, identificador=s.identificador, nombre=s.nombre, sin_responsable=s.sin_responsable,
        evento_tipo=s.evento_tipo, desde=s.desde, hasta=s.hasta, posicion=s.posicion,
    )


@router.post("/{id_infraccion}/imputar", response_model=ActaOut)
def imputar(
    id_infraccion: int,
    request: Request,
    usuario: Any = Depends(solo_administracion),
    sesion: Session = Depends(get_session),
) -> ActaOut:
    acta = service.imputar(sesion, id_infraccion, usuario, auditoria.ip_desde_request(request))
    sesion.commit()
    return _out(sesion, acta)


@router.post("/{id_infraccion}/pagar", response_model=ActaOut)
def pagar(
    id_infraccion: int,
    request: Request,
    usuario: Any = Depends(solo_administracion),
    sesion: Session = Depends(get_session),
) -> ActaOut:
    acta = service.pagar(sesion, id_infraccion, usuario, auditoria.ip_desde_request(request))
    sesion.commit()
    return _out(sesion, acta)
