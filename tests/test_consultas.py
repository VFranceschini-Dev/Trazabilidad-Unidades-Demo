"""API de consulta para las pantallas: listados, catalogos, altas recientes y motivo."""

from __future__ import annotations

import itertools
from typing import Any

from sqlalchemy.orm import Session

from app.identidad.models import Rol, Usuario

CLAVE = "Demo-Pruebas-2026!"
_contador = itertools.count(1)


def _cabeceras(client: Any, sesion: Session, hash_pruebas: str, rol: Rol, sucursal: str = "SC01") -> dict[str, str]:
    n = next(_contador)
    usuario = Usuario(
        legajo=f"6{n:04d}",
        correo=f"consulta{n}@pruebas.local",
        nombre=f"Consulta {n}",
        rol=rol,
        id_sucursal=sucursal,
        hash_clave=hash_pruebas,
    )
    sesion.add(usuario)
    sesion.commit()
    r = client.post("/api/v1/auth/ingresar", json={"correo": usuario.correo, "clave": CLAVE})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _alta(client: Any, cabeceras: dict[str, str], **extra: Any) -> dict[str, Any]:
    n = next(_contador)
    cuerpo = {
        "vin": f"1FTFW1E80PFC{n:05d}",
        "patente": f"CS{n:04d}Q",
        "modelo": "Ranger",
        "version": "XLS",
        "circuito": "COMERCIAL",
        "id_sucursal": "SC01",
        "km_inicial": 50,
        **extra,
    }
    r = client.post("/api/v1/unidades", json=cuerpo, headers=cabeceras)
    assert r.status_code == 201, r.text
    return r.json()["unidad"]


def test_listado_exige_token(client) -> None:
    assert client.get("/api/v1/unidades").status_code == 401


def test_listado_busca_por_patente_y_vin_sin_distinguir_mayusculas(client, sesion, hash_pruebas, base) -> None:
    cab = _cabeceras(client, sesion, hash_pruebas, Rol.RESP_MKT_VENTAS)
    unidad = _alta(client, cab)
    for texto in (unidad["patente"].lower(), unidad["vin"][-8:].lower()):
        filas = client.get("/api/v1/unidades", params={"q": texto}, headers=cab).json()
        assert [f["id"] for f in filas] == [unidad["id"]]
        assert filas[0]["sucursal_nombre"] == "Casa Central"


def test_listado_filtra_por_estados_y_circuito(client, sesion, hash_pruebas, base) -> None:
    cab = _cabeceras(client, sesion, hash_pruebas, Rol.RESP_MKT_VENTAS)
    unidad = _alta(client, cab)
    params = {"estado": ["DISPONIBLE", "ASIGNADA"], "circuito": "COMERCIAL"}
    assert unidad["id"] in [f["id"] for f in client.get("/api/v1/unidades", params=params, headers=cab).json()]
    for otro in ({"estado": "BAJA"}, {"circuito": "POSVENTA"}):
        assert unidad["id"] not in [f["id"] for f in client.get("/api/v1/unidades", params=otro, headers=cab).json()]


def test_altas_recientes_primero_la_ultima(client, sesion, hash_pruebas, base) -> None:
    cab = _cabeceras(client, sesion, hash_pruebas, Rol.RESP_MKT_VENTAS)
    primera, segunda = _alta(client, cab), _alta(client, cab)
    filas = client.get("/api/v1/unidades/recientes", params={"limite": 2}, headers=cab).json()
    assert [f["id"] for f in filas] == [segunda["id"], primera["id"]]
    assert filas[0]["origen"] == "WEB"


def test_alta_guarda_proximo_service(client, sesion, hash_pruebas, base) -> None:
    cab = _cabeceras(client, sesion, hash_pruebas, Rol.RESP_MKT_VENTAS)
    assert _alta(client, cab, km_proximo_service=10000)["km_proximo_service"] == 10000


def test_limite_rotacion_segun_circuito(client, sesion, hash_pruebas, base) -> None:
    cab = _cabeceras(client, sesion, hash_pruebas, Rol.RESP_MKT_VENTAS)
    for circuito, meses in (("COMERCIAL", 6), ("POSVENTA", 12)):
        r = client.get("/api/v1/unidades/limite-rotacion", params={"circuito": circuito}, headers=cab)
        assert r.json()["meses"] == meses


def test_catalogos(client, sesion, hash_pruebas, base) -> None:
    cab = _cabeceras(client, sesion, hash_pruebas, Rol.RESP_MKT_VENTAS)
    assert {"codigo": "SC02", "nombre": "Formosa"} in client.get("/api/v1/sucursales", headers=cab).json()
    responsables = client.get("/api/v1/responsables", headers=cab).json()
    assert base.asesor.id in [r["id"] for r in responsables]
    # HU-03.3: el inactivo aparece para poder advertir la inconsistencia
    assert base.inactivo.id in [r["id"] for r in responsables if not r["activo"]]
    assert base.mkt.id not in [r["id"] for r in responsables]


def test_asignar_guarda_motivo_y_aparece_en_asignaciones(client, sesion, hash_pruebas, base) -> None:
    cab = _cabeceras(client, sesion, hash_pruebas, Rol.RESP_MKT_VENTAS)
    unidad = _alta(client, cab)
    r = client.post(
        f"/api/v1/unidades/{unidad['id']}/asignaciones",
        json={"id_responsable": base.asesor.id, "id_sucursal": "SC01", "motivo": "Demanda de la zona"},
        headers=cab,
    )
    assert r.status_code == 200, r.text
    assert r.json()["evento"]["datos"]["motivo"] == "Demanda de la zona"
    filas = client.get(f"/api/v1/unidades/{unidad['id']}/asignaciones", headers=cab).json()
    assert len(filas) == 1
    assert filas[0]["responsable_nombre"] == base.asesor.nombre
    assert filas[0]["fecha_hasta"] is None
    # La asignacion quedo grabada: la ficha la ve en una consulta posterior
    ficha = client.get(f"/api/v1/unidades/{unidad['id']}", headers=cab).json()
    assert ficha["unidad"]["estado_actual"] == "ASIGNADA"
    assert ficha["responsable_actual"]["identificador"] == base.asesor.id
