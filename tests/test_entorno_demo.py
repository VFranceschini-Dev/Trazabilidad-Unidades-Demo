"""Entorno de demostracion (ENTORNO, cuentas es_demo), lista de claves comunes y auditoria
de operaciones de unidades con IP."""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core import seguridad
from app.core.config import settings
from app.identidad.models import Rol, Usuario
from app.tablas_generales.models import Auditoria
from app.unidades.models import UnidadDemo

CLAVE = "Demo-Pruebas-2026!"
_contador = itertools.count(1)


def _usuario_demo(sesion, hash_pruebas, *, es_demo: bool, rol: Rol = Rol.ASESOR) -> Usuario:
    n = next(_contador)
    usuario = Usuario(
        legajo=f"8{n:04d}",
        correo=f"entorno{n}@pruebas.local",
        nombre=f"Entorno Prueba {n}",
        rol=rol,
        id_sucursal="SC01",
        hash_clave=hash_pruebas,
        es_demo=es_demo,
    )
    sesion.add(usuario)
    sesion.commit()
    return usuario


def _ingresar(client, correo: str):
    return client.post("/api/v1/auth/ingresar", json={"correo": correo, "clave": CLAVE})


# --- ENTORNO: la semilla solo corre en demo ----------------------------------------


def test_semilla_se_niega_a_correr_en_produccion(monkeypatch, fabrica_sesion, base) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import seed

    monkeypatch.setattr(settings, "entorno", "produccion")
    with fabrica_sesion() as ses:
        antes = len(ses.scalars(select(Usuario)).all())
    with pytest.raises(SystemExit, match="ENTORNO=demo"):
        seed.sembrar()
    with fabrica_sesion() as ses:
        assert len(ses.scalars(select(Usuario)).all()) == antes


def test_entorno_por_defecto_es_produccion() -> None:
    """Sin .env la instalacion nunca habilita la semilla ni las cuentas de demo."""
    from app.core.config import Settings

    assert Settings.model_fields["entorno"].default == "produccion"


# --- Cuentas es_demo ---------------------------------------------------------------


def test_cuenta_demo_ingresa_en_entorno_demo(monkeypatch, client, sesion, hash_pruebas) -> None:
    monkeypatch.setattr(settings, "entorno", "demo")
    usuario = _usuario_demo(sesion, hash_pruebas, es_demo=True)
    assert _ingresar(client, usuario.correo).status_code == 200


def test_cuenta_demo_no_ingresa_en_produccion(monkeypatch, client, sesion, hash_pruebas) -> None:
    monkeypatch.setattr(settings, "entorno", "produccion")
    usuario = _usuario_demo(sesion, hash_pruebas, es_demo=True)
    r = _ingresar(client, usuario.correo)
    assert r.status_code == 401
    assert r.json()["codigo"] == "CREDENCIALES_INVALIDAS"


def test_cuenta_normal_ingresa_en_produccion(monkeypatch, client, sesion, hash_pruebas) -> None:
    monkeypatch.setattr(settings, "entorno", "produccion")
    usuario = _usuario_demo(sesion, hash_pruebas, es_demo=False)
    assert _ingresar(client, usuario.correo).status_code == 200


# --- Lista de claves comunes -------------------------------------------------------


def test_lista_de_claves_comunes_cargada() -> None:
    comunes = seguridad._comunes()
    assert len(comunes) == 1000
    assert {"password", "123456", "qwerty"} <= comunes


def test_politica_rechaza_clave_comun(monkeypatch) -> None:
    """Las 1.000 de la lista tienen menos de 10 caracteres; se prueba la regla con una
    lista ampliada para que solo falle por ser comun."""
    monkeypatch.setattr(seguridad, "_cache_comunes", frozenset({"contrasena2026segura"}))
    with pytest.raises(Exception) as exc:
        seguridad.validar_politica_clave("Contrasena2026Segura")
    assert "es una de las contraseñas mas comunes" in exc.value.detalle


# --- Operaciones de unidades: persistencia y auditoria con IP ----------------------


def test_alta_por_api_persiste_y_audita_ip(client, sesion, fabrica_sesion, hash_pruebas) -> None:
    usuario = _usuario_demo(sesion, hash_pruebas, es_demo=False, rol=Rol.RESP_MKT_VENTAS)
    token = _ingresar(client, usuario.correo).json()["token"]
    n = next(_contador)
    r = client.post(
        "/api/v1/unidades",
        json={
            "vin": f"1FTFW1E80PFE{n:05d}",
            "patente": f"EN{n:04d}Z",
            "modelo": "Ranger",
            "version": "XLS 4x4",
            "circuito": "COMERCIAL",
            "id_sucursal": "SC01",
            "km_inicial": 100,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    id_unidad = r.json()["unidad"]["id"]
    # Sesion nueva: la operacion tiene que haber quedado confirmada en la base.
    with fabrica_sesion() as ses:
        assert ses.get(UnidadDemo, id_unidad) is not None
        auditoria = ses.scalars(
            select(Auditoria).where(Auditoria.accion == "ALTA_UNIDAD", Auditoria.recurso == f"unidad:{id_unidad}")
        ).one()
        assert auditoria.ip == "testclient"
