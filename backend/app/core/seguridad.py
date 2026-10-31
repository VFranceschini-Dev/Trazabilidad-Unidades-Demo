"""Seguridad: bcrypt, politica de claves, JWT y dependencias de autenticacion.

Toda ruta exige token y rol salvo `salud` y `auth/ingresar`. El cierre de sesion por
inactividad se controla en el servidor con la marca `ultima_actividad` del usuario.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator

import jwt
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_session
from app.core.excepciones import ErrorDominio, SinPermiso

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
_bearer = HTTPBearer(auto_error=False)

_LISTA_COMUNES = Path(__file__).resolve().parent.parent.parent / "datos" / "contrasenas_comunes.txt"
_cache_comunes: frozenset[str] | None = None


def hash_clave(clave: str) -> str:
    return pwd_context.hash(clave)


def verificar_clave(clave: str, hash_stored: str) -> bool:
    try:
        return pwd_context.verify(clave, hash_stored)
    except ValueError:
        return False


def _comunes() -> frozenset[str]:
    global _cache_comunes
    if _cache_comunes is None:
        lineas: list[str] = []
        if _LISTA_COMUNES.exists():
            lineas = [l.strip().lower() for l in _LISTA_COMUNES.read_text(encoding="utf-8").splitlines() if l.strip()]
        _cache_comunes = frozenset(lineas)
    return _cache_comunes


def validar_politica_clave(clave: str, *, correo: str = "", nombre: str = "") -> None:
    """Minimo 10 caracteres, mayuscula, minuscula, numero; sin nombre ni correo; no comun."""
    errores: list[str] = []
    if len(clave) < 10:
        errores.append("minimo 10 caracteres")
    if not re.search(r"[A-Z]", clave):
        errores.append("una letra mayuscula")
    if not re.search(r"[a-z]", clave):
        errores.append("una letra minuscula")
    if not re.search(r"[0-9]", clave):
        errores.append("un numero")
    bajo = clave.lower()
    if correo and correo.split("@")[0].lower() in bajo:
        errores.append("no puede contener el correo")
    for parte in (nombre or "").lower().split():
        if len(parte) >= 4 and parte in bajo:
            errores.append("no puede contener el nombre")
    if bajo in _comunes():
        errores.append("es una de las contraseñas mas comunes")
    if errores:
        raise ErrorDominio(
            codigo="CLAVE_DEBIL",
            mensaje="La contraseña no cumple la política.",
            detalle=errores,
            estado_http=422,
        )


def crear_token(id_usuario: int, rol: str, version_sesion: int = 0) -> str:
    ahora = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(id_usuario),
        "rol": rol,
        "sv": version_sesion,
        "iat": ahora,
        "exp": ahora + timedelta(hours=settings.duracion_token_horas),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algoritmo)


def decodificar_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algoritmo])
    except jwt.ExpiredSignatureError as exc:
        raise ErrorDominio(
            codigo="TOKEN_VENCIDO",
            mensaje="La sesión venció. Ingrese nuevamente.",
            detalle=None,
            estado_http=401,
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise ErrorDominio(
            codigo="TOKEN_INVALIDO",
            mensaje="Token inválido.",
            detalle=None,
            estado_http=401,
        ) from exc


def _usuario_autenticado(sesion: Session, token: str) -> Any:
    from app.identidad.models import Usuario  # import local para evitar ciclo

    datos = decodificar_token(token)
    usuario = sesion.get(Usuario, int(datos["sub"]))
    if usuario is None or not usuario.activo:
        raise ErrorDominio(
            codigo="USUARIO_INVALIDO",
            mensaje="El usuario no está activo.",
            detalle=None,
            estado_http=401,
        )
    if datos.get("sv", 0) != usuario.version_sesion:
        raise ErrorDominio(
            codigo="SESION_INVALIDADA",
            mensaje="La sesión se cerró porque se restableció la contraseña.",
            detalle=None,
            estado_http=401,
        )
    ahora = datetime.now(timezone.utc)
    limite = ahora - timedelta(minutes=settings.sesion_inactiva_minutos)
    ultima = usuario.ultima_actividad
    if ultima is not None and ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    if ultima is not None and ultima < limite:
        raise ErrorDominio(
            codigo="SESION_INACTIVA",
            mensaje="La sesión cerró por inactividad.",
            detalle=None,
            estado_http=401,
        )
    sesion.execute(update(Usuario).where(Usuario.id == usuario.id).values(ultima_actividad=ahora))
    sesion.commit()
    return usuario


def obtener_usuario(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer),
    sesion: Session = Depends(get_session),
) -> Any:
    if credenciales is None:
        raise ErrorDominio(
            codigo="SIN_TOKEN",
            mensaje="Falta el token de acceso.",
            detalle=None,
            estado_http=401,
        )
    return _usuario_autenticado(sesion, credenciales.credentials)


def requerir_rol(*roles: str) -> Any:
    """Dependencia fabrica: exige que el usuario tenga alguno de los roles indicados."""

    def dependencia(usuario: Any = Depends(obtener_usuario)) -> Any:
        if usuario.rol.value not in roles:
            raise SinPermiso(f"Su rol ({usuario.rol.value}) no puede ejecutar esta operación.")
        return usuario

    return dependencia


def verificar_api_key_n8n(x_api_key: str = Header(default="")) -> None:
    """Acceso del usuario técnico de n8n: API key por cabecera, limitado a la ingesta."""
    if x_api_key != settings.n8n_api_key:
        raise ErrorDominio(
            codigo="API_KEY_INVALIDA",
            mensaje="API key incorrecta.",
            detalle=None,
            estado_http=401,
        )


def generator_placeholder() -> Generator[None, None, None]:  # pragma: no cover
    yield None
