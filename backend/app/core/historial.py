"""Responsable vigente de una unidad en un instante, derivado solo del historial de eventos.

Orden de busqueda (docs/especificacion.md):
1. prestamo cuyo intervalo entrega->devolucion contenga el instante;
2. uso comercial cuyo intervalo salida->regreso lo contenga;
3. asignacion vigente en ese instante (fecha_hasta nula = abierta hasta ahora);
4. None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.estados import TipoEvento


@dataclass(frozen=True)
class Responsable:
    tipo: str                 # USUARIO | CLIENTE
    identificador: int
    nombre: str
    evento_id: int            # evento que lo justifica
    desde: datetime
    hasta: datetime | None    # None => intervalo abierto (hasta el momento actual)


def _modelo_evento() -> type[Any]:
    from app.unidades.models import EventoUnidad

    return EventoUnidad


def _modelo_usuario() -> type[Any]:
    from app.identidad.models import Usuario

    return Usuario


def _parejas(
    sesion: Session, id_unidad: int, apertura: TipoEvento, cierre: TipoEvento
) -> list[tuple[Any, Any | None]]:
    """Empareja eventos apertura/cierre por orden cronologico (LIFO por unidad)."""
    EU = _modelo_evento()
    eventos = sesion.scalars(
        select(EU)
        .where(EU.id_unidad == id_unidad, EU.tipo_evento.in_([apertura.value, cierre.value]))
        .order_by(EU.fecha_hora.asc())
    ).all()
    parejas: list[tuple[Any, Any | None]] = []
    pendientes: list[Any] = []
    for ev in eventos:
        if ev.tipo_evento == apertura.value:
            pendientes.append(ev)
        elif pendientes:
            parejas.append((pendientes.pop(), ev))
    for ev in pendientes:
        parejas.append((ev, None))
    return parejas


def responsable_vigente(sesion: Session, id_unidad: int, instante: datetime) -> Responsable | None:
    """Devuelve quien responde por la unidad en `instante`, o None."""
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    ahora = datetime.now(timezone.utc)
    EU = _modelo_evento()

    # 1) Prestamo POSVENTA (cliente): PRESTAMO -> DEVOLUCION
    for ap, ci in _parejas(sesion, id_unidad, TipoEvento.PRESTAMO, TipoEvento.DEVOLUCION):
        desde = ap.fecha_hora
        hasta = ci.fecha_hora if ci else ahora
        if desde <= instante <= hasta:
            datos = ap.datos or {}
            return Responsable(
                tipo="CLIENTE",
                identificador=int(datos.get("id_cliente", 0)),
                nombre=str(datos.get("nombre_cliente", "Cliente")),
                evento_id=ap.id_evento,
                desde=desde,
                hasta=ci.fecha_hora if ci else None,
            )

    # 2) Uso comercial: SALIDA -> REGRESO (el usuario que registró la salida)
    for ap, ci in _parejas(sesion, id_unidad, TipoEvento.SALIDA, TipoEvento.REGRESO):
        desde = ap.fecha_hora
        hasta = ci.fecha_hora if ci else ahora
        if desde <= instante <= hasta and ap.id_usuario is not None:
            usuario = sesion.get(_modelo_usuario(), ap.id_usuario)
            return Responsable(
                tipo="USUARIO",
                identificador=ap.id_usuario,
                nombre=usuario.nombre if usuario else "—",
                evento_id=ap.id_evento,
                desde=desde,
                hasta=ci.fecha_hora if ci else None,
            )

    # 3) Asignacion vigente: ASIGNACION/REASIGNACION mas reciente <= instante
    #    sin LIBERACION ni REASIGNACION posterior antes del instante
    asg = sesion.scalars(
        select(EU)
        .where(
            EU.id_unidad == id_unidad,
            EU.tipo_evento.in_([TipoEvento.ASIGNACION.value, TipoEvento.REASIGNACION.value]),
            EU.fecha_hora <= instante,
        )
        .order_by(EU.fecha_hora.desc())
        .limit(1)
    ).first()
    if asg is not None:
        cierres = sesion.scalars(
            select(EU)
            .where(
                EU.id_unidad == id_unidad,
                EU.tipo_evento.in_([TipoEvento.LIBERACION.value, TipoEvento.REASIGNACION.value]),
                EU.fecha_hora > asg.fecha_hora,
                EU.fecha_hora <= instante,
            )
        ).all()
        if not cierres:
            # En ASIGNACION/REASIGNACION el responsable viaja en datos.id_responsable;
            # id_usuario es quien registro el evento, no quien responde por la unidad.
            datos_asg = asg.datos or {}
            responsable_id = datos_asg.get("id_responsable") or asg.id_usuario
            if responsable_id is not None:
                usuario = sesion.get(_modelo_usuario(), int(responsable_id))
                return Responsable(
                    tipo="USUARIO",
                    identificador=int(responsable_id),
                    nombre=usuario.nombre if usuario else "—",
                    evento_id=asg.id_evento,
                    desde=asg.fecha_hora,
                    hasta=None,
                )
    return None
