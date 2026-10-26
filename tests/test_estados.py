"""Motor de estados: todas las transiciones de la tabla, las invalidas y la carga diferida.

Cobertura del cierre de la etapa 1: cada transicion valida e invalida de la tabla del
prompt 2, con el detalle del 409 (estado actual y acciones permitidas), mas las reglas
de carga diferida (fecha futura y fecha anterior al ultimo evento).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import estados
from app.core.excepciones import ErrorDominio, TransicionInvalida
from app.unidades import service
from app.unidades.models import Asignacion, Circuito, UnidadDemo

from soporte import alta_unidad, llevar_a, transicionar, ultimo_evento

E = estados.EstadoUnidad
T = estados.TipoEvento


def _datos_para(evento: T, base) -> dict:
    if evento in (T.ASIGNACION, T.REASIGNACION):
        return {"id_responsable": base.asesor.id, "id_sucursal": "SC01"}
    if evento is T.PRESTAMO:
        return {"id_cliente": 1, "nombre_cliente": "Cliente Prueba"}
    if evento is T.BAJA:
        return {"motivo": "venta como usado"}
    return {}


TRANSICIONES_VALIDAS = [
    (E.DISPONIBLE, T.ASIGNACION, E.ASIGNADA),
    (E.ASIGNADA, T.REASIGNACION, E.ASIGNADA),
    (E.ASIGNADA, T.LIBERACION, E.DISPONIBLE),
    (E.ASIGNADA, T.SALIDA, E.EN_USO),
    (E.EN_USO, T.REGRESO, E.ASIGNADA),
    (E.DISPONIBLE, T.PRESTAMO, E.EN_PRESTAMO),
    (E.EN_PRESTAMO, T.DEVOLUCION, E.DISPONIBLE),
    (E.DISPONIBLE, T.INGRESO_SERVICE, E.EN_SERVICE),
    (E.EN_SERVICE, T.FIN_SERVICE, E.DISPONIBLE),
    (E.DISPONIBLE, T.PASE_VENTA, E.EN_VENTA),
    (E.ASIGNADA, T.PASE_VENTA, E.EN_VENTA),
    (E.EN_VENTA, T.BAJA, E.BAJA),
]


@pytest.mark.parametrize("origen,evento,destino", TRANSICIONES_VALIDAS)
def test_transicion_valida(sesion: Session, base, origen: E, evento: T, destino: E) -> None:
    unidad = llevar_a(sesion, base, alta_unidad(sesion, base), origen)
    transicionar(sesion, unidad, evento, base.mkt, _datos_para(evento, base))
    sesion.refresh(unidad)
    assert unidad.estado_actual == destino.value
    evento_fila = ultimo_evento(sesion, unidad)
    assert evento_fila.tipo_evento == evento.value
    assert evento_fila.estado_anterior == origen.value
    assert evento_fila.estado_nuevo == destino.value


TRANSICIONES_INFORMATIVAS = [
    (E.ASIGNADA, T.POSICION),
    (E.EN_USO, T.INFRACCION),
    (E.BAJA, T.POSICION),
]


@pytest.mark.parametrize("origen,evento", TRANSICIONES_INFORMATIVAS)
def test_evento_informativo_no_cambia_estado(sesion: Session, base, origen: E, evento: T) -> None:
    unidad = llevar_a(sesion, base, alta_unidad(sesion, base), origen)
    transicionar(sesion, unidad, evento, base.mkt, {"lat": -31.4, "lon": -64.2})
    sesion.refresh(unidad)
    assert unidad.estado_actual == origen.value
    evento_fila = ultimo_evento(sesion, unidad)
    assert evento_fila.estado_nuevo == origen.value
    assert evento_fila.estado_anterior == origen.value


TRANSICIONES_INVALIDAS = [
    (E.DISPONIBLE, T.SALIDA),
    (E.DISPONIBLE, T.REGRESO),
    (E.DISPONIBLE, T.DEVOLUCION),
    (E.DISPONIBLE, T.FIN_SERVICE),
    (E.DISPONIBLE, T.BAJA),
    (E.ASIGNADA, T.PRESTAMO),
    (E.ASIGNADA, T.INGRESO_SERVICE),
    (E.ASIGNADA, T.DEVOLUCION),
    (E.ASIGNADA, T.BAJA),
    (E.EN_USO, T.ASIGNACION),
    (E.EN_USO, T.PRESTAMO),
    (E.EN_USO, T.INGRESO_SERVICE),
    (E.EN_USO, T.LIBERACION),
    (E.EN_USO, T.PASE_VENTA),
    (E.EN_PRESTAMO, T.SALIDA),
    (E.EN_PRESTAMO, T.ASIGNACION),
    (E.EN_PRESTAMO, T.INGRESO_SERVICE),
    (E.EN_SERVICE, T.SALIDA),
    (E.EN_SERVICE, T.PRESTAMO),
    (E.EN_SERVICE, T.PASE_VENTA),
    (E.EN_SERVICE, T.LIBERACION),
    (E.EN_VENTA, T.ASIGNACION),
    (E.EN_VENTA, T.PRESTAMO),
    (E.EN_VENTA, T.INGRESO_SERVICE),
    (E.EN_VENTA, T.SALIDA),
    (E.BAJA, T.ASIGNACION),
    (E.BAJA, T.LIBERACION),
    (E.BAJA, T.PASE_VENTA),
    (E.BAJA, T.INGRESO_SERVICE),
]


@pytest.mark.parametrize("origen,evento", TRANSICIONES_INVALIDAS)
def test_transicion_invalida_devuelve_409_con_detalle(sesion: Session, base, origen: E, evento: T) -> None:
    unidad = llevar_a(sesion, base, alta_unidad(sesion, base), origen)
    sesion.commit()
    with pytest.raises(TransicionInvalida) as exc:
        transicionar(sesion, unidad, evento, base.mkt, _datos_para(evento, base))
    assert exc.value.estado_http == 409
    assert exc.value.codigo == "TRANSICION_INVALIDA"
    assert exc.value.detalle["estado_actual"] == origen.value
    assert evento.value not in exc.value.detalle["acciones_permitidas"]
    sesion.rollback()
    fresca = sesion.get(UnidadDemo, unidad.id)
    assert fresca.estado_actual == origen.value


def test_alta_registra_evento_y_queda_disponible(sesion: Session, base) -> None:
    unidad = alta_unidad(sesion, base)
    assert unidad.estado_actual == E.DISPONIBLE.value
    evento_fila = ultimo_evento(sesion, unidad)
    assert evento_fila.tipo_evento == T.ALTA.value
    assert evento_fila.estado_anterior is None
    assert evento_fila.carga_diferida is False


def test_alta_con_vin_corto(sesion: Session, base) -> None:
    with pytest.raises(ErrorDominio) as exc:
        service.alta_unidad(
            sesion, vin="1FTFW1E80PFA", patente="ZZ0001", modelo="Ranger", version="XLS",
            circuito=Circuito.COMERCIAL, id_sucursal="SC01", km_inicial=10, usuario=base.mkt,
        )
    assert exc.value.codigo == "VIN_INVALIDO"
    assert exc.value.estado_http == 422


def test_alta_con_vin_o_patente_duplicados(sesion: Session, base) -> None:
    unidad = alta_unidad(sesion, base)
    with pytest.raises(ErrorDominio) as exc:
        service.alta_unidad(
            sesion, vin=unidad.vin.strip(), patente="ZZ0002", modelo="Ranger", version="XLS",
            circuito=Circuito.COMERCIAL, id_sucursal="SC01", km_inicial=10, usuario=base.mkt,
        )
    assert exc.value.codigo == "VIN_EXISTENTE"
    assert exc.value.estado_http == 409
    assert exc.value.detalle["patente"] == unidad.patente
    with pytest.raises(ErrorDominio) as exc:
        service.alta_unidad(
            sesion, vin="1FTFW1E80PFZ99999", patente=unidad.patente, modelo="Ranger", version="XLS",
            circuito=Circuito.COMERCIAL, id_sucursal="SC01", km_inicial=10, usuario=base.mkt,
        )
    assert exc.value.codigo == "PATENTE_EXISTENTE"


@pytest.mark.parametrize("circuito,meses", [(Circuito.COMERCIAL, 6), (Circuito.POSVENTA, 12)])
def test_fecha_limite_rotacion_segun_circuito(sesion: Session, base, circuito: Circuito, meses: int) -> None:
    unidad = alta_unidad(sesion, base, circuito=circuito, usuario=base.mkt if circuito is Circuito.COMERCIAL else base.posventa)
    assert unidad.fecha_limite_rotacion == unidad.fecha_alta + timedelta(days=meses * 30)


def test_asignar_y_reasignar_cierra_y_abre_asignacion(sesion: Session, base) -> None:
    unidad = alta_unidad(sesion, base)
    service.asignar(sesion, unidad.id, id_responsable=base.asesor.id, id_sucursal="SC01", usuario=base.mkt)
    service.asignar(
        sesion, unidad.id, id_responsable=base.asesor.id, id_sucursal="SC01", usuario=base.mkt, reasignacion=True
    )
    filas = sesion.scalars(select(Asignacion).where(Asignacion.id_unidad == unidad.id).order_by(Asignacion.fecha_desde)).all()
    assert len(filas) == 2
    assert filas[0].fecha_hasta is not None
    assert filas[1].fecha_hasta is None
    sesion.refresh(unidad)
    assert unidad.estado_actual == E.ASIGNADA.value


def test_liberar_cierra_asignacion_y_vuelve_disponible(sesion: Session, base) -> None:
    unidad = alta_unidad(sesion, base)
    service.asignar(sesion, unidad.id, id_responsable=base.asesor.id, id_sucursal="SC01", usuario=base.mkt)
    service.liberar(sesion, unidad.id, usuario=base.mkt, motivo="rotacion")
    filas = sesion.scalars(select(Asignacion).where(Asignacion.id_unidad == unidad.id)).all()
    assert len(filas) == 1 and filas[0].fecha_hasta is not None
    sesion.refresh(unidad)
    assert unidad.estado_actual == E.DISPONIBLE.value


@pytest.mark.parametrize(
    "circuito,responsable,sucursal",
    [
        (Circuito.POSVENTA, "asesor", "SC01"),
        (Circuito.COMERCIAL, "inactivo", "SC01"),
        (Circuito.COMERCIAL, "asesor2", "SC01"),
    ],
)
def test_asignar_con_precondiciones_rechazadas(sesion: Session, base, circuito, responsable, sucursal) -> None:
    usuario_alta = base.mkt if circuito is Circuito.COMERCIAL else base.posventa
    unidad = alta_unidad(sesion, base, circuito=circuito, usuario=usuario_alta)
    sesion.commit()
    with pytest.raises(TransicionInvalida):
        service.asignar(
            sesion, unidad.id,
            id_responsable=getattr(base, responsable).id, id_sucursal=sucursal, usuario=base.mkt,
        )
    sesion.rollback()
    fresca = sesion.get(UnidadDemo, unidad.id)
    assert fresca.estado_actual == E.DISPONIBLE.value


def test_asignar_unidad_en_service_rechazado(sesion: Session, base) -> None:
    unidad = alta_unidad(sesion, base)
    service.service_ingreso(sesion, unidad.id, usuario=base.posventa)
    sesion.commit()
    with pytest.raises(TransicionInvalida) as exc:
        service.asignar(sesion, unidad.id, id_responsable=base.asesor.id, id_sucursal="SC01", usuario=base.mkt)
    assert exc.value.detalle["estado_actual"] == E.EN_SERVICE.value
    sesion.rollback()


def test_service_ingreso_y_fin_actualiza_km(sesion: Session, base) -> None:
    unidad = alta_unidad(sesion, base, km_inicial=1000)
    service.service_ingreso(sesion, unidad.id, usuario=base.posventa, observaciones="ruido de frenos")
    sesion.refresh(unidad)
    assert unidad.estado_actual == E.EN_SERVICE.value
    service.service_fin(sesion, unidad.id, km=1500, proximo_service_km=None, usuario=base.posventa)
    sesion.refresh(unidad)
    assert unidad.estado_actual == E.DISPONIBLE.value
    assert unidad.km_actual == 1500
    assert unidad.km_proximo_service == 11500  # km + intervalo configurado (10000)


def test_service_fin_con_km_menor_rechazado(sesion: Session, base) -> None:
    unidad = alta_unidad(sesion, base, km_inicial=1000)
    service.service_ingreso(sesion, unidad.id, usuario=base.posventa)
    with pytest.raises(TransicionInvalida):
        service.service_fin(sesion, unidad.id, km=900, proximo_service_km=None, usuario=base.posventa)
    sesion.rollback()


def test_carga_diferida_futura_rechazada(sesion: Session, base) -> None:
    with pytest.raises(ErrorDominio) as exc:
        alta_unidad(sesion, base, fecha_hora=datetime.now(timezone.utc) + timedelta(hours=1))
    assert exc.value.codigo == "FECHA_FUTURA"
    assert exc.value.estado_http == 422
    sesion.rollback()


def test_carga_diferida_anterior_al_ultimo_evento_rechazada(sesion: Session, base) -> None:
    pasada = datetime.now(timezone.utc) - timedelta(days=2)
    unidad = alta_unidad(sesion, base, fecha_hora=pasada)
    with pytest.raises(ErrorDominio) as exc:
        service.asignar(
            sesion, unidad.id, id_responsable=base.asesor.id, id_sucursal="SC01",
            usuario=base.mkt, fecha_hora=pasada - timedelta(days=1),
        )
    assert exc.value.codigo == "FECHA_ANTERIOR_ULTIMO_EVENTO"
    sesion.rollback()


def test_carga_diferida_valida_marca_el_evento(sesion: Session, base) -> None:
    pasada = datetime.now(timezone.utc) - timedelta(days=3)
    unidad = alta_unidad(sesion, base, fecha_hora=pasada)
    assert unidad.fecha_alta == pasada
    evento_fila = ultimo_evento(sesion, unidad)
    assert evento_fila.carga_diferida is True
    assert evento_fila.fecha_hora == pasada


def test_origen_solo_valores_del_tfg() -> None:
    """El diccionario de datos del TFG define exactamente WEB, N8N, TRACCAR y DMS."""
    assert {o.value for o in estados.Origen} == {"WEB", "N8N", "TRACCAR", "DMS"}
