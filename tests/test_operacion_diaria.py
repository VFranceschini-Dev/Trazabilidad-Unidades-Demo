"""Aceptacion de HU-04, HU-05 y HU-06 contra la API, un criterio por prueba o mas."""

from __future__ import annotations

import itertools
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select

from app.identidad.models import Rol, Usuario
from app.tablas_generales.models import Alerta, Cliente
from app.unidades.models import UnidadDemo

CLAVE = "Demo-Pruebas-2026!"
_contador = itertools.count(1)
CONTROL_OK = {
    "service_al_dia": True,
    "documentacion_y_seguro": True,
    "sin_danos_visibles": True,
    "accesorios_completos": True,
}


def _cabeceras(client: Any, sesion: Any, hash_pruebas: str, rol: Rol, sucursal: str = "SC01") -> tuple[dict[str, str], Usuario]:
    n = next(_contador)
    usuario = Usuario(
        legajo=f"4{n:04d}", correo=f"operacion{n}@pruebas.local", nombre=f"Operacion {n}",
        rol=rol, id_sucursal=sucursal, hash_clave=hash_pruebas,
    )
    sesion.add(usuario)
    sesion.commit()
    r = client.post("/api/v1/auth/ingresar", json={"correo": usuario.correo, "clave": CLAVE})
    return {"Authorization": f"Bearer {r.json()['token']}"}, usuario


def _alta(client: Any, cab: dict[str, str], circuito: str, **extra: Any) -> dict[str, Any]:
    n = next(_contador)
    r = client.post(
        "/api/v1/unidades",
        json={
            "vin": f"1FTFW1E80PFO{n:05d}", "patente": f"OP{n:04d}X", "modelo": "Ranger", "version": "XLS",
            "circuito": circuito, "id_sucursal": "SC01", "km_inicial": 1000, **extra,
        },
        headers=cab,
    )
    assert r.status_code == 201, r.text
    return r.json()["unidad"]


@pytest.fixture()
def comercial(client, sesion, hash_pruebas, base) -> dict[str, Any]:
    """Unidad ASIGNADA a un asesor, con las cabeceras de ambos roles."""
    cab_mkt, _ = _cabeceras(client, sesion, hash_pruebas, Rol.RESP_MKT_VENTAS)
    cab, asesor = _cabeceras(client, sesion, hash_pruebas, Rol.ASESOR)
    unidad = _alta(client, cab_mkt, "COMERCIAL")
    r = client.post(
        f"/api/v1/unidades/{unidad['id']}/asignaciones",
        json={"id_responsable": asesor.id, "id_sucursal": "SC01"},
        headers=cab_mkt,
    )
    assert r.status_code == 200, r.text
    return {"cab": cab, "cab_mkt": cab_mkt, "asesor": asesor, "unidad": unidad}


@pytest.fixture()
def posventa(client, sesion, hash_pruebas, base) -> dict[str, Any]:
    cab, usuario = _cabeceras(client, sesion, hash_pruebas, Rol.RESP_POSVENTA)
    return {"cab": cab, "usuario": usuario, "unidad": _alta(client, cab, "POSVENTA", km_proximo_service=10000)}


def _salida(client: Any, c: dict[str, Any], **extra: Any) -> Any:
    cuerpo = {"id_unidad": c["unidad"]["id"], "tipo_uso": "GIRA", "km_salida": 1000, **extra}
    return client.post("/api/v1/usos/salida", json=cuerpo, headers=c["cab"])


def _ficha(client: Any, c: dict[str, Any]) -> dict[str, Any]:
    return client.get(f"/api/v1/unidades/{c['unidad']['id']}", headers=c["cab"]).json()


def _entrega(client: Any, p: dict[str, Any], **extra: Any) -> Any:
    cuerpo = {
        "id_unidad": p["unidad"]["id"],
        "nro_orden_reparacion": "OR 55184",
        "cliente_documento": f"20{next(_contador):09d}",
        "cliente_nombre": "Cliente Prueba",
        "fecha_devolucion_prevista": (date.today() + timedelta(days=3)).isoformat(),
        "km_entrega": 1000,
        "combustible_entrega": 6,
        "control_previo": CONTROL_OK,
        **extra,
    }
    return client.post("/api/v1/prestamos", json=cuerpo, headers=p["cab"])


def _devolucion(client: Any, p: dict[str, Any], id_prestamo: int, **extra: Any) -> Any:
    cuerpo = {"km_devolucion": 1100, "combustible_devolucion": 5, "estado_devolucion": "Sin novedades", **extra}
    return client.post(f"/api/v1/prestamos/{id_prestamo}/devolucion", json=cuerpo, headers=p["cab"])


# --- HU-04 -------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", ["GIRA", "GUARDIA", "EVENTO"])
def test_hu04_1_salida_pasa_a_en_uso(client, comercial, tipo) -> None:
    r = _salida(client, comercial, tipo_uso=tipo, km_salida=1200)
    assert r.status_code == 201, r.text
    assert r.json()["id_cliente"] is None
    ficha = _ficha(client, comercial)
    assert ficha["unidad"]["estado_actual"] == "EN_USO"
    assert ficha["unidad"]["km_actual"] == 1200
    assert ficha["responsable_actual"]["identificador"] == comercial["asesor"].id


@pytest.mark.parametrize(
    "faltante", [{}, {"cliente_nombre": "Ana"}, {"cliente_telefono": "362-4"}, {"cliente_nombre": " ", "cliente_telefono": " "}]
)
def test_hu04_2_test_drive_exige_datos_del_prospecto(client, comercial, faltante) -> None:
    r = _salida(client, comercial, tipo_uso="TEST_DRIVE", **faltante)
    assert r.status_code == 422
    assert r.json()["codigo"] == "DATOS_PROSPECTO"
    assert _ficha(client, comercial)["unidad"]["estado_actual"] == "ASIGNADA"


def test_hu04_2_test_drive_registra_al_prospecto_sin_documento(client, comercial, fabrica_sesion) -> None:
    r = _salida(client, comercial, tipo_uso="TEST_DRIVE", cliente_nombre="Ana Prospecto", cliente_telefono="362-4000000")
    assert r.status_code == 201, r.text
    with fabrica_sesion() as ses:
        cliente = ses.get(Cliente, r.json()["id_cliente"])
    assert (cliente.nombre, cliente.contacto, cliente.documento) == ("Ana Prospecto", "362-4000000", None)


def test_hu04_3_rechaza_regreso_con_km_menor(client, comercial) -> None:
    uso = _salida(client, comercial, km_salida=1200).json()
    r = client.post(f"/api/v1/usos/{uso['id_uso']}/regreso", json={"km_regreso": 1199}, headers=comercial["cab"])
    assert r.status_code == 409
    assert _ficha(client, comercial)["unidad"]["estado_actual"] == "EN_USO"


def test_hu04_4_regreso_vuelve_a_asignada_y_actualiza_km(client, comercial) -> None:
    uso = _salida(client, comercial).json()
    r = client.post(f"/api/v1/usos/{uso['id_uso']}/regreso", json={"km_regreso": 1500}, headers=comercial["cab"])
    assert r.status_code == 200, r.text
    assert r.json()["fecha_hora_regreso"] is not None
    unidad = _ficha(client, comercial)["unidad"]
    assert (unidad["estado_actual"], unidad["km_actual"]) == ("ASIGNADA", 1500)
    # Un uso cerrado no admite un segundo regreso
    r = client.post(f"/api/v1/usos/{uso['id_uso']}/regreso", json={"km_regreso": 1600}, headers=comercial["cab"])
    assert (r.status_code, r.json()["codigo"]) == (409, "USO_CERRADO")


def test_salida_solo_del_asesor_asignado(client, sesion, hash_pruebas, comercial) -> None:
    otro, _ = _cabeceras(client, sesion, hash_pruebas, Rol.ASESOR)
    r = _salida(client, {**comercial, "cab": otro})
    assert r.status_code == 409
    assert "no está asignada" in r.json()["mensaje"]


def test_salida_rechaza_km_menor_al_actual(client, comercial) -> None:
    assert _salida(client, comercial, km_salida=999).status_code == 409


def test_regreso_solo_de_quien_retiro(client, sesion, hash_pruebas, comercial) -> None:
    uso = _salida(client, comercial).json()
    otro, _ = _cabeceras(client, sesion, hash_pruebas, Rol.ASESOR)
    r = client.post(f"/api/v1/usos/{uso['id_uso']}/regreso", json={"km_regreso": 1500}, headers=otro)
    assert r.status_code == 409


def test_uso_inexistente(client, comercial) -> None:
    r = client.post("/api/v1/usos/999999/regreso", json={"km_regreso": 1}, headers=comercial["cab"])
    assert r.status_code == 404


def test_solo_el_asesor_registra_usos(client, comercial) -> None:
    r = _salida(client, {**comercial, "cab": comercial["cab_mkt"]})
    assert r.status_code == 403


def test_carga_diferida_en_salida(client, comercial) -> None:
    futura = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert _salida(client, comercial, fecha_hora=futura).json()["codigo"] == "FECHA_FUTURA"
    previa = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    assert _salida(client, comercial, fecha_hora=previa).json()["codigo"] == "FECHA_ANTERIOR_ULTIMO_EVENTO"
    hace_un_rato = datetime.now(timezone.utc).isoformat()
    assert _salida(client, comercial, fecha_hora=hace_un_rato).status_code == 201
    eventos = client.get(f"/api/v1/unidades/{comercial['unidad']['id']}/historial", headers=comercial["cab"]).json()["eventos"]
    assert (eventos[0]["tipo_evento"], eventos[0]["carga_diferida"]) == ("SALIDA", True)


def test_mis_unidades_muestra_la_salida_abierta(client, comercial) -> None:
    filas = client.get("/api/v1/usos/mis-unidades", headers=comercial["cab"]).json()
    assert [(f["unidad"]["id"], f["uso_abierto"]) for f in filas] == [(comercial["unidad"]["id"], None)]
    uso = _salida(client, comercial).json()
    filas = client.get("/api/v1/usos/mis-unidades", headers=comercial["cab"]).json()
    assert filas[0]["uso_abierto"]["id_uso"] == uso["id_uso"]


# --- HU-05 -------------------------------------------------------------------------


def test_hu05_1_y_3_entrega_pasa_a_en_prestamo_con_fechas(client, posventa) -> None:
    prevista = (date.today() + timedelta(days=5)).isoformat()
    r = _entrega(client, posventa, fecha_devolucion_prevista=prevista, km_entrega=1100)
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["fecha_hora_entrega"] is not None
    assert cuerpo["fecha_devolucion_prevista"] == prevista
    assert cuerpo["control_previo"] == CONTROL_OK
    ficha = _ficha(client, posventa)
    assert (ficha["unidad"]["estado_actual"], ficha["unidad"]["km_actual"]) == ("EN_PRESTAMO", 1100)
    assert ficha["responsable_actual"]["tipo"] == "CLIENTE"
    assert ficha["responsable_actual"]["nombre"] == "Cliente Prueba"


def test_hu05_2_service_vencido_bloquea_la_entrega(client, sesion, hash_pruebas, base) -> None:
    cab, _ = _cabeceras(client, sesion, hash_pruebas, Rol.RESP_POSVENTA)
    p = {"cab": cab, "unidad": _alta(client, cab, "POSVENTA", km_proximo_service=1000)}
    r = _entrega(client, p)
    assert r.status_code == 409
    assert "service vencido" in r.json()["mensaje"]
    assert _ficha(client, p)["unidad"]["estado_actual"] == "DISPONIBLE"


def test_hu05_2_vencido_segun_el_km_declarado_en_la_entrega(client, posventa) -> None:
    """Unidad a 1.000 km con service a 10.000: entregarla con 10.000 km tambien se bloquea."""
    r = _entrega(client, posventa, km_entrega=10000)
    assert r.status_code == 409
    assert "service vencido" in r.json()["mensaje"]


def test_hu05_4_item_sin_marcar_exige_observacion(client, posventa) -> None:
    control = {**CONTROL_OK, "accesorios_completos": False}
    r = _entrega(client, posventa, control_previo=control)
    assert (r.status_code, r.json()["codigo"]) == (422, "OBSERVACION_REQUERIDA")
    assert r.json()["detalle"]["sin_marcar"] == ["accesorios_completos"]
    r = _entrega(client, posventa, control_previo=control, observaciones="Falta la llave de rueda")
    assert r.status_code == 201, r.text
    assert r.json()["estado_entrega"] == "Falta la llave de rueda"


def test_control_previo_incompleto_se_rechaza(client, posventa) -> None:
    r = _entrega(client, posventa, control_previo={"service_al_dia": True})
    assert (r.status_code, r.json()["codigo"]) == (422, "CONTROL_INCOMPLETO")


def test_solo_circuito_posventa(client, sesion, hash_pruebas, comercial) -> None:
    cab_mkt = comercial["cab_mkt"]
    disponible = _alta(client, cab_mkt, "COMERCIAL")
    cab, _ = _cabeceras(client, sesion, hash_pruebas, Rol.RESP_POSVENTA)
    assert _entrega(client, {"cab": cab, "unidad": disponible}).status_code == 409


def test_cliente_existente_se_reutiliza_y_nuevo_exige_nombre(client, posventa, fabrica_sesion) -> None:
    r = _entrega(client, posventa, cliente_nombre=None)
    assert (r.status_code, r.json()["codigo"]) == (422, "CLIENTE_SIN_NOMBRE")
    documento = f"27{next(_contador):09d}"
    primero = _entrega(client, posventa, cliente_documento=documento).json()
    _devolucion(client, posventa, primero["id_prestamo"])
    segundo = _entrega(client, posventa, cliente_documento=documento, cliente_nombre=None, km_entrega=1100)
    assert segundo.status_code == 201, segundo.text
    assert segundo.json()["id_cliente"] == primero["id_cliente"]


def test_devolucion_prevista_no_anterior_a_la_entrega(client, posventa) -> None:
    ayer = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
    r = _entrega(client, posventa, fecha_devolucion_prevista=ayer)
    assert (r.status_code, r.json()["codigo"]) == (422, "DEVOLUCION_PREVISTA_INVALIDA")


def test_combustible_fuera_de_rango(client, posventa) -> None:
    assert _entrega(client, posventa, combustible_entrega=9).status_code == 422


def test_entrega_rechazada_no_deja_cliente_nuevo(client, posventa, fabrica_sesion) -> None:
    documento = f"23{next(_contador):09d}"
    assert _entrega(client, posventa, cliente_documento=documento, km_entrega=1).status_code == 409
    with fabrica_sesion() as ses:
        assert ses.scalar(select(Cliente).where(Cliente.documento == documento)) is None


def test_solo_posventa_presta(client, posventa, comercial) -> None:
    assert _entrega(client, {**posventa, "cab": comercial["cab_mkt"]}).status_code == 403
    assert client.get("/api/v1/prestamos", headers=comercial["cab"]).status_code == 403


# --- HU-06 -------------------------------------------------------------------------


def test_hu06_1_devolucion_cierra_y_vuelve_a_disponible(client, posventa) -> None:
    prestamo = _entrega(client, posventa).json()
    r = _devolucion(client, posventa, prestamo["id_prestamo"])
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["fecha_hora_devolucion"] is not None
    assert (cuerpo["km_devolucion"], cuerpo["combustible_devolucion"], cuerpo["estado_devolucion"]) == (1100, 5, "Sin novedades")
    ficha = _ficha(client, posventa)
    assert (ficha["unidad"]["estado_actual"], ficha["unidad"]["km_actual"]) == ("DISPONIBLE", 1100)
    r = _devolucion(client, posventa, prestamo["id_prestamo"])
    assert (r.status_code, r.json()["codigo"]) == (409, "PRESTAMO_CERRADO")


def test_devolucion_rechaza_km_menor(client, posventa) -> None:
    prestamo = _entrega(client, posventa).json()
    assert _devolucion(client, posventa, prestamo["id_prestamo"], km_devolucion=999).status_code == 409
    assert _ficha(client, posventa)["unidad"]["estado_actual"] == "EN_PRESTAMO"


def test_prestamo_inexistente(client, posventa) -> None:
    assert _devolucion(client, posventa, 999999).status_code == 404


def test_hu06_2_devolucion_con_danos_genera_alerta(client, posventa, fabrica_sesion) -> None:
    prestamo = _entrega(client, posventa).json()
    r = _devolucion(client, posventa, prestamo["id_prestamo"], con_danos=True, estado_devolucion="Rayón en paragolpes")
    assert r.status_code == 200, r.text
    with fabrica_sesion() as ses:
        alerta = ses.scalars(select(Alerta).where(Alerta.id_unidad == posventa["unidad"]["id"])).one()
    assert (alerta.tipo_alerta, alerta.estado) == ("DEVOLUCION_CON_DANOS", "ABIERTA")
    assert "Rayón en paragolpes" in alerta.mensaje


def test_devolucion_sin_danos_no_genera_alerta(client, posventa, fabrica_sesion) -> None:
    prestamo = _entrega(client, posventa).json()
    _devolucion(client, posventa, prestamo["id_prestamo"])
    with fabrica_sesion() as ses:
        assert ses.scalars(select(Alerta).where(Alerta.id_unidad == posventa["unidad"]["id"])).first() is None


def test_hu06_3_prestamo_vencido_aparece_demorado(client, posventa, fabrica_sesion) -> None:
    prestamo = _entrega(client, posventa).json()
    filas = {f["id_prestamo"]: f for f in client.get("/api/v1/prestamos", params={"activos": True}, headers=posventa["cab"]).json()}
    assert filas[prestamo["id_prestamo"]]["demorado"] is False

    from app.posventa.models import Prestamo

    with fabrica_sesion() as ses:
        ses.get(Prestamo, prestamo["id_prestamo"]).fecha_devolucion_prevista = date.today() - timedelta(days=2)
        ses.commit()
    filas = {f["id_prestamo"]: f for f in client.get("/api/v1/prestamos", headers=posventa["cab"]).json()}
    assert filas[prestamo["id_prestamo"]]["demorado"] is True
    assert filas[prestamo["id_prestamo"]]["unidad_patente"] == posventa["unidad"]["patente"]

    _devolucion(client, posventa, prestamo["id_prestamo"])
    activos = [f["id_prestamo"] for f in client.get("/api/v1/prestamos", headers=posventa["cab"]).json()]
    assert prestamo["id_prestamo"] not in activos
    todos = {f["id_prestamo"]: f for f in client.get("/api/v1/prestamos", params={"activos": False}, headers=posventa["cab"]).json()}
    assert todos[prestamo["id_prestamo"]]["demorado"] is False


def test_indices_unicos_impiden_dos_abiertos(sesion_dueno) -> None:
    from sqlalchemy import text

    indices = sesion_dueno.execute(
        text("SELECT indexname FROM pg_indexes WHERE indexname IN ('ux_uso_abierto_por_unidad', 'ux_prestamo_abierto_por_unidad')")
    ).scalars().all()
    assert len(indices) == 2


def test_dos_regresos_simultaneos_solo_uno_cierra(client, comercial, fabrica_sesion) -> None:
    """El segundo pedido leyo el uso abierto antes de que el primero lo cerrara."""
    from app.comercial import service
    from app.comercial.models import UsoComercial
    from app.core.excepciones import ErrorDominio

    uso = _salida(client, comercial).json()
    with fabrica_sesion() as ses:
        asesor = ses.get(Usuario, comercial["asesor"].id)
        leido = ses.get(UsoComercial, uso["id_uso"])
        assert leido.fecha_hora_regreso is None
        r = client.post(f"/api/v1/usos/{uso['id_uso']}/regreso", json={"km_regreso": 1500}, headers=comercial["cab"])
        assert r.status_code == 200, r.text
        with pytest.raises(ErrorDominio, match="ya tiene el regreso"):
            service.registrar_regreso(ses, uso["id_uso"], km_regreso=1600, usuario=asesor)
