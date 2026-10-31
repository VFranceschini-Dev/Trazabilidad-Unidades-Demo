"""Pruebas de identidad (HU-01) y permisos por rol, contra la API real.

Cada prueba crea sus propios usuarios (correo y legajo unicos) para no alterar los
usuarios compartidos del fixture `base`: el login modifica intentos, bloqueos y claves.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.identidad.models import Rol, Usuario
from app.unidades.models import Circuito, UnidadDemo

CLAVE = "Demo-Pruebas-2026!"
_contador = itertools.count(1)


def _crear_usuario(
    sesion: Session,
    hash_pruebas: str,
    *,
    rol: Rol = Rol.ASESOR,
    sucursal: str = "SC01",
    activo: bool = True,
    debe_cambiar_clave: bool = False,
) -> Usuario:
    n = next(_contador)
    usuario = Usuario(
        legajo=f"7{n:04d}",
        correo=f"login{n}@pruebas.local",
        nombre=f"Login Prueba {n}",
        rol=rol,
        id_sucursal=sucursal,
        hash_clave=hash_pruebas,
        activo=activo,
        debe_cambiar_clave=debe_cambiar_clave,
    )
    sesion.add(usuario)
    sesion.commit()
    return usuario


def _ingresar(client: Any, correo: str, clave: str = CLAVE) -> Any:
    return client.post("/api/v1/auth/ingresar", json={"correo": correo, "clave": clave})


def _token(client: Any, correo: str) -> dict[str, str]:
    r = _ingresar(client, correo)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _error(r: Any) -> dict[str, Any]:
    """Cuerpo del error en el formato comun {codigo, mensaje, detalle}."""
    return r.json()


def _recargar(fabrica_sesion: Any, id_usuario: int) -> Usuario:
    with fabrica_sesion() as ses:
        return ses.get(Usuario, id_usuario)


# --- Enums leidos desde la base (regresion del error 500 en el login) ---------------


def test_rol_y_circuito_se_leen_como_enum(fabrica_sesion, base, hash_pruebas) -> None:
    from soporte import alta_unidad

    with fabrica_sesion() as ses:
        usuario = _crear_usuario(ses, hash_pruebas, rol=Rol.RESP_MKT_VENTAS)
        unidad = alta_unidad(ses, base, circuito=Circuito.POSVENTA)
        ses.commit()
        id_usuario, id_unidad = usuario.id, unidad.id
    # Sesion nueva: los valores vienen de la base y no del mapa de identidad.
    with fabrica_sesion() as ses:
        assert ses.get(Usuario, id_usuario).rol is Rol.RESP_MKT_VENTAS
        assert ses.get(UnidadDemo, id_unidad).circuito is Circuito.POSVENTA


# --- HU-01: ingreso ----------------------------------------------------------------


def test_ingreso_correcto_devuelve_token_y_usuario(client, sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas, rol=Rol.RESP_POSVENTA, debe_cambiar_clave=True)
    r = _ingresar(client, usuario.correo)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["token"]
    assert cuerpo["debe_cambiar_clave"] is True
    assert cuerpo["usuario"]["rol"] == "RESP_POSVENTA"
    assert cuerpo["usuario"]["correo"] == usuario.correo


def test_ingreso_ignora_mayusculas_y_espacios_del_correo(client, sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas)
    r = _ingresar(client, f"  {usuario.correo.upper()} ")
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("caso", ["clave_incorrecta", "correo_inexistente", "usuario_inactivo"])
def test_ingreso_fallido_mensaje_generico(client, sesion, hash_pruebas, caso) -> None:
    """HU-01: el mismo mensaje sin revelar cual dato fallo (HU-01.4: baja en DMS)."""
    usuario = _crear_usuario(sesion, hash_pruebas, activo=caso != "usuario_inactivo")
    correo = "nadie@pruebas.local" if caso == "correo_inexistente" else usuario.correo
    clave = "Otra-Clave-2026!" if caso == "clave_incorrecta" else CLAVE
    r = _ingresar(client, correo, clave)
    assert r.status_code == 401
    error = _error(r)
    assert error["codigo"] == "CREDENCIALES_INVALIDAS"
    assert error["mensaje"].startswith("Usuario o contraseña incorrectos")


def test_ingreso_fallido_informa_numero_de_intento(client, sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas)
    for intento in (1, 2):
        r = _ingresar(client, usuario.correo, "Otra-Clave-2026!")
        assert f"intento {intento} de {settings.intentos_maximos}" in _error(r)["mensaje"]


def test_ingreso_correcto_reinicia_intentos(client, sesion, fabrica_sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas)
    _ingresar(client, usuario.correo, "Otra-Clave-2026!")
    _ingresar(client, usuario.correo, "Otra-Clave-2026!")
    assert _recargar(fabrica_sesion, usuario.id).intentos_fallidos == 2
    assert _ingresar(client, usuario.correo).status_code == 200
    assert _recargar(fabrica_sesion, usuario.id).intentos_fallidos == 0


def test_bloqueo_tras_intentos_maximos(client, sesion, fabrica_sesion, hash_pruebas) -> None:
    """HU-01: 5 intentos fallidos bloquean la cuenta 15 minutos, aun con la clave correcta."""
    usuario = _crear_usuario(sesion, hash_pruebas)
    for _ in range(settings.intentos_maximos - 1):
        assert _ingresar(client, usuario.correo, "Otra-Clave-2026!").status_code == 401
    r = _ingresar(client, usuario.correo, "Otra-Clave-2026!")
    assert r.status_code == 401
    assert "bloqueada" in _error(r)["mensaje"]
    bloqueado = _recargar(fabrica_sesion, usuario.id).bloqueado_hasta
    assert bloqueado is not None
    esperado = datetime.now(timezone.utc) + timedelta(minutes=settings.bloqueo_minutos)
    assert abs((bloqueado - esperado).total_seconds()) < 60

    r = _ingresar(client, usuario.correo)
    assert r.status_code == 423
    assert _error(r)["codigo"] == "CUENTA_BLOQUEADA"


def test_bloqueo_vencido_permite_ingresar(client, sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas)
    usuario.bloqueado_hasta = datetime.now(timezone.utc) - timedelta(minutes=1)
    sesion.commit()
    assert _ingresar(client, usuario.correo).status_code == 200


def test_errores_de_autenticacion_con_formato_comun(client) -> None:
    """La API responde errores como {codigo, mensaje, detalle} en la raiz (main.py);
    el frontend lee `mensaje` de la raiz para mostrarlo."""
    r = _ingresar(client, "nadie@pruebas.local", "Otra-Clave-2026!")
    assert r.status_code == 401
    assert {"codigo", "mensaje", "detalle"} <= set(r.json())


# --- HU-01: cambio y recuperacion de clave -----------------------------------------


def test_cambio_de_clave_primer_ingreso(client, sesion, fabrica_sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas, debe_cambiar_clave=True)
    cabeceras = _token(client, usuario.correo)
    nueva = "Nueva-Segura-2027"
    r = client.post("/api/v1/auth/cambiar-clave", json={"clave_nueva": nueva}, headers=cabeceras)
    assert r.status_code == 200, r.text
    assert _recargar(fabrica_sesion, usuario.id).debe_cambiar_clave is False
    assert _ingresar(client, usuario.correo, CLAVE).status_code == 401
    assert _ingresar(client, usuario.correo, nueva).status_code == 200


@pytest.mark.parametrize(
    "clave",
    [
        "corta1A",            # menos de 10 caracteres
        "sinmayuscula2026",   # sin mayuscula
        "SINMINUSCULA2026",   # sin minuscula
        "SinNumeroAlguno",    # sin numero
    ],
)
def test_cambio_de_clave_rechaza_clave_debil(client, sesion, hash_pruebas, clave) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas, debe_cambiar_clave=True)
    r = client.post(
        "/api/v1/auth/cambiar-clave", json={"clave_nueva": clave}, headers=_token(client, usuario.correo)
    )
    assert r.status_code == 422


def test_cambio_de_clave_rechaza_correo_en_la_clave(client, sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas, debe_cambiar_clave=True)
    clave = usuario.correo.split("@")[0].capitalize() + "X2026"
    r = client.post(
        "/api/v1/auth/cambiar-clave", json={"clave_nueva": clave}, headers=_token(client, usuario.correo)
    )
    assert r.status_code == 422
    assert "no puede contener el correo" in _error(r)["detalle"]


def test_recuperar_no_revela_si_el_correo_existe(client, sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas)
    existe = client.post("/api/v1/auth/recuperar", json={"correo": usuario.correo})
    no_existe = client.post("/api/v1/auth/recuperar", json={"correo": "nadie@pruebas.local"})
    assert existe.status_code == no_existe.status_code == 200
    assert existe.json() == no_existe.json()


def test_recuperar_emite_clave_temporal_y_desbloquea(client, sesion, fabrica_sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas)
    usuario.intentos_fallidos = 3
    usuario.bloqueado_hasta = datetime.now(timezone.utc) + timedelta(minutes=10)
    sesion.commit()
    client.post("/api/v1/auth/recuperar", json={"correo": usuario.correo})
    recargado = _recargar(fabrica_sesion, usuario.id)
    assert recargado.debe_cambiar_clave is True
    assert recargado.intentos_fallidos == 0
    assert recargado.bloqueado_hasta is None
    assert recargado.clave_temporal_hasta is not None
    # La clave anterior deja de servir: solo vale la temporal (no se revela por respuesta).
    assert _ingresar(client, usuario.correo).status_code == 401


def test_clave_temporal_vencida_no_permite_ingresar(client, sesion, hash_pruebas) -> None:
    """HU-01: la contraseña temporal de recuperacion vale 48 h."""
    usuario = _crear_usuario(sesion, hash_pruebas, debe_cambiar_clave=True)
    usuario.clave_temporal_hasta = datetime.now(timezone.utc) - timedelta(minutes=1)
    sesion.commit()
    assert _ingresar(client, usuario.correo).status_code == 401


# --- Sesion y token ----------------------------------------------------------------


def test_rutas_protegidas_exigen_token(client) -> None:
    r = client.get("/api/v1/yo")
    assert r.status_code == 401
    assert _error(r)["codigo"] == "SIN_TOKEN"


def test_token_invalido_rechazado(client) -> None:
    r = client.get("/api/v1/yo", headers={"Authorization": "Bearer no-es-un-jwt"})
    assert r.status_code == 401
    assert _error(r)["codigo"] == "TOKEN_INVALIDO"


def test_token_vencido_rechazado(client, sesion, hash_pruebas) -> None:
    import jwt

    usuario = _crear_usuario(sesion, hash_pruebas)
    pasado = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(usuario.id), "rol": usuario.rol.value, "iat": pasado, "exp": pasado},
        settings.jwt_secret,
        algorithm=settings.jwt_algoritmo,
    )
    r = client.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert _error(r)["codigo"] == "TOKEN_VENCIDO"


def test_salir_invalida_el_token(client, sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas)
    cabeceras = _token(client, usuario.correo)
    assert client.get("/api/v1/yo", headers=cabeceras).status_code == 200
    assert client.post("/api/v1/auth/salir", headers=cabeceras).status_code == 200
    r = client.get("/api/v1/yo", headers=cabeceras)
    assert r.status_code == 401
    assert _error(r)["codigo"] == "SESION_INACTIVA"


def test_usuario_dado_de_baja_pierde_acceso_con_token_vigente(client, sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas)
    cabeceras = _token(client, usuario.correo)
    usuario.activo = False
    sesion.commit()
    r = client.get("/api/v1/yo", headers=cabeceras)
    assert r.status_code == 401
    assert _error(r)["codigo"] == "USUARIO_INVALIDO"


# --- Permisos por rol --------------------------------------------------------------


@pytest.mark.parametrize(
    "rol,menu_esperado",
    [
        (Rol.RESP_MKT_VENTAS, ["Inicio", "Unidades", "Asignaciones", "Altas", "Alertas"]),
        (Rol.ASESOR, ["Mis unidades", "Test drive"]),
        (Rol.RESP_POSVENTA, ["Inicio", "Unidades", "Altas", "Préstamos", "Service", "Alertas"]),
    ],
)
def test_menu_permitido_segun_rol(client, sesion, hash_pruebas, rol, menu_esperado) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas, rol=rol)
    r = client.get("/api/v1/yo", headers=_token(client, usuario.correo))
    assert r.status_code == 200, r.text
    assert r.json()["menu_permitido"] == menu_esperado
    assert r.json()["sucursal_nombre"] == "Casa Central"


def test_requerir_rol_rechaza_otro_rol(client, sesion, hash_pruebas) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas, rol=Rol.ASESOR)
    r = client.post("/api/v1/sincronizacion/dms", headers=_token(client, usuario.correo))
    assert r.status_code == 403
    assert _error(r)["codigo"] == "SIN_PERMISO"


def _alta(client: Any, cabeceras: dict[str, str], circuito: str) -> Any:
    n = next(_contador)
    return client.post(
        "/api/v1/unidades",
        json={
            "vin": f"1FTFW1E80PFL{n:05d}",
            "patente": f"LG{n:04d}Z",
            "modelo": "Ranger",
            "version": "XLS 4x4",
            "circuito": circuito,
            "id_sucursal": "SC01",
            "km_inicial": 100,
        },
        headers=cabeceras,
    )


@pytest.mark.parametrize(
    "rol,circuito,estado",
    [
        (Rol.RESP_MKT_VENTAS, "COMERCIAL", 201),
        (Rol.RESP_MKT_VENTAS, "POSVENTA", 403),
        (Rol.RESP_POSVENTA, "POSVENTA", 201),
        (Rol.RESP_POSVENTA, "COMERCIAL", 403),
        (Rol.ASESOR, "COMERCIAL", 403),
        (Rol.ADMIN, "COMERCIAL", 403),
    ],
)
def test_alta_de_unidad_segun_rol_y_circuito(client, sesion, hash_pruebas, rol, circuito, estado) -> None:
    usuario = _crear_usuario(sesion, hash_pruebas, rol=rol)
    r = _alta(client, _token(client, usuario.correo), circuito)
    assert r.status_code == estado, r.text


def test_auditoria_registra_ingresos(client, sesion, fabrica_sesion, hash_pruebas) -> None:
    from app.tablas_generales.models import Auditoria

    usuario = _crear_usuario(sesion, hash_pruebas)
    _ingresar(client, usuario.correo, "Otra-Clave-2026!")
    _ingresar(client, usuario.correo)
    with fabrica_sesion() as ses:
        acciones = ses.scalars(
            select(Auditoria.accion).where(Auditoria.id_usuario == usuario.id).order_by(Auditoria.id)
        ).all()
    assert acciones == ["LOGIN_FALLIDO", "LOGIN_OK"]
