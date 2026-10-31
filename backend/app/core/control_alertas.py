"""Control diario de alertas (HU-13) y consulta segun el area de cada perfil."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import alertas
from app.core.config import settings
from app.core.excepciones import ErrorDominio, NoEncontrado, SinPermiso
from app.identidad.models import Rol
from app.infracciones.models import EstadoActa, Infraccion
from app.posventa.models import Prestamo
from app.tablas_generales.models import Alerta, Parametro, valor_parametro
from app.unidades.models import Circuito, UnidadDemo

CLAVE_ULTIMO_CONTROL = "ultimo_control_alertas"
POR_CIRCUITO = {"ROTACION_VENCIDA", "SERVICE_PROXIMO"}
SOLO_POSVENTA = {"PRESTAMO_DEMORADO", "DEVOLUCION_CON_DANOS"}
ADMINISTRACION = {"ACTA_A_VALIDAR", "MULTA_POR_VENCER", "SIN_RESPONSABLE"}
CIRCUITO_DEL_ROL = {Rol.RESP_MKT_VENTAS: Circuito.COMERCIAL, Rol.RESP_POSVENTA: Circuito.POSVENTA}


def ejecutar_control(sesion: Session) -> int:
    """HU-13.1, .2 y .4, y service proximo como respaldo. Devuelve las alertas abiertas."""
    ahora = datetime.now(timezone.utc)
    hoy = ahora.astimezone(ZoneInfo(settings.timezone_display)).date()
    aviso_multa = int(valor_parametro(sesion, "aviso_multa_dias", "5"))

    unidades = sesion.scalars(
        select(UnidadDemo).where(UnidadDemo.estado_actual.not_in(("EN_VENTA", "BAJA")))
    ).all()
    for u in unidades:
        if u.fecha_limite_rotacion is not None and u.fecha_limite_rotacion < ahora:
            vence = u.fecha_limite_rotacion.astimezone(ZoneInfo(settings.timezone_display))
            alertas.generar(
                sesion, "ROTACION_VENCIDA", f"{u.patente} superó el plazo de rotación (vencía {vence:%d/%m/%Y}).", id_unidad=u.id
            )
        alertas.verificar_service_proximo(sesion, u)

    demorados = sesion.execute(
        select(Prestamo, UnidadDemo)
        .join(UnidadDemo, UnidadDemo.id == Prestamo.id_unidad)
        .where(Prestamo.fecha_hora_devolucion.is_(None), Prestamo.fecha_devolucion_prevista < hoy)
    ).all()
    for prestamo, unidad in demorados:
        alertas.generar(
            sesion,
            "PRESTAMO_DEMORADO",
            f"{unidad.patente} debía volver el {prestamo.fecha_devolucion_prevista:%d/%m/%Y} · {prestamo.nro_orden_reparacion}.",
            id_unidad=unidad.id,
        )

    multas = sesion.scalars(
        select(Infraccion).where(
            Infraccion.estado == EstadoActa.IMPUTADA.value,
            Infraccion.fecha_vencimiento <= hoy + timedelta(days=aviso_multa),
        )
    ).all()
    for acta in multas:
        alertas.generar(
            sesion,
            "MULTA_POR_VENCER",
            f"Acta {acta.nro_acta} vence el {acta.fecha_vencimiento:%d/%m/%Y}.",
            id_unidad=acta.id_unidad,
            id_infraccion=acta.id_infraccion,
        )

    fila = sesion.scalar(select(Parametro).where(Parametro.clave == CLAVE_ULTIMO_CONTROL))
    if fila is None:
        sesion.add(Parametro(clave=CLAVE_ULTIMO_CONTROL, valor=ahora.isoformat()))
    else:
        fila.valor = ahora.isoformat()
    sesion.flush()
    return len(sesion.scalars(select(Alerta.id_alerta).where(Alerta.estado == "ABIERTA")).all())


def ultimo_control(sesion: Session) -> Optional[str]:
    fila = sesion.scalar(select(Parametro).where(Parametro.clave == CLAVE_ULTIMO_CONTROL))
    return fila.valor if fila is not None else None


def _le_corresponde(usuario: Any, alerta: Alerta, unidad: Optional[UnidadDemo]) -> bool:
    if alerta.tipo_alerta in ADMINISTRACION:
        return usuario.rol is Rol.ADMINISTRACION
    if alerta.tipo_alerta in SOLO_POSVENTA:
        return usuario.rol is Rol.RESP_POSVENTA
    if alerta.tipo_alerta in POR_CIRCUITO:
        circuito = CIRCUITO_DEL_ROL.get(usuario.rol)
        return circuito is not None and unidad is not None and unidad.circuito is circuito
    return False


def _ve_todas(usuario: Any) -> bool:
    return usuario.rol in (Rol.GERENCIA, Rol.ADMIN)


@dataclass(frozen=True)
class AlertaVisible:
    alerta: Alerta
    unidad: Optional[UnidadDemo]
    puede_cerrar: bool


def listar(sesion: Session, usuario: Any) -> list[AlertaVisible]:
    """Cada area ve las suyas; Gerencia y el Administrador del sistema ven todas sin cerrarlas."""
    filas = sesion.execute(
        select(Alerta, UnidadDemo)
        .outerjoin(UnidadDemo, UnidadDemo.id == Alerta.id_unidad)
        .order_by(Alerta.fecha_creacion.desc(), Alerta.id_alerta.desc())
    ).all()
    visibles = []
    for alerta, unidad in filas:
        propia = _le_corresponde(usuario, alerta, unidad)
        if propia or _ve_todas(usuario):
            visibles.append(AlertaVisible(alerta, unidad, propia and alerta.estado == "ABIERTA"))
    return visibles


def cerrar(sesion: Session, id_alerta: int, accion: str, usuario: Any) -> Alerta:
    """HU-13.5: registra quien la cerro, cuando y la accion realizada."""
    alerta = sesion.get(Alerta, id_alerta)
    if alerta is None:
        raise NoEncontrado("la alerta")
    unidad = sesion.get(UnidadDemo, alerta.id_unidad) if alerta.id_unidad else None
    if not _le_corresponde(usuario, alerta, unidad):
        raise SinPermiso("La alerta no corresponde a su área.")
    if alerta.estado != "ABIERTA":
        raise ErrorDominio(codigo="ALERTA_CERRADA", mensaje="La alerta ya está cerrada.", estado_http=409)
    alerta.estado = "CERRADA"
    alerta.id_usuario_cierre = usuario.id
    alerta.fecha_cierre = datetime.now(timezone.utc)
    alerta.accion_realizada = accion
    sesion.flush()
    return alerta
