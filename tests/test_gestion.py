"""Aceptacion de HU-11 a HU-14 y de la comparacion de posicion de HU-10.2."""

from __future__ import annotations

import itertools
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select

from app.core import alertas, control_alertas
from app.core.config import settings
from app.identidad.models import Rol, Usuario
from app.infracciones.models import Infraccion
from app.integraciones import traccar
from app.integraciones.traccar import ErrorTraccar, Posicion, TraccarPosiciones, describir_para_acta, localidad_cercana
from app.tablas_generales.models import Alerta
from app.unidades import ciclo
from app.unidades.models import PosicionCache, UnidadDemo

CLAVE = "Demo-Pruebas-2026!"
AR = ZoneInfo("America/Argentina/Buenos_Aires")
_contador = itertools.count(1)
CONTROL = dict.fromkeys(("service_al_dia", "documentacion_y_seguro", "sin_danos_visibles", "accesorios_completos"), True)
RESISTENCIA = (-27.45, -58.98)
FORMOSA = (-26.18, -58.18)


def _usuario(client: Any, sesion: Any, hash_pruebas: str, rol: Rol, sucursal: str = "SC01") -> tuple[dict[str, str], Usuario]:
    n = next(_contador)
    usuario = Usuario(
        legajo=f"2{n:04d}", correo=f"gestion{n}@pruebas.local", nombre=f"Gestion {n}", rol=rol, id_sucursal=sucursal, hash_clave=hash_pruebas,
    )
    sesion.add(usuario)
    sesion.commit()
    r = client.post("/api/v1/auth/ingresar", json={"correo": usuario.correo, "clave": CLAVE})
    return {"Authorization": f"Bearer {r.json()['token']}"}, usuario


def _alta(client: Any, cab: dict[str, str], circuito: str = "COMERCIAL", sucursal: str = "SC01", **extra: Any) -> dict[str, Any]:
    n = next(_contador)
    r = client.post(
        "/api/v1/unidades",
        json={
            "vin": f"1FTFW1E80PFG{n:05d}", "patente": f"GE{n:03d}ST", "modelo": "Ranger", "version": "XLS",
            "circuito": circuito, "id_sucursal": sucursal, "km_inicial": 1000, **extra,
        },
        headers=cab,
    )
    assert r.status_code == 201, r.text
    return r.json()["unidad"]


@pytest.fixture()
def mkt(client, sesion, hash_pruebas, base) -> dict[str, str]:
    return _usuario(client, sesion, hash_pruebas, Rol.RESP_MKT_VENTAS)[0]


@pytest.fixture()
def posventa(client, sesion, hash_pruebas, base) -> dict[str, str]:
    return _usuario(client, sesion, hash_pruebas, Rol.RESP_POSVENTA)[0]


@pytest.fixture()
def adm(client, sesion, hash_pruebas, base) -> dict[str, str]:
    return _usuario(client, sesion, hash_pruebas, Rol.ADMINISTRACION)[0]


def _acta(sesion: Any, patente: str, estado: str = "PENDIENTE_VALIDACION", **extra: Any) -> Infraccion:
    n = next(_contador)
    acta = Infraccion(nro_acta=f"GE-{n}", patente_leida=patente, archivo_pdf=f"g{n}.pdf", estado=estado, **extra)
    sesion.add(acta)
    sesion.commit()
    return acta


def _alertas(fabrica_sesion: Any, **filtros: Any) -> list[Alerta]:
    with fabrica_sesion() as ses:
        return list(ses.scalars(select(Alerta).filter_by(estado="ABIERTA", **filtros)))


def _mover_campo(fabrica_sesion: Any, id_unidad: int, **campos: Any) -> None:
    with fabrica_sesion() as ses:
        unidad = ses.get(UnidadDemo, id_unidad)
        for k, v in campos.items():
            setattr(unidad, k, v)
        ses.commit()


# --- HU-11 --------------------------------------------------------------------------


class _Falso:
    def __init__(self, ultima=None, error=False):
        self._ultima, self._error = ultima, error

    def ultima(self, _):
        if self._error:
            raise ErrorTraccar("caido")
        return self._ultima


def test_hu11_2_sin_dispositivo_informa_aunque_haya_cache(client, mkt, fabrica_sesion) -> None:
    unidad = _alta(client, mkt)
    with fabrica_sesion() as ses:
        ses.add(PosicionCache(id_unidad=unidad["id"], latitud=1, longitud=2, fecha_hora=datetime.now(timezone.utc)))
        ses.commit()
    r = client.get(f"/api/v1/unidades/{unidad['id']}/ubicacion", headers=mkt)
    assert r.status_code == 200, r.text
    assert (r.json()["estado"], r.json()["latitud"]) == ("SIN_DISPOSITIVO", None)


def test_hu11_1_ultima_posicion_y_guarda_cache(client, mkt, monkeypatch, fabrica_sesion) -> None:
    unidad = _alta(client, mkt)
    _mover_campo(fabrica_sesion, unidad["id"], id_dispositivo_traccar=7)
    momento = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)

    def falso_get(url, params, auth, timeout):
        fila = {"fixTime": "2026-10-01T12:00:00.000+00:00", "latitude": RESISTENCIA[0], "longitude": RESISTENCIA[1]}
        return httpx.Response(200, json=[fila], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", falso_get)
    r = client.get(f"/api/v1/unidades/{unidad['id']}/ubicacion", headers=mkt).json()
    assert (r["estado"], r["localidad"]) == ("VIGENTE", "Resistencia")
    with fabrica_sesion() as ses:
        assert ses.get(PosicionCache, unidad["id"]).fecha_hora == momento


def test_hu11_3_traccar_caido_usa_la_guardada_con_aviso(client, mkt, monkeypatch, fabrica_sesion) -> None:
    unidad = _alta(client, mkt)
    _mover_campo(fabrica_sesion, unidad["id"], id_dispositivo_traccar=8)

    def caido(*a, **k):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(httpx, "get", caido)
    r = client.get(f"/api/v1/unidades/{unidad['id']}/ubicacion", headers=mkt).json()
    assert r["estado"] == "SIN_DATOS"
    momento = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    with fabrica_sesion() as ses:
        ses.add(PosicionCache(id_unidad=unidad["id"], latitud=FORMOSA[0], longitud=FORMOSA[1], fecha_hora=momento))
        ses.commit()
    r = client.get(f"/api/v1/unidades/{unidad['id']}/ubicacion", headers=mkt).json()
    assert (r["estado"], r["localidad"]) == ("CACHE", "Formosa")


def test_posicion_atrasada_no_pisa_la_cache(sesion, base, client, mkt) -> None:
    unidad_api = _alta(client, mkt)
    unidad = sesion.get(UnidadDemo, unidad_api["id"])
    unidad.id_dispositivo_traccar = 9
    sesion.commit()
    reciente = datetime(2026, 10, 2, tzinfo=timezone.utc)
    ciclo.ubicacion(sesion, unidad, _Falso(Posicion(*RESISTENCIA, reciente)))
    ciclo.ubicacion(sesion, unidad, _Falso(Posicion(*FORMOSA, reciente - timedelta(days=1))))
    assert sesion.get(PosicionCache, unidad.id).latitud == RESISTENCIA[0]


def test_dispositivo_sin_posiciones(sesion, client, mkt) -> None:
    unidad_api = _alta(client, mkt)
    unidad = sesion.get(UnidadDemo, unidad_api["id"])
    unidad.id_dispositivo_traccar = 10
    assert ciclo.ubicacion(sesion, unidad, _Falso(None)).estado == "SIN_DATOS"


def test_asesor_no_consulta_ubicacion_ajena(client, sesion, hash_pruebas, mkt) -> None:
    unidad = _alta(client, mkt)
    cab, _ = _usuario(client, sesion, hash_pruebas, Rol.ASESOR)
    assert client.get(f"/api/v1/unidades/{unidad['id']}/ubicacion", headers=cab).status_code == 403


# --- HU-10.2 ------------------------------------------------------------------------


def _fila(momento: datetime, lat_lon: tuple[float, float]) -> dict[str, object]:
    return {"fixTime": momento.isoformat(), "latitude": lat_lon[0], "longitude": lat_lon[1]}


def test_cercana_incluye_el_borde_de_15_minutos_y_no_mas(monkeypatch) -> None:
    instante = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    borde = _fila(instante + timedelta(minutes=15), RESISTENCIA)
    afuera = _fila(instante + timedelta(minutes=15, seconds=1), FORMOSA)

    def falso_get(url, params, auth, timeout):
        return httpx.Response(200, json=[afuera, borde], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", falso_get)
    posicion = TraccarPosiciones("http://t").cercana(1, instante)
    assert posicion.latitud == RESISTENCIA[0]


def test_cercana_sin_nada_dentro_del_margen(monkeypatch) -> None:
    instante = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    afuera = _fila(instante - timedelta(minutes=15, seconds=1), FORMOSA)

    def falso_get(url, params, auth, timeout):
        return httpx.Response(200, json=[afuera], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", falso_get)
    assert TraccarPosiciones("http://t").cercana(1, instante) is None


@pytest.mark.parametrize(
    "lugar,esperado",
    [
        ("Municipalidad de Resistencia", "coincide"),
        ("MUNICIPALIDAD DE RESISTENCIA", "coincide"),
        ("Municipalidad de Formosa", "no coincide"),
        ("Vialidad Nacional", "no indica"),
    ],
)
def test_describir_compara_la_localidad(lugar, esperado) -> None:
    posicion = Posicion(*RESISTENCIA, datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    assert esperado in describir_para_acta(posicion, lugar)


def test_describir_ignora_acentos() -> None:
    posicion = Posicion(-26.78, -60.44, datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    assert localidad_cercana(posicion.latitud, posicion.longitud) == "Sáenz Peña"
    assert "(coincide)" in describir_para_acta(posicion, "Municipalidad de Saenz Pena")


def test_describir_sin_posicion() -> None:
    assert describir_para_acta(None, "Resistencia") == "sin posición"


def test_posicion_cercana_tolera_sin_dispositivo_y_traccar_caido(monkeypatch) -> None:
    instante = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    assert traccar.posicion_cercana(None, instante) is None

    def caido(*a, **k):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(httpx, "get", caido)
    assert traccar.posicion_cercana(1, instante) is None


# --- HU-12 --------------------------------------------------------------------------


def test_hu12_indicadores_filtros_y_responsable(client, sesion, hash_pruebas, mkt, base) -> None:
    gerencia, _ = _usuario(client, sesion, hash_pruebas, Rol.GERENCIA)
    unidad = _alta(client, mkt, sucursal="SC03")
    client.post(f"/api/v1/unidades/{unidad['id']}/service/ingreso", json={}, headers=mkt)
    _acta(sesion, unidad["patente"])
    _acta(sesion, unidad["patente"], estado="IMPUTADA", id_unidad=unidad["id"])
    _acta(sesion, unidad["patente"], estado="PAGADA", id_unidad=unidad["id"])
    _acta(sesion, unidad["patente"], estado="RECHAZADA")

    filtrado = client.get("/api/v1/tablero/indicadores", params={"id_sucursal": "SC03", "circuito": "COMERCIAL"}, headers=gerencia).json()
    fila = next(f for f in filtrado["filas"] if f["id"] == unidad["id"])
    assert (fila["sucursal"], fila["estado"]) == ("Sáenz Peña", "EN_SERVICE")
    assert filtrado["en_service"] >= 1
    assert filtrado["multas_pendientes"] >= 2
    otra = client.get("/api/v1/tablero/indicadores", params={"id_sucursal": "SC02"}, headers=gerencia).json()
    assert unidad["id"] not in [f["id"] for f in otra["filas"]]
    todo = client.get("/api/v1/tablero/indicadores", headers=gerencia).json()
    assert todo["activas"] == len([f for f in todo["filas"] if f["estado"] != "BAJA"])


def test_tablero_cuenta_la_multa_una_sola_vez(client, sesion, hash_pruebas, mkt) -> None:
    gerencia, _ = _usuario(client, sesion, hash_pruebas, Rol.GERENCIA)
    unidad = _alta(client, mkt, sucursal="SC04")
    ver = lambda: client.get("/api/v1/tablero/indicadores", params={"id_sucursal": "SC04"}, headers=gerencia).json()["multas_pendientes"]  # noqa: E731
    antes = ver()
    _acta(sesion, unidad["patente"], estado="VALIDADA", id_unidad=unidad["id"])
    assert ver() == antes + 1


def test_tablero_excluye_al_asesor_y_recorta_a_posventa(client, sesion, hash_pruebas, mkt, posventa) -> None:
    asesor, _ = _usuario(client, sesion, hash_pruebas, Rol.ASESOR)
    assert client.get("/api/v1/tablero/indicadores", headers=asesor).status_code == 403
    comercial = _alta(client, mkt)
    filas = client.get("/api/v1/tablero/indicadores", headers=posventa).json()["filas"]
    assert comercial["id"] not in [f["id"] for f in filas]


# --- HU-13 --------------------------------------------------------------------------


def test_hu13_1_rotacion_vencida(sesion, client, mkt, fabrica_sesion) -> None:
    unidad = _alta(client, mkt)
    _mover_campo(fabrica_sesion, unidad["id"], fecha_limite_rotacion=datetime.now(timezone.utc) - timedelta(days=1))
    control_alertas.ejecutar_control(sesion)
    control_alertas.ejecutar_control(sesion)
    sesion.commit()
    assert len(_alertas(fabrica_sesion, tipo_alerta="ROTACION_VENCIDA", id_unidad=unidad["id"])) == 1


def test_unidad_en_venta_no_genera_rotacion(sesion, client, mkt, fabrica_sesion) -> None:
    unidad = _alta(client, mkt)
    _mover_campo(fabrica_sesion, unidad["id"], fecha_limite_rotacion=datetime.now(timezone.utc) - timedelta(days=1), estado_actual="EN_VENTA")
    control_alertas.ejecutar_control(sesion)
    sesion.commit()
    assert _alertas(fabrica_sesion, tipo_alerta="ROTACION_VENCIDA", id_unidad=unidad["id"]) == []


def test_hu13_2_prestamo_demorado(sesion, client, posventa, fabrica_sesion) -> None:
    from app.posventa.models import Prestamo

    unidad = _alta(client, posventa, "POSVENTA")
    r = client.post(
        "/api/v1/prestamos",
        json={
            "id_unidad": unidad["id"], "nro_orden_reparacion": "OR 9", "cliente_documento": f"20{next(_contador):09d}",
            "cliente_nombre": "Demorado", "fecha_devolucion_prevista": (datetime.now(AR) + timedelta(days=1)).date().isoformat(),
            "km_entrega": 1000, "combustible_entrega": 6, "control_previo": CONTROL,
        },
        headers=posventa,
    )
    with fabrica_sesion() as ses:
        ses.get(Prestamo, r.json()["id_prestamo"]).fecha_devolucion_prevista = datetime.now(AR).date() - timedelta(days=1)
        ses.commit()
    control_alertas.ejecutar_control(sesion)
    sesion.commit()
    assert len(_alertas(fabrica_sesion, tipo_alerta="PRESTAMO_DEMORADO", id_unidad=unidad["id"])) == 1


@pytest.mark.parametrize("km,genera", [(9500, False), (9501, True)])
def test_hu13_3_service_a_menos_de_500_km_al_actualizar(client, sesion, hash_pruebas, mkt, fabrica_sesion, km, genera) -> None:
    unidad = _alta(client, mkt, km_proximo_service=10000)
    cab, asesor = _usuario(client, sesion, hash_pruebas, Rol.ASESOR)
    client.post(f"/api/v1/unidades/{unidad['id']}/asignaciones", json={"id_responsable": asesor.id, "id_sucursal": "SC01"}, headers=mkt)
    uso = client.post("/api/v1/usos/salida", json={"id_unidad": unidad["id"], "tipo_uso": "GIRA", "km_salida": 1000}, headers=cab).json()
    assert client.post(f"/api/v1/usos/{uso['id_uso']}/regreso", json={"km_regreso": km}, headers=cab).status_code == 200
    assert bool(_alertas(fabrica_sesion, tipo_alerta="SERVICE_PROXIMO", id_unidad=unidad["id"])) is genera


def test_service_vencido_lo_informa(sesion, client, mkt, fabrica_sesion) -> None:
    unidad_api = _alta(client, mkt, km_proximo_service=900)
    alertas.verificar_service_proximo(sesion, sesion.get(UnidadDemo, unidad_api["id"]))
    sesion.commit()
    assert "vencido hace 100 km" in _alertas(fabrica_sesion, id_unidad=unidad_api["id"])[0].mensaje


@pytest.mark.parametrize("dias,genera", [(5, True), (6, False)])
def test_hu13_4_multa_imputada_en_el_borde_de_5_dias(sesion, client, mkt, fabrica_sesion, dias, genera) -> None:
    unidad = _alta(client, mkt)
    vence = datetime.now(AR).date() + timedelta(days=dias)
    acta = _acta(sesion, unidad["patente"], estado="IMPUTADA", id_unidad=unidad["id"], fecha_vencimiento=vence)
    control_alertas.ejecutar_control(sesion)
    sesion.commit()
    assert bool(_alertas(fabrica_sesion, tipo_alerta="MULTA_POR_VENCER", id_infraccion=acta.id_infraccion)) is genera


def test_multa_pagada_no_genera_alerta(sesion, client, mkt, fabrica_sesion) -> None:
    unidad = _alta(client, mkt)
    acta = _acta(sesion, unidad["patente"], estado="PAGADA", id_unidad=unidad["id"], fecha_vencimiento=date.today())
    control_alertas.ejecutar_control(sesion)
    sesion.commit()
    assert _alertas(fabrica_sesion, id_infraccion=acta.id_infraccion) == []


def test_hu13_5_cierre_registra_quien_y_vuelve_si_sigue_el_problema(client, sesion, hash_pruebas, fabrica_sesion) -> None:
    cab, usuario = _usuario(client, sesion, hash_pruebas, Rol.RESP_MKT_VENTAS)
    unidad = _alta(client, cab)
    _mover_campo(fabrica_sesion, unidad["id"], fecha_limite_rotacion=datetime.now(timezone.utc) - timedelta(days=1))
    control_alertas.ejecutar_control(sesion)
    sesion.commit()
    alerta = next(a for a in client.get("/api/v1/alertas", headers=cab).json()["alertas"] if a["id_unidad"] == unidad["id"])
    assert alerta["puede_cerrar"] is True
    ruta = f"/api/v1/alertas/{alerta['id_alerta']}/cerrar"
    assert client.post(ruta, json={"accion": ""}, headers=cab).status_code == 422
    assert client.post(ruta, json={"accion": "Se rotó la unidad"}, headers=cab).status_code == 200
    assert client.post(ruta, json={"accion": "otra"}, headers=cab).status_code == 409
    cerrada = next(a for a in client.get("/api/v1/alertas", headers=cab).json()["alertas"] if a["id_alerta"] == alerta["id_alerta"])
    assert (cerrada["cerrada_por"], cerrada["accion_realizada"], cerrada["puede_cerrar"]) == (usuario.nombre, "Se rotó la unidad", False)
    assert cerrada["fecha_cierre"] is not None
    control_alertas.ejecutar_control(sesion)
    sesion.commit()
    assert len(_alertas(fabrica_sesion, tipo_alerta="ROTACION_VENCIDA", id_unidad=unidad["id"])) == 1


def test_alertas_por_area(client, sesion, hash_pruebas, mkt, posventa, adm, fabrica_sesion) -> None:
    gerencia, _ = _usuario(client, sesion, hash_pruebas, Rol.GERENCIA)
    comercial, propia_posventa = _alta(client, mkt), _alta(client, posventa, "POSVENTA")
    with fabrica_sesion() as ses:
        for u in (comercial, propia_posventa):
            alertas.generar(ses, "SERVICE_PROXIMO", "x", id_unidad=u["id"])
        alertas.generar(ses, "DEVOLUCION_CON_DANOS", "x", id_unidad=propia_posventa["id"])
        ses.commit()

    def ids(cab: dict[str, str]) -> dict[tuple[str, Any], bool]:
        return {(a["tipo_alerta"], a["id_unidad"]): a["puede_cerrar"] for a in client.get("/api/v1/alertas", headers=cab).json()["alertas"]}

    assert ("SERVICE_PROXIMO", comercial["id"]) in ids(mkt)
    assert ("SERVICE_PROXIMO", propia_posventa["id"]) not in ids(mkt)
    assert ("DEVOLUCION_CON_DANOS", propia_posventa["id"]) not in ids(mkt)
    assert ids(posventa)[("DEVOLUCION_CON_DANOS", propia_posventa["id"])] is True
    assert ("SERVICE_PROXIMO", comercial["id"]) not in ids(adm)
    assert ids(gerencia)[("SERVICE_PROXIMO", comercial["id"])] is False
    ajena = next(a for a in client.get("/api/v1/alertas", headers=gerencia).json()["alertas"] if a["id_unidad"] == comercial["id"])
    assert client.post(f"/api/v1/alertas/{ajena['id_alerta']}/cerrar", json={"accion": "x"}, headers=gerencia).status_code == 403


def test_asesor_sin_alertas_y_control_solo_admin(client, sesion, hash_pruebas, mkt) -> None:
    asesor, _ = _usuario(client, sesion, hash_pruebas, Rol.ASESOR)
    assert client.get("/api/v1/alertas", headers=asesor).status_code == 403
    assert client.post("/api/v1/alertas/ejecutar-control", headers=mkt).status_code == 403
    admin, _ = _usuario(client, sesion, hash_pruebas, Rol.ADMIN)
    assert client.post("/api/v1/alertas/ejecutar-control", headers=admin).status_code == 200
    assert client.get("/api/v1/alertas", headers=admin).json()["ultimo_control"] is not None


def test_alerta_inexistente(client, mkt) -> None:
    assert client.post("/api/v1/alertas/999999/cerrar", json={"accion": "x"}, headers=mkt).status_code == 404


# --- HU-14 --------------------------------------------------------------------------


def test_hu14_1_y_3_pase_y_baja_conservan_historial(client, sesion, hash_pruebas, mkt) -> None:
    unidad = _alta(client, mkt)
    ruta = f"/api/v1/unidades/{unidad['id']}"
    r = client.post(f"{ruta}/pase-venta", json={"motivo": "Cumplió el plazo", "id_sucursal": "SC04"}, headers=mkt)
    assert r.status_code == 200, r.text
    assert (r.json()["estado_actual"], r.json()["id_sucursal"]) == ("EN_VENTA", "SC04")
    assert client.post(f"{ruta}/baja", json={"motivo": "OTRO"}, headers=mkt).status_code == 422
    r = client.post(f"{ruta}/baja", json={"motivo": "VENTA_USADO"}, headers=mkt)
    assert r.json()["estado_actual"] == "BAJA"
    tipos = [e["tipo_evento"] for e in client.get(f"{ruta}/historial", headers=mkt).json()["eventos"]]
    assert tipos == ["BAJA", "PASE_VENTA", "ALTA"]


def test_pase_desde_asignada_cierra_la_asignacion(client, sesion, hash_pruebas, mkt) -> None:
    unidad = _alta(client, mkt)
    _, asesor = _usuario(client, sesion, hash_pruebas, Rol.ASESOR)
    client.post(f"/api/v1/unidades/{unidad['id']}/asignaciones", json={"id_responsable": asesor.id, "id_sucursal": "SC01"}, headers=mkt)
    assert client.post(f"/api/v1/unidades/{unidad['id']}/pase-venta", json={"motivo": "x"}, headers=mkt).status_code == 200
    filas = client.get(f"/api/v1/unidades/{unidad['id']}/asignaciones", headers=mkt).json()
    assert filas[0]["fecha_hasta"] is not None


@pytest.mark.parametrize("estado", ["PENDIENTE_VALIDACION", "VALIDADA"])
def test_hu14_2_actas_pendientes_bloquean_y_se_listan(client, sesion, mkt, estado) -> None:
    unidad = _alta(client, mkt)
    extra = {"id_unidad": unidad["id"]} if estado == "VALIDADA" else {}
    acta = _acta(sesion, unidad["patente"], estado=estado, **extra)
    r = client.post(f"/api/v1/unidades/{unidad['id']}/pase-venta", json={"motivo": "x"}, headers=mkt)
    assert (r.status_code, r.json()["codigo"]) == (409, "ACTAS_PENDIENTES")
    assert r.json()["detalle"]["actas"][0]["nro_acta"] == acta.nro_acta
    assert client.get(f"/api/v1/unidades/{unidad['id']}", headers=mkt).json()["unidad"]["estado_actual"] == "DISPONIBLE"
    listado = client.get(f"/api/v1/unidades/{unidad['id']}/actas-pendientes", headers=mkt).json()
    assert [a["nro_acta"] for a in listado] == [acta.nro_acta]


@pytest.mark.parametrize("estado", ["IMPUTADA", "PAGADA", "RECHAZADA"])
def test_actas_resueltas_no_bloquean(client, sesion, mkt, estado) -> None:
    unidad = _alta(client, mkt)
    _acta(sesion, unidad["patente"], estado=estado, id_unidad=unidad["id"])
    assert client.post(f"/api/v1/unidades/{unidad['id']}/pase-venta", json={"motivo": "x"}, headers=mkt).status_code == 200


def test_pase_en_service_y_roles(client, mkt, posventa) -> None:
    unidad = _alta(client, mkt)
    ruta = f"/api/v1/unidades/{unidad['id']}"
    assert client.post(f"{ruta}/pase-venta", json={"motivo": "x"}, headers=posventa).status_code == 403
    client.post(f"{ruta}/service/ingreso", json={}, headers=mkt)
    assert client.post(f"{ruta}/pase-venta", json={"motivo": "x"}, headers=mkt).status_code == 409
    assert client.post(f"{ruta}/baja", json={"motivo": "VENTA_USADO"}, headers=mkt).status_code == 409


def test_alerta_informa_sucursal_y_circuito(client, sesion, hash_pruebas, mkt, fabrica_sesion) -> None:
    gerencia, _ = _usuario(client, sesion, hash_pruebas, Rol.GERENCIA)
    unidad = _alta(client, mkt, sucursal="SC03")
    with fabrica_sesion() as ses:
        alertas.generar(ses, "SERVICE_PROXIMO", "x", id_unidad=unidad["id"])
        ses.commit()
    fila = next(a for a in client.get("/api/v1/alertas", headers=gerencia).json()["alertas"] if a["id_unidad"] == unidad["id"])
    assert (fila["id_sucursal"], fila["circuito"]) == ("SC03", "COMERCIAL")
