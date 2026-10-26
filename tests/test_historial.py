"""Responsable vigente en un instante: orden de busqueda y bordes exactos (HU-07.4).

Bordes exigidos por el prompt 2: instante igual a la salida, igual al regreso,
intervalos abiertos hasta el momento actual y consulta sin datos. El orden de
busqueda es prestamo > uso comercial > asignacion vigente > None.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core import estados
from app.core.historial import responsable_vigente
from app.unidades import service

from soporte import alta_unidad, transicionar

T = estados.TipoEvento
UTC = timezone.utc

D0 = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
D1 = D0 + timedelta(days=1)
D2 = D0 + timedelta(days=2)
D3 = D0 + timedelta(days=3)


def _asignacion(sesion, base, unidad, instante, responsable=None):
    return transicionar(
        sesion,
        unidad,
        T.ASIGNACION,
        base.mkt,
        {"id_responsable": (responsable or base.asesor).id, "id_sucursal": unidad.id_sucursal},
        fecha_hora=instante,
    )


def test_sin_datos_devuelve_none(sesion, base) -> None:
    unidad = alta_unidad(sesion, base, fecha_hora=D0)
    assert responsable_vigente(sesion, unidad.id, D1) is None


def test_asignacion_vigente_devuelve_al_responsable(sesion, base) -> None:
    unidad = alta_unidad(sesion, base, fecha_hora=D0)
    evento = _asignacion(sesion, base, unidad, D1)
    resp = responsable_vigente(sesion, unidad.id, D1 + timedelta(hours=1))
    assert resp is not None
    assert resp.tipo == "USUARIO"
    assert resp.identificador == base.asesor.id
    assert resp.nombre == base.asesor.nombre
    assert resp.evento_id == evento.id_evento
    assert resp.desde == D1
    assert resp.hasta is None


def test_instante_anterior_a_la_asignacion(sesion, base) -> None:
    unidad = alta_unidad(sesion, base, fecha_hora=D0)
    _asignacion(sesion, base, unidad, D1)
    assert responsable_vigente(sesion, unidad.id, D0 + timedelta(hours=1)) is None


def test_reasignacion_cambia_al_responsable(sesion, base) -> None:
    unidad = alta_unidad(sesion, base, fecha_hora=D0)
    _asignacion(sesion, base, unidad, D1)
    transicionar(
        sesion,
        unidad,
        T.REASIGNACION,
        base.mkt,
        {"id_responsable": base.asesor2.id, "id_sucursal": unidad.id_sucursal},
        fecha_hora=D2,
    )
    primero = responsable_vigente(sesion, unidad.id, D1 + timedelta(hours=1))
    segundo = responsable_vigente(sesion, unidad.id, D2 + timedelta(hours=1))
    assert primero is not None and primero.identificador == base.asesor.id
    assert segundo is not None and segundo.identificador == base.asesor2.id


def test_liberacion_cierra_la_vigencia(sesion, base) -> None:
    unidad = alta_unidad(sesion, base, fecha_hora=D0)
    _asignacion(sesion, base, unidad, D1)
    transicionar(sesion, unidad, T.LIBERACION, base.mkt, {}, fecha_hora=D2)
    assert responsable_vigente(sesion, unidad.id, D1 + timedelta(hours=1)) is not None
    assert responsable_vigente(sesion, unidad.id, D2 + timedelta(hours=1)) is None


def test_uso_comercial_manda_sobre_la_asignacion(sesion, base) -> None:
    unidad = alta_unidad(sesion, base, fecha_hora=D0)
    _asignacion(sesion, base, unidad, D1)
    salida = transicionar(sesion, unidad, T.SALIDA, base.mkt, {}, fecha_hora=D2)
    resp = responsable_vigente(sesion, unidad.id, D2 + timedelta(hours=1))
    assert resp is not None
    assert resp.tipo == "USUARIO"
    assert resp.identificador == base.mkt.id  # quien registro la salida, no el asesor asignado
    assert resp.evento_id == salida.id_evento


def test_bordes_exactos_salida_y_regreso(sesion, base) -> None:
    unidad = alta_unidad(sesion, base, fecha_hora=D0)
    _asignacion(sesion, base, unidad, D1)
    transicionar(sesion, unidad, T.SALIDA, base.mkt, {}, fecha_hora=D2)
    transicionar(sesion, unidad, T.REGRESO, base.mkt, {"km": 1100}, fecha_hora=D3)
    en_salida = responsable_vigente(sesion, unidad.id, D2)
    en_regreso = responsable_vigente(sesion, unidad.id, D3)
    despues = responsable_vigente(sesion, unidad.id, D3 + timedelta(seconds=1))
    assert en_salida is not None and en_salida.identificador == base.mkt.id
    assert en_regreso is not None and en_regreso.identificador == base.mkt.id
    assert despues is not None and despues.identificador == base.asesor.id  # vuelve a la asignacion


def test_uso_abierto_se_toma_hasta_el_momento_actual(sesion, base) -> None:
    unidad = alta_unidad(sesion, base, fecha_hora=D0)
    _asignacion(sesion, base, unidad, D1)
    transicionar(sesion, unidad, T.SALIDA, base.mkt, {}, fecha_hora=D2)
    resp = responsable_vigente(sesion, unidad.id, D2 + timedelta(days=2))
    assert resp is not None
    assert resp.identificador == base.mkt.id
    assert resp.hasta is None


def test_prestamo_devuelve_al_cliente_con_bordes(sesion, base) -> None:
    unidad = alta_unidad(sesion, base, fecha_hora=D0)
    transicionar(
        sesion,
        unidad,
        T.PRESTAMO,
        base.posventa,
        {"id_cliente": 77, "nombre_cliente": "Cliente Prueba"},
        fecha_hora=D1,
    )
    transicionar(sesion, unidad, T.DEVOLUCION, base.posventa, {"km": 1300}, fecha_hora=D2)
    en_entrega = responsable_vigente(sesion, unidad.id, D1)
    en_medio = responsable_vigente(sesion, unidad.id, D1 + timedelta(hours=6))
    en_devolucion = responsable_vigente(sesion, unidad.id, D2)
    despues = responsable_vigente(sesion, unidad.id, D2 + timedelta(hours=1))
    assert en_entrega is not None
    assert en_entrega.tipo == "CLIENTE"
    assert en_entrega.identificador == 77
    assert en_entrega.nombre == "Cliente Prueba"
    assert en_medio is not None and en_medio.tipo == "CLIENTE"
    assert en_devolucion is not None and en_devolucion.tipo == "CLIENTE"
    assert despues is None


def test_responsable_en_sin_instante_usa_el_momento_actual(sesion, base) -> None:
    unidad = alta_unidad(sesion, base, fecha_hora=D0)
    _asignacion(sesion, base, unidad, D1)
    resp = service.responsable_en(sesion, unidad.id, None)
    assert resp is not None
    assert resp.identificador == base.asesor.id
