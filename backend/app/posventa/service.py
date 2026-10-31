"""Servicio de prestamos por garantia (HU-05 y HU-06) a traves del motor de estados."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import alertas, estados
from app.core.auditoria import registrar as auditar
from app.core.config import settings
from app.core.excepciones import ErrorDominio, NoEncontrado
from app.posventa.models import Prestamo
from app.tablas_generales.models import Cliente
from app.unidades.models import Circuito, UnidadDemo
from app.unidades.service import obtener_unidad_bloqueada, validar_carga_diferida

ITEMS_CONTROL_PREVIO = ("service_al_dia", "documentacion_y_seguro", "sin_danos_visibles", "accesorios_completos")


def _hoy() -> date:
    return datetime.now(ZoneInfo(settings.timezone_display)).date()


def service_vencido(unidad: UnidadDemo, km_entrega: int) -> bool:
    """HU-05.2: vencido segun el kilometraje, el actual o el que se declara al entregar;
    sin proximo service cargado no hay vencimiento."""
    return unidad.km_proximo_service is not None and max(unidad.km_actual, km_entrega) >= unidad.km_proximo_service


def _cliente(sesion: Session, documento: str, nombre: Optional[str]) -> Cliente:
    documento = documento.strip()
    cliente = sesion.scalar(select(Cliente).where(Cliente.documento == documento))
    if cliente is not None:
        return cliente
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorDominio(
            codigo="CLIENTE_SIN_NOMBRE",
            mensaje="El cliente no está registrado: indique su nombre.",
            detalle={"campos": ["cliente_nombre"]},
            estado_http=422,
        )
    cliente = Cliente(documento=documento, nombre=nombre)
    sesion.add(cliente)
    sesion.flush()
    return cliente


def _validar_control_previo(control: dict[str, bool], observaciones: Optional[str]) -> None:
    """HU-05.1 y HU-05.4: el control se completa entero; un item sin marcar exige observacion."""
    faltantes = [i for i in ITEMS_CONTROL_PREVIO if i not in control]
    desconocidos = [i for i in control if i not in ITEMS_CONTROL_PREVIO]
    if faltantes or desconocidos:
        raise ErrorDominio(
            codigo="CONTROL_INCOMPLETO",
            mensaje="El control previo debe informar todos sus ítems.",
            detalle={"faltantes": faltantes, "desconocidos": desconocidos},
            estado_http=422,
        )
    sin_marcar = [i for i in ITEMS_CONTROL_PREVIO if not control[i]]
    if sin_marcar and not (observaciones or "").strip():
        raise ErrorDominio(
            codigo="OBSERVACION_REQUERIDA",
            mensaje="Un ítem del control previo sin marcar exige una observación que lo justifique.",
            detalle={"sin_marcar": sin_marcar},
            estado_http=422,
        )


def registrar_entrega(
    sesion: Session,
    id_unidad: int,
    *,
    nro_orden_reparacion: str,
    cliente_documento: str,
    fecha_devolucion_prevista: date,
    km_entrega: int,
    combustible_entrega: int,
    control_previo: dict[str, bool],
    usuario: Any,
    cliente_nombre: Optional[str] = None,
    observaciones: Optional[str] = None,
    origen: estados.Origen = estados.Origen.WEB,
    fecha_hora: Optional[datetime] = None,
    ip: Optional[str] = None,
) -> tuple[UnidadDemo, Prestamo]:
    """HU-05: DISPONIBLE -> EN_PRESTAMO; el cliente responde desde la hora de entrega."""
    unidad = obtener_unidad_bloqueada(sesion, id_unidad)
    instante = validar_carga_diferida(sesion, id_unidad, fecha_hora)
    _validar_control_previo(control_previo, observaciones)

    dia_entrega = (instante or datetime.now(timezone.utc)).astimezone(ZoneInfo(settings.timezone_display)).date()
    if fecha_devolucion_prevista < dia_entrega:
        raise ErrorDominio(
            codigo="DEVOLUCION_PREVISTA_INVALIDA",
            mensaje="La devolución prevista no puede ser anterior a la entrega.",
            estado_http=422,
        )

    precondiciones: list[str] = []
    if unidad.circuito is not Circuito.POSVENTA:
        precondiciones.append("Solo las unidades del circuito POSVENTA se prestan por garantía.")
    if service_vencido(unidad, km_entrega):
        precondiciones.append(
            f"La unidad tiene el service vencido ({max(unidad.km_actual, km_entrega)} km; "
            f"próximo a {unidad.km_proximo_service} km)."
        )
    if km_entrega < unidad.km_actual:
        precondiciones.append(f"El kilometraje ({km_entrega}) no puede ser menor al actual ({unidad.km_actual}).")

    cliente = _cliente(sesion, cliente_documento, cliente_nombre)
    evento = estados.transicionar(
        sesion, unidad, estados.TipoEvento.PRESTAMO, usuario, origen,
        datos={
            "id_cliente": cliente.id,
            "nombre_cliente": cliente.nombre,
            "nro_orden_reparacion": nro_orden_reparacion,
            "km": km_entrega,
            "combustible": combustible_entrega,
        },
        fecha_hora=instante,
        precondiciones=tuple(precondiciones),
    )
    prestamo = Prestamo(
        id_unidad=unidad.id,
        id_cliente=cliente.id,
        nro_orden_reparacion=nro_orden_reparacion,
        id_usuario_entrega=usuario.id,
        fecha_hora_entrega=evento.fecha_hora,
        km_entrega=km_entrega,
        combustible_entrega=combustible_entrega,
        control_previo=control_previo,
        estado_entrega=observaciones,
        fecha_devolucion_prevista=fecha_devolucion_prevista,
    )
    sesion.add(prestamo)
    unidad.km_actual = km_entrega
    alertas.verificar_service_proximo(sesion, unidad)
    sesion.flush()
    auditar(sesion, id_usuario=usuario.id, accion="PRESTAMO_ENTREGA", recurso=f"unidad:{unidad.id}", ip=ip, resultado="EXITO")
    return unidad, prestamo


def registrar_devolucion(
    sesion: Session,
    id_prestamo: int,
    *,
    km_devolucion: int,
    combustible_devolucion: int,
    estado_devolucion: str,
    usuario: Any,
    con_danos: bool = False,
    origen: estados.Origen = estados.Origen.WEB,
    fecha_hora: Optional[datetime] = None,
    ip: Optional[str] = None,
) -> tuple[UnidadDemo, Prestamo]:
    """HU-06: EN_PRESTAMO -> DISPONIBLE; una devolucion con danos genera una alerta."""
    prestamo = sesion.get(Prestamo, id_prestamo)
    if prestamo is None:
        raise NoEncontrado("el préstamo")
    unidad = obtener_unidad_bloqueada(sesion, prestamo.id_unidad)
    sesion.refresh(prestamo)  # con la unidad bloqueada: otro pedido pudo cerrarlo mientras se esperaba
    if prestamo.fecha_hora_devolucion is not None:
        raise ErrorDominio(codigo="PRESTAMO_CERRADO", mensaje="Este préstamo ya fue devuelto.", estado_http=409)
    instante = validar_carga_diferida(sesion, prestamo.id_unidad, fecha_hora)

    precondiciones: tuple[str, ...] = ()
    if km_devolucion < prestamo.km_entrega:
        precondiciones = (
            f"El kilometraje de devolución ({km_devolucion}) no puede ser menor al de entrega ({prestamo.km_entrega}).",
        )
    evento = estados.transicionar(
        sesion, unidad, estados.TipoEvento.DEVOLUCION, usuario, origen,
        datos={"km": km_devolucion, "combustible": combustible_devolucion, "con_danos": con_danos},
        fecha_hora=instante,
        precondiciones=precondiciones,
    )
    prestamo.fecha_hora_devolucion = evento.fecha_hora
    prestamo.km_devolucion = km_devolucion
    prestamo.combustible_devolucion = combustible_devolucion
    prestamo.estado_devolucion = estado_devolucion
    prestamo.id_usuario_recepcion = usuario.id
    unidad.km_actual = km_devolucion
    alertas.verificar_service_proximo(sesion, unidad)
    if con_danos:
        alertas.generar(
            sesion,
            "DEVOLUCION_CON_DANOS",
            f"Devolución con daños de {unidad.patente}: {estado_devolucion}",
            id_unidad=unidad.id,
        )
    sesion.flush()
    auditar(sesion, id_usuario=usuario.id, accion="PRESTAMO_DEVOLUCION", recurso=f"unidad:{unidad.id}", ip=ip, resultado="EXITO")
    return unidad, prestamo


def listar_prestamos(sesion: Session, *, activos: bool = True) -> list[tuple[Prestamo, UnidadDemo, Cliente, bool]]:
    """Prestamos con unidad, cliente y marca de demorado (HU-06.3), los mas recientes primero."""
    consulta = (
        select(Prestamo, UnidadDemo, Cliente)
        .join(UnidadDemo, UnidadDemo.id == Prestamo.id_unidad)
        .join(Cliente, Cliente.id == Prestamo.id_cliente)
        .order_by(Prestamo.fecha_hora_entrega.desc())
    )
    if activos:
        consulta = consulta.where(Prestamo.fecha_hora_devolucion.is_(None))
    hoy = _hoy()
    return [
        (p, u, c, p.fecha_hora_devolucion is None and p.fecha_devolucion_prevista < hoy)
        for p, u, c in sesion.execute(consulta).all()
    ]
