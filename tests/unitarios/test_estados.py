"""Pruebas del motor de estados: cada transicion valida e invalida de la tabla."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.estados import (
    TABLA_TRANSICIONES,
    EstadoUnidad,
    Origen,
    TipoEvento,
    acciones_permitidas_desde,
    buscar_regla,
    transicionar,
)
from app.core.excepciones import TransicionInvalida
from app.unidades.models import Circuito, UnidadDemo


def _unidad(sesion: Session, estado: EstadoUnidad | None, circuito=Circuito.COMERCIAL) -> UnidadDemo:
    u = UnidadDemo(
        vin="1FTRA1234567890AB" if estado is not None else "9BRZZZ00000000001",
        patente=f"AA{estado.value[:2] if estado else 'ZZ'}123" if estado else "PRA001",
        modelo="Ranger", version="XLS 2.3", circuito=circuito,
        estado_actual=(estado.value if estado else EstadoUnidad.DISPONIBLE.value),
        id_sucursal="CC", km_actual=1000,
    )
    sesion.add(u)
    sesion.commit()
    return u


class TestReglas:
    def test_tabla_completa_presente(self):
        eventos = {r.evento for r in TABLA_TRANSICIONES}
        assert eventos >= {
            TipoEvento.ALTA, TipoEvento.ASIGNACION, TipoEvento.REASIGNACION, TipoEvento.LIBERACION,
            TipoEvento.SALIDA, TipoEvento.REGRESO, TipoEvento.PRESTAMO, TipoEvento.DEVOLUCION,
            TipoEvento.INGRESO_SERVICE, TipoEvento.FIN_SERVICE, TipoEvento.PASE_VENTA,
            TipoEvento.BAJA, TipoEvento.POSICION, TipoEvento.INFRACCION,
        }

    @pytest.mark.parametrize("estado,evento,destino", [
        (None, TipoEvento.ALTA, EstadoUnidad.DISPONIBLE),
        (EstadoUnidad.DISPONIBLE, TipoEvento.ASIGNACION, EstadoUnidad.ASIGNADA),
        (EstadoUnidad.ASIGNADA, TipoEvento.REASIGNACION, EstadoUnidad.ASIGNADA),
        (EstadoUnidad.ASIGNADA, TipoEvento.LIBERACION, EstadoUnidad.DISPONIBLE),
        (EstadoUnidad.ASIGNADA, TipoEvento.SALIDA, EstadoUnidad.EN_USO),
        (EstadoUnidad.EN_USO, TipoEvento.REGRESO, EstadoUnidad.ASIGNADA),
        (EstadoUnidad.DISPONIBLE, TipoEvento.PRESTAMO, EstadoUnidad.EN_PRESTAMO),
        (EstadoUnidad.EN_PRESTAMO, TipoEvento.DEVOLUCION, EstadoUnidad.DISPONIBLE),
        (EstadoUnidad.DISPONIBLE, TipoEvento.INGRESO_SERVICE, EstadoUnidad.EN_SERVICE),
        (EstadoUnidad.EN_SERVICE, TipoEvento.FIN_SERVICE, EstadoUnidad.DISPONIBLE),
        (EstadoUnidad.DISPONIBLE, TipoEvento.PASE_VENTA, EstadoUnidad.EN_VENTA),
        (EstadoUnidad.ASIGNADA, TipoEvento.PASE_VENTA, EstadoUnidad.EN_VENTA),
        (EstadoUnidad.EN_VENTA, TipoEvento.BAJA, EstadoUnidad.BAJA),
    ])
    def test_transiciones_validas(self, sesion: Session, estado, evento, destino):
        u = _unidad(sesion, estado)
        origen = Origen.TRACCAR if evento is TipoEvento.POSICION else (Origen.N8N if evento is TipoEvento.INFRACCION else Origen.API)
        ev = transicionar(sesion, u, evento, None, origen)
        sesion.commit()
        if estado is None:
            assert u.estado_actual == EstadoUnidad.DISPONIBLE.value
        else:
            assert u.estado_actual == destino.value
        assert ev.tipo_evento == evento.value
        assert ev.estado_nuevo == destino.value

    @pytest.mark.parametrize("estado,evento", [
        (EstadoUnidad.DISPONIBLE, TipoEvento.SALIDA),
        (EstadoUnidad.DISPONIBLE, TipoEvento.REGRESO),
        (EstadoUnidad.EN_USO, TipoEvento.ASIGNACION),
        (EstadoUnidad.EN_PRESTAMO, TipoEvento.ASIGNACION),
        (EstadoUnidad.EN_SERVICE, TipoEvento.PRESTAMO),
        (EstadoUnidad.EN_VENTA, TipoEvento.ASIGNACION),
        (EstadoUnidad.BAJA, TipoEvento.ASIGNACION),
        (EstadoUnidad.BAJA, TipoEvento.PASE_VENTA),
        (EstadoUnidad.EN_USO, TipoEvento.INGRESO_SERVICE),
        (EstadoUnidad.EN_PRESTAMO, TipoEvento.LIBERACION),
    ])
    def test_transiciones_invalidas_409(self, sesion: Session, estado, evento):
        u = _unidad(sesion, estado)
        with pytest.raises(TransicionInvalida) as exc:
            transicionar(sesion, u, evento, None, Origen.API)
        assert exc.value.estado_http == 409
        assert exc.value.detalle["estado_actual"] == estado.value
        assert isinstance(exc.value.detalle["acciones_permitidas"], list)

    def test_informativos_sin_cambio_de_estado(self, sesion: Session):
        u = _unidad(sesion, EstadoUnidad.ASIGNADA)
        antes = u.estado_actual
        ev = transicionar(sesion, u, TipoEvento.POSICION, None, Origen.TRACCAR, datos={"lat": -26.18, "lon": -58.17})
        ev2 = transicionar(sesion, u, TipoEvento.INFRACCION, None, Origen.N8N, datos={"expediente": "E1"})
        sesion.commit()
        assert u.estado_actual == antes
        assert ev.estado_anterior == ev.estado_nuevo == antes
        assert ev2.estado_nuevo == antes

    def test_posicion_requiere_origen_traccar(self, sesion: Session):
        u = _unidad(sesion, EstadoUnidad.DISPONIBLE)
        with pytest.raises(TransicionInvalida):
            transicionar(sesion, u, TipoEvento.POSICION, None, Origen.API)

    def test_infraccion_requiere_origen_n8n(self, sesion: Session):
        u = _unidad(sesion, EstadoUnidad.DISPONIBLE)
        with pytest.raises(TransicionInvalida):
            transicionar(sesion, u, TipoEvento.INFRACCION, None, Origen.API)

    def test_precondicion_bloquea_y_no_cambia_estado(self, sesion: Session):
        u = _unidad(sesion, EstadoUnidad.DISPONIBLE)
        with pytest.raises(TransicionInvalida):
            transicionar(sesion, u, TipoEvento.ASIGNACION, None, Origen.API, precondiciones=("El responsable está inactivo.",))
        assert u.estado_actual == EstadoUnidad.DISPONIBLE.value

    def test_carga_diferida_marca_flag(self, sesion: Session):
        u = _unidad(sesion, EstadoUnidad.DISPONIBLE)
        pasada = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        ev = transicionar(sesion, u, TipoEvento.INGRESO_SERVICE, None, Origen.API, fecha_hora=pasada)
        sesion.commit()
        assert ev.carga_diferida is True
        assert ev.fecha_hora.astimezone(timezone.utc) == pasada

    def test_acciones_permitidas_desde_disponible(self):
        acc = acciones_permitidas_desde(EstadoUnidad.DISPONIBLE)
        assert {"ASIGNACION", "PRESTAMO", "INGRESO_SERVICE", "PASE_VENTA", "POSICION", "INFRACCION"} <= set(acc)

    def test_buscar_regla_alta(self):
        assert buscar_regla(TipoEvento.ALTA, None) is not None
