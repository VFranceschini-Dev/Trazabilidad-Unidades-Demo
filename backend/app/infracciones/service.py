"""Servicio del circuito de actas: ingesta, validacion, sugerencia, imputacion y pago."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import alertas, estados
from app.core.auditoria import registrar as auditar
from app.core.config import settings
from app.core.excepciones import ErrorDominio, NoEncontrado
from app.core.historial import responsable_vigente
from app.identidad.models import Rol, Usuario
from app.infracciones.esquemas import LecturaIn, ValidarIn
from app.infracciones.models import EstadoActa, Infraccion
from app.integraciones.traccar import describir_para_acta, posicion_cercana
from app.tablas_generales.models import valor_parametro
from app.unidades.models import Circuito, EventoUnidad, UnidadDemo
from app.unidades.service import obtener_unidad_bloqueada

ROL_POR_CIRCUITO = {Circuito.COMERCIAL: Rol.RESP_MKT_VENTAS, Circuito.POSVENTA: Rol.RESP_POSVENTA}


@dataclass(frozen=True)
class Sugerencia:
    tipo: str
    identificador: int
    nombre: str
    sin_responsable: bool
    evento_tipo: Optional[str]
    desde: Optional[datetime]
    hasta: Optional[datetime]
    posicion: str


def umbral_confianza(sesion: Session) -> int:
    return int(valor_parametro(sesion, "umbral_ocr", "80"))


def obtener(sesion: Session, id_infraccion: int) -> Infraccion:
    acta = sesion.get(Infraccion, id_infraccion)
    if acta is None:
        raise NoEncontrado("el acta")
    return acta


def _exigir_estado(acta: Infraccion, *permitidos: EstadoActa) -> None:
    if acta.estado not in {e.value for e in permitidos}:
        raise ErrorDominio(
            codigo="ESTADO_ACTA_INVALIDO",
            mensaje=f"La operación no corresponde a un acta en estado {acta.estado}.",
            detalle={"estado_actual": acta.estado},
            estado_http=409,
        )


def _unidad_por_patente(sesion: Session, patente: Optional[str]) -> Optional[UnidadDemo]:
    if not patente:
        return None
    return sesion.scalar(select(UnidadDemo).where(UnidadDemo.patente == patente))


def unidad_existente(sesion: Session, acta: Infraccion) -> bool:
    return _unidad_por_patente(sesion, acta.patente_leida) is not None


def ruta_pdf(acta: Infraccion) -> Path:
    return Path(settings.actas_dir) / acta.archivo_pdf


def normalizar_patente(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


def ingresar(sesion: Session, lectura: LecturaIn) -> tuple[Infraccion, bool]:
    """HU-08: devuelve (acta, creada). El PDF ya lo guardo n8n en la carpeta compartida; si el
    numero estaba registrado no se duplica y se borra el PDF repetido."""
    archivo = Path(settings.actas_dir) / lectura.archivo_pdf
    if not archivo.is_file():
        raise ErrorDominio(
            codigo="PDF_NO_ENCONTRADO", mensaje=f"No se encuentra el PDF {lectura.archivo_pdf}.", estado_http=422
        )
    with archivo.open("rb") as pdf:
        if pdf.read(5) != b"%PDF-":
            raise ErrorDominio(codigo="ARCHIVO_NO_PDF", mensaje="El archivo recibido no es un PDF.", estado_http=422)

    if lectura.nro_acta:
        existente = sesion.scalar(select(Infraccion).where(Infraccion.nro_acta == lectura.nro_acta))
        if existente is not None:
            if existente.archivo_pdf != lectura.archivo_pdf:
                archivo.unlink(missing_ok=True)
            return existente, False

    acta = Infraccion(
        nro_acta=lectura.nro_acta,
        patente_leida=normalizar_patente(lectura.patente)[:9] if lectura.patente else None,
        fecha_hora_infraccion=lectura.fecha_hora,
        jurisdiccion=lectura.jurisdiccion,
        monto=lectura.monto,
        fecha_vencimiento=lectura.vencimiento,
        archivo_pdf=lectura.archivo_pdf,
        confianza_ocr=lectura.confianza,
        confianza_campos=lectura.confianza_campos,
    )
    try:
        with sesion.begin_nested():
            sesion.add(acta)
            sesion.flush()
    except IntegrityError:  # otra ingesta simultanea registro el mismo numero
        archivo.unlink(missing_ok=True)
        return sesion.scalar(select(Infraccion).where(Infraccion.nro_acta == lectura.nro_acta)), False
    alertas.generar(
        sesion,
        "ACTA_A_VALIDAR",
        f"Acta {lectura.nro_acta or 'sin datos legibles'} pendiente de validación.",
        id_infraccion=acta.id_infraccion,
    )
    auditar(sesion, id_usuario=None, accion="ACTA_INGESTA", recurso=f"acta:{acta.id_infraccion}", ip=None, resultado="EXITO")
    return acta, True


def listar(sesion: Session, estado: Optional[EstadoActa] = None) -> list[Infraccion]:
    consulta = select(Infraccion).order_by(Infraccion.fecha_recepcion.desc(), Infraccion.id_infraccion.desc())
    if estado is not None:
        consulta = consulta.where(Infraccion.estado == estado.value)
    return list(sesion.scalars(consulta))


def validar(sesion: Session, id_infraccion: int, datos: ValidarIn, usuario: Any, ip: Optional[str] = None) -> Infraccion:
    """HU-09.3 y HU-09.4: la patente debe ser de una unidad demo; queda VALIDADA con quien valido."""
    acta = obtener(sesion, id_infraccion)
    _exigir_estado(acta, EstadoActa.PENDIENTE_VALIDACION)

    patente = normalizar_patente(datos.patente)
    unidad = _unidad_por_patente(sesion, patente)
    if unidad is None:
        raise ErrorDominio(
            codigo="PATENTE_SIN_UNIDAD",
            mensaje=f"La patente {patente} no corresponde a ninguna unidad demo. Corríjala o rechace el acta.",
            detalle={"patente": patente},
            estado_http=409,
        )
    otra = sesion.scalar(
        select(Infraccion).where(Infraccion.nro_acta == datos.nro_acta, Infraccion.id_infraccion != acta.id_infraccion)
    )
    if otra is not None:
        raise ErrorDominio(
            codigo="ACTA_DUPLICADA",
            mensaje=f"Ya existe un acta con el número {datos.nro_acta}.",
            detalle={"id_infraccion": otra.id_infraccion},
            estado_http=409,
        )
    instante = datos.fecha_hora_infraccion
    if instante.tzinfo is None:
        raise ErrorDominio(codigo="FECHA_SIN_ZONA", mensaje="La fecha y hora debe indicar su zona horaria.", estado_http=422)
    if instante > datetime.now(timezone.utc):
        raise ErrorDominio(codigo="FECHA_FUTURA", mensaje="La fecha de la infracción no puede ser futura.", estado_http=422)

    acta.nro_acta = datos.nro_acta
    acta.patente_leida = patente[:9]
    acta.fecha_hora_infraccion = instante
    acta.jurisdiccion = datos.jurisdiccion
    acta.monto = datos.monto
    acta.fecha_vencimiento = datos.fecha_vencimiento
    acta.id_unidad = unidad.id
    acta.estado = EstadoActa.VALIDADA.value
    acta.id_usuario_validacion = usuario.id
    acta.fecha_validacion = datetime.now(timezone.utc)
    alertas.cerrar(sesion, "ACTA_A_VALIDAR", usuario, "Acta validada", id_infraccion=acta.id_infraccion)
    auditar(sesion, id_usuario=usuario.id, accion="ACTA_VALIDADA", recurso=f"acta:{acta.id_infraccion}", ip=ip, resultado="EXITO")
    sesion.flush()
    return acta


def rechazar(sesion: Session, id_infraccion: int, motivo: str, usuario: Any, ip: Optional[str] = None) -> Infraccion:
    acta = obtener(sesion, id_infraccion)
    _exigir_estado(acta, EstadoActa.PENDIENTE_VALIDACION, EstadoActa.VALIDADA)
    acta.estado = EstadoActa.RECHAZADA.value
    acta.motivo_rechazo = motivo
    alertas.cerrar(sesion, "ACTA_A_VALIDAR", usuario, "Acta rechazada", id_infraccion=acta.id_infraccion)
    auditar(sesion, id_usuario=usuario.id, accion="ACTA_RECHAZADA", recurso=f"acta:{acta.id_infraccion}", ip=ip, resultado="EXITO")
    sesion.flush()
    return acta


def _responsable_del_circuito(sesion: Session, unidad: UnidadDemo) -> Usuario:
    rol = ROL_POR_CIRCUITO[unidad.circuito]
    usuario = sesion.scalar(select(Usuario).where(Usuario.rol == rol, Usuario.activo.is_(True)).order_by(Usuario.id))
    if usuario is None:
        raise ErrorDominio(
            codigo="SIN_RESPONSABLE_CIRCUITO",
            mensaje=f"No hay un usuario activo con el perfil {rol.value} para imputar el acta.",
            estado_http=409,
        )
    return usuario


def sugerir(sesion: Session, id_infraccion: int) -> Sugerencia:
    """HU-10.1 y HU-10.4: quien respondia en ese instante o, si nadie, el responsable del circuito."""
    acta = obtener(sesion, id_infraccion)
    _exigir_estado(acta, EstadoActa.VALIDADA)
    unidad = sesion.get(UnidadDemo, acta.id_unidad)
    vigente = responsable_vigente(sesion, unidad.id, acta.fecha_hora_infraccion)
    posicion = posicion_cercana(unidad.id_dispositivo_traccar, acta.fecha_hora_infraccion)
    texto_posicion = describir_para_acta(posicion, acta.jurisdiccion)
    if vigente is None:
        usuario = _responsable_del_circuito(sesion, unidad)
        return Sugerencia("USUARIO", usuario.id, usuario.nombre, True, None, None, None, texto_posicion)
    evento = sesion.get(EventoUnidad, vigente.evento_id)
    return Sugerencia(
        vigente.tipo, vigente.identificador, vigente.nombre, False,
        evento.tipo_evento if evento else None, vigente.desde, vigente.hasta, texto_posicion,
    )


def imputar(sesion: Session, id_infraccion: int, usuario: Any, ip: Optional[str] = None) -> Infraccion:
    """HU-10.3 y HU-10.4: el responsable lo calcula el servidor; deja el evento en el historial."""
    acta = obtener(sesion, id_infraccion)
    _exigir_estado(acta, EstadoActa.VALIDADA)
    unidad = obtener_unidad_bloqueada(sesion, acta.id_unidad)
    sesion.refresh(acta)
    _exigir_estado(acta, EstadoActa.VALIDADA)

    sugerencia = sugerir(sesion, id_infraccion)
    if sugerencia.tipo == "CLIENTE":
        acta.id_resp_cliente = sugerencia.identificador
    else:
        acta.id_resp_usuario = sugerencia.identificador
    acta.estado = EstadoActa.IMPUTADA.value
    estados.transicionar(
        sesion, unidad, estados.TipoEvento.INFRACCION, usuario, estados.Origen.WEB,
        datos={
            "nro_acta": acta.nro_acta,
            "monto": str(acta.monto),
            "jurisdiccion": acta.jurisdiccion,
            "responsable": sugerencia.nombre,
            "sin_responsable": sugerencia.sin_responsable,
        },
    )
    if sugerencia.sin_responsable:
        alertas.generar(
            sesion,
            "SIN_RESPONSABLE",
            f"Acta {acta.nro_acta} de {unidad.patente} imputada a {sugerencia.nombre}: "
            "no había un responsable identificable.",
            id_unidad=unidad.id,
            id_infraccion=acta.id_infraccion,
        )
    auditar(sesion, id_usuario=usuario.id, accion="ACTA_IMPUTADA", recurso=f"acta:{acta.id_infraccion}", ip=ip, resultado="EXITO")
    sesion.flush()
    return acta


def pagar(sesion: Session, id_infraccion: int, usuario: Any, ip: Optional[str] = None) -> Infraccion:
    acta = obtener(sesion, id_infraccion)
    _exigir_estado(acta, EstadoActa.IMPUTADA)
    acta.estado = EstadoActa.PAGADA.value
    auditar(sesion, id_usuario=usuario.id, accion="ACTA_PAGADA", recurso=f"acta:{acta.id_infraccion}", ip=ip, resultado="EXITO")
    sesion.flush()
    return acta


def nombre_responsable(sesion: Session, acta: Infraccion) -> Optional[str]:
    from app.tablas_generales.models import Cliente

    if acta.id_resp_usuario is not None:
        return sesion.get(Usuario, acta.id_resp_usuario).nombre
    if acta.id_resp_cliente is not None:
        return sesion.get(Cliente, acta.id_resp_cliente).nombre
    return None
