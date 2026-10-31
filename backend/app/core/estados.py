"""Motor de estados de la unidad demo.

Una sola funcion `transicionar` que, en una misma transaccion: bloquea la fila de la
unidad (SELECT ... FOR UPDATE), valida la transicion contra la tabla, verifica las
precondiciones del servicio llamador, actualiza `estado_actual` e inserta el evento en
el historial inmutable. Una transicion no prevista devuelve 409 con el estado actual y
las acciones permitidas (ver docs/especificacion.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.excepciones import TransicionInvalida


class EstadoUnidad(str, Enum):
    DISPONIBLE = "DISPONIBLE"
    ASIGNADA = "ASIGNADA"
    EN_USO = "EN_USO"
    EN_PRESTAMO = "EN_PRESTAMO"
    EN_SERVICE = "EN_SERVICE"
    EN_VENTA = "EN_VENTA"
    BAJA = "BAJA"


class TipoEvento(str, Enum):
    ALTA = "ALTA"
    ASIGNACION = "ASIGNACION"
    REASIGNACION = "REASIGNACION"
    LIBERACION = "LIBERACION"
    SALIDA = "SALIDA"
    REGRESO = "REGRESO"
    PRESTAMO = "PRESTAMO"
    DEVOLUCION = "DEVOLUCION"
    INGRESO_SERVICE = "INGRESO_SERVICE"
    FIN_SERVICE = "FIN_SERVICE"
    PASE_VENTA = "PASE_VENTA"
    BAJA = "BAJA"
    POSICION = "POSICION"
    INFRACCION = "INFRACCION"


class Origen(str, Enum):
    """Origen tecnico del evento: solo los valores del diccionario de datos del TFG."""

    WEB = "WEB"
    N8N = "N8N"
    TRACCAR = "TRACCAR"
    DMS = "DMS"


@dataclass(frozen=True)
class ReglaTransicion:
    origen: EstadoUnidad | None      # None => desde cualquier estado (alta o informativos)
    evento: TipoEvento
    destino: EstadoUnidad | None     # None => sin cambio de estado (informativos)
    hu: str


TABLA_TRANSICIONES: tuple[ReglaTransicion, ...] = (
    ReglaTransicion(None, TipoEvento.ALTA, EstadoUnidad.DISPONIBLE, "HU-02"),
    ReglaTransicion(EstadoUnidad.DISPONIBLE, TipoEvento.ASIGNACION, EstadoUnidad.ASIGNADA, "HU-03"),
    ReglaTransicion(EstadoUnidad.ASIGNADA, TipoEvento.REASIGNACION, EstadoUnidad.ASIGNADA, "HU-03"),
    ReglaTransicion(EstadoUnidad.ASIGNADA, TipoEvento.LIBERACION, EstadoUnidad.DISPONIBLE, "HU-03"),
    ReglaTransicion(EstadoUnidad.ASIGNADA, TipoEvento.SALIDA, EstadoUnidad.EN_USO, "HU-04"),
    ReglaTransicion(EstadoUnidad.EN_USO, TipoEvento.REGRESO, EstadoUnidad.ASIGNADA, "HU-04"),
    ReglaTransicion(EstadoUnidad.DISPONIBLE, TipoEvento.PRESTAMO, EstadoUnidad.EN_PRESTAMO, "HU-05"),
    ReglaTransicion(EstadoUnidad.EN_PRESTAMO, TipoEvento.DEVOLUCION, EstadoUnidad.DISPONIBLE, "HU-06"),
    ReglaTransicion(EstadoUnidad.DISPONIBLE, TipoEvento.INGRESO_SERVICE, EstadoUnidad.EN_SERVICE, "HU-07"),
    ReglaTransicion(EstadoUnidad.EN_SERVICE, TipoEvento.FIN_SERVICE, EstadoUnidad.DISPONIBLE, "HU-07"),
    ReglaTransicion(EstadoUnidad.DISPONIBLE, TipoEvento.PASE_VENTA, EstadoUnidad.EN_VENTA, "HU-14"),
    ReglaTransicion(EstadoUnidad.ASIGNADA, TipoEvento.PASE_VENTA, EstadoUnidad.EN_VENTA, "HU-14"),
    ReglaTransicion(EstadoUnidad.EN_VENTA, TipoEvento.BAJA, EstadoUnidad.BAJA, "HU-14"),
    ReglaTransicion(None, TipoEvento.POSICION, None, "HU-11"),
    ReglaTransicion(None, TipoEvento.INFRACCION, None, "HU-10"),
)

_INFORMATIVOS = {TipoEvento.POSICION, TipoEvento.INFRACCION}


def buscar_regla(evento: TipoEvento, estado: EstadoUnidad | None) -> ReglaTransicion | None:
    """Regla aplicable al par (estado, evento); None si la transicion no esta prevista."""
    for r in TABLA_TRANSICIONES:
        if r.evento is evento and (r.origen is None or r.origen is estado):
            return r
    return None


def acciones_permitidas_desde(estado: EstadoUnidad) -> list[str]:
    """Eventos admisibles desde el estado dado (para el detalle del 409)."""
    return sorted(
        {
            r.evento.value
            for r in TABLA_TRANSICIONES
            if r.origen is estado or (r.origen is None and r.evento in _INFORMATIVOS)
        }
    )


def transicionar(
    sesion: Session,
    unidad: Any,
    evento: TipoEvento,
    usuario: Any | None,
    origen: Origen,
    datos: dict[str, Any] | None = None,
    fecha_hora: datetime | None = None,
    precondiciones: tuple[str, ...] = (),
) -> Any:
    """Aplica una transicion completa en la transaccion activa de `sesion`.

    Pasos: SELECT ... FOR UPDATE sobre la unidad, validacion de la regla, chequeo de
    precondiciones (textos ya evaluados por el servicio; cualquiera que llegue
    prohibe la operacion), actualizacion de estado e insercion del evento.
    Devuelve la fila de evento_unidad insertada.
    """
    from app.unidades.models import EventoUnidad  # import local: evita ciclo de modulos

    unidad_fila = sesion.execute(
        select(unidad.__class__)
        .where(unidad.__class__.id == unidad.id)
        .with_for_update()
        # Sin esto, quien espero el bloqueo sigue viendo lo que leyo antes de la otra transaccion
        .execution_options(populate_existing=True)
    ).scalar_one()

    es_alta = evento is TipoEvento.ALTA
    estado_actual = EstadoUnidad(unidad_fila.estado_actual)

    r = buscar_regla(evento, None if es_alta else estado_actual)
    if r is None:
        raise TransicionInvalida(
            estado_actual.value,
            acciones_permitidas_desde(estado_actual),
            f"El evento {evento.value} no esta previsto para una unidad en estado "
            f"{estado_actual.value}.",
        )

    for motivo in precondiciones:
        raise TransicionInvalida(
            estado_actual.value, acciones_permitidas_desde(estado_actual), motivo
        )

    instante = fecha_hora or datetime.now(timezone.utc)
    if instante.tzinfo is None:  # normalizacion defensiva a UTC
        instante = instante.replace(tzinfo=timezone.utc)

    destino = r.destino
    if destino is not None:
        unidad_fila.estado_actual = destino.value

    fila_evento = EventoUnidad(
        id_unidad=unidad_fila.id,
        tipo_evento=evento.value,
        estado_anterior=None if es_alta else estado_actual.value,
        estado_nuevo=destino.value if destino is not None else estado_actual.value,
        fecha_hora=instante,
        id_usuario=getattr(usuario, "id", None),
        origen=origen.value,
        carga_diferida=fecha_hora is not None,
        datos=datos or {},
    )
    sesion.add(fila_evento)
    sesion.flush()
    return fila_evento
