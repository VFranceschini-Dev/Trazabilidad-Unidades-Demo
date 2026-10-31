"""Servicio de uso comercial (HU-04): salida y regreso a traves del motor de estados."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.comercial.models import TipoUso, UsoComercial
from app.core import alertas, estados
from app.core.auditoria import registrar as auditar
from app.core.excepciones import ErrorDominio, NoEncontrado
from app.tablas_generales.models import Cliente
from app.unidades.models import Asignacion, UnidadDemo
from app.unidades.service import obtener_unidad_bloqueada, validar_carga_diferida


def _responsable_asignado(sesion: Session, id_unidad: int) -> Optional[int]:
    return sesion.scalar(
        select(Asignacion.id_responsable).where(Asignacion.id_unidad == id_unidad, Asignacion.fecha_hasta.is_(None))
    )


def registrar_salida(
    sesion: Session,
    id_unidad: int,
    *,
    tipo_uso: TipoUso,
    km_salida: int,
    usuario: Any,
    cliente_nombre: Optional[str] = None,
    cliente_telefono: Optional[str] = None,
    observaciones: Optional[str] = None,
    origen: estados.Origen = estados.Origen.WEB,
    fecha_hora: Optional[datetime] = None,
    ip: Optional[str] = None,
) -> tuple[UnidadDemo, UsoComercial]:
    """HU-04.1 y HU-04.2: ASIGNADA -> EN_USO; un test drive exige los datos del prospecto."""
    unidad = obtener_unidad_bloqueada(sesion, id_unidad)
    instante = validar_carga_diferida(sesion, id_unidad, fecha_hora)

    nombre = (cliente_nombre or "").strip()
    telefono = (cliente_telefono or "").strip()
    if tipo_uso is TipoUso.TEST_DRIVE and not (nombre and telefono):
        raise ErrorDominio(
            codigo="DATOS_PROSPECTO",
            mensaje="Un test drive requiere el nombre y el teléfono del cliente prospecto.",
            detalle={"campos": ["cliente_nombre", "cliente_telefono"]},
            estado_http=422,
        )

    precondiciones: list[str] = []
    if _responsable_asignado(sesion, id_unidad) != usuario.id:
        precondiciones.append("La unidad no está asignada a este usuario.")
    if km_salida < unidad.km_actual:
        precondiciones.append(f"El kilometraje ({km_salida}) no puede ser menor al actual ({unidad.km_actual}).")

    evento = estados.transicionar(
        sesion, unidad, estados.TipoEvento.SALIDA, usuario, origen,
        datos={"tipo_uso": tipo_uso.value, "km": km_salida},
        fecha_hora=instante,
        precondiciones=tuple(precondiciones),
    )

    id_cliente = None
    if tipo_uso is TipoUso.TEST_DRIVE:
        cliente = Cliente(nombre=nombre, contacto=telefono)
        sesion.add(cliente)
        sesion.flush()
        id_cliente = cliente.id

    uso = UsoComercial(
        id_unidad=unidad.id,
        tipo_uso=tipo_uso.value,
        id_usuario=usuario.id,
        id_cliente=id_cliente,
        fecha_hora_salida=evento.fecha_hora,
        km_salida=km_salida,
        observaciones=observaciones,
    )
    sesion.add(uso)
    unidad.km_actual = km_salida
    alertas.verificar_service_proximo(sesion, unidad)
    sesion.flush()
    auditar(sesion, id_usuario=usuario.id, accion="USO_SALIDA", recurso=f"unidad:{unidad.id}", ip=ip, resultado="EXITO")
    return unidad, uso


def registrar_regreso(
    sesion: Session,
    id_uso: int,
    *,
    km_regreso: int,
    usuario: Any,
    observaciones: Optional[str] = None,
    origen: estados.Origen = estados.Origen.WEB,
    fecha_hora: Optional[datetime] = None,
    ip: Optional[str] = None,
) -> tuple[UnidadDemo, UsoComercial]:
    """HU-04.3 y HU-04.4: EN_USO -> ASIGNADA, km de regreso >= km de salida."""
    uso = sesion.get(UsoComercial, id_uso)
    if uso is None:
        raise NoEncontrado("el uso")
    unidad = obtener_unidad_bloqueada(sesion, uso.id_unidad)
    sesion.refresh(uso)  # con la unidad bloqueada: otro pedido pudo cerrarlo mientras se esperaba
    if uso.fecha_hora_regreso is not None:
        raise ErrorDominio(codigo="USO_CERRADO", mensaje="Este uso ya tiene el regreso registrado.", estado_http=409)
    instante = validar_carga_diferida(sesion, uso.id_unidad, fecha_hora)

    precondiciones: list[str] = []
    if uso.id_usuario != usuario.id:
        precondiciones.append("El regreso lo registra quien retiró la unidad.")
    if km_regreso < uso.km_salida:
        precondiciones.append(f"El kilometraje de regreso ({km_regreso}) no puede ser menor al de salida ({uso.km_salida}).")

    evento = estados.transicionar(
        sesion, unidad, estados.TipoEvento.REGRESO, usuario, origen,
        datos={"tipo_uso": uso.tipo_uso, "km": km_regreso},
        fecha_hora=instante,
        precondiciones=tuple(precondiciones),
    )
    uso.fecha_hora_regreso = evento.fecha_hora
    uso.km_regreso = km_regreso
    if observaciones:
        uso.observaciones = f"{uso.observaciones}\n{observaciones}" if uso.observaciones else observaciones
    unidad.km_actual = km_regreso
    alertas.verificar_service_proximo(sesion, unidad)
    sesion.flush()
    auditar(sesion, id_usuario=usuario.id, accion="USO_REGRESO", recurso=f"unidad:{unidad.id}", ip=ip, resultado="EXITO")
    return unidad, uso


def unidades_a_cargo(sesion: Session, id_usuario: int) -> list[tuple[UnidadDemo, Optional[UsoComercial]]]:
    """Unidades con asignacion vigente del usuario, con su salida abierta si la hay."""
    unidades = sesion.scalars(
        select(UnidadDemo)
        .join(Asignacion, Asignacion.id_unidad == UnidadDemo.id)
        .where(Asignacion.id_responsable == id_usuario, Asignacion.fecha_hasta.is_(None))
        .order_by(UnidadDemo.patente)
    ).all()
    return [
        (
            unidad,
            sesion.scalar(
                select(UsoComercial).where(
                    UsoComercial.id_unidad == unidad.id, UsoComercial.fecha_hora_regreso.is_(None)
                )
            ),
        )
        for unidad in unidades
    ]
