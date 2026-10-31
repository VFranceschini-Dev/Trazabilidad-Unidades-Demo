"""Servicio de identidad: login con bloqueo, cambio de clave y recuperacion (HU-01)."""

from __future__ import annotations

import hashlib
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import auditoria, seguridad
from app.core.config import settings
from app.core.excepciones import ErrorDominio
from app.identidad.models import Rol, TokenRecuperacion, Usuario


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def obtener_por_correo(sesion: Session, correo: str) -> Optional[Usuario]:
    return sesion.scalar(select(Usuario).where(Usuario.correo == correo.lower().strip()))


def bloqueado_hasta(usuario: Usuario) -> bool:
    return usuario.bloqueado_hasta is not None and usuario.bloqueado_hasta > _ahora()


def ingresar(sesion: Session, correo: str, clave: str, ip: Optional[str], request: Any = None) -> dict[str, Any]:
    """HU-01.1..4: mensaje unico 'Usuario o contraseña incorrectos' con el numero de intento;
    5 intentos fallidos -> bloqueo de 15 minutos; baja en DMS -> acceso rechazado;
    cuenta es_demo con ENTORNO=produccion -> acceso rechazado."""
    usuario = obtener_por_correo(sesion, correo)

    cuenta_demo_bloqueada = usuario is not None and usuario.es_demo and settings.entorno != "demo"
    if usuario is None or not usuario.activo or cuenta_demo_bloqueada:
        # HU-01.4, no-existente y cuenta de demo fuera de ENTORNO=demo: mismo mensaje
        # generico, sin revelar cual dato fallo
        auditoria.registrar(sesion, id_usuario=None, accion="LOGIN_FALLIDO", recurso="auth", ip=ip, resultado="FRACASO")
        sesion.commit()
        raise credenciales_invalidas("Usuario o contraseña incorrectos.")

    if bloqueado_hasta(usuario):
        restante = int((usuario.bloqueado_hasta - _ahora()).total_seconds() // 60) + 1
        raise ErrorDominio(
            codigo="CUENTA_BLOQUEADA",
            mensaje=f"Usuario o contraseña incorrectos. La cuenta está bloqueada por 15 minutos por intentos fallidos ({restante} min restantes).",
            detalle={"bloqueado_hasta": usuario.bloqueado_hasta.isoformat()},
            estado_http=423,
        )

    if not seguridad.verificar_clave(clave, usuario.hash_clave):
        usuario.intentos_fallidos += 1
        detalle_extra = None
        if usuario.intentos_fallidos >= settings.intentos_maximos:
            usuario.bloqueado_hasta = _ahora() + timedelta(minutes=settings.bloqueo_minutos)
            usuario.intentos_fallidos = 0
            detalle_extra = "La cuenta quedó bloqueada por 15 minutos."
        auditoria.registrar(sesion, id_usuario=usuario.id, accion="LOGIN_FALLIDO", recurso="auth", ip=ip, resultado="FRACASO")
        sesion.commit()
        raise credenciales_invalidas(
            f"Usuario o contraseña incorrectos (intento {usuario.intentos_fallidos} de {settings.intentos_maximos})."
            if detalle_extra is None
            else f"Usuario o contraseña incorrectos. {detalle_extra}"
        )

    if usuario.clave_temporal_hasta is not None and usuario.clave_temporal_hasta < _ahora():
        # HU-01: la clave temporal de recuperacion vale 48 h; vencida, hay que pedir otra
        auditoria.registrar(sesion, id_usuario=usuario.id, accion="LOGIN_FALLIDO", recurso="auth", ip=ip, resultado="FRACASO")
        sesion.commit()
        raise ErrorDominio(
            codigo="CLAVE_TEMPORAL_VENCIDA",
            mensaje="La contraseña temporal venció. Solicite una nueva con «¿Olvidó su contraseña?».",
            estado_http=401,
        )

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultima_actividad = _ahora()
    auditoria.registrar(sesion, id_usuario=usuario.id, accion="LOGIN_OK", recurso="auth", ip=ip, resultado="EXITO")
    sesion.commit()
    token = seguridad.crear_token(usuario.id, usuario.rol.value, usuario.version_sesion)
    return {
        "token": token,
        "debe_cambiar_clave": usuario.debe_cambiar_clave,
        "usuario": usuario,
    }


def credenciales_invalidas(mensaje: str) -> ErrorDominio:
    return ErrorDominio(codigo="CREDENCIALES_INVALIDAS", mensaje=mensaje, estado_http=401)


def cambiar_clave(sesion: Session, usuario: Usuario, clave_nueva: str, ip: Optional[str]) -> None:
    """HU-01: cambio obligatorio en el primer ingreso; politica de claves eauditoria."""
    seguridad.validar_politica_clave(clave_nueva, correo=usuario.correo, nombre=usuario.nombre)
    usuario.hash_clave = seguridad.hash_clave(clave_nueva)
    usuario.debe_cambiar_clave = False
    usuario.clave_temporal_hasta = None
    usuario.clave_cambiada_en = _ahora()
    # Un enlace pedido antes del cambio ya no debe poder pisar la clave nueva
    _anular_enlaces(sesion, usuario.id)
    auditoria.registrar(sesion, id_usuario=usuario.id, accion="CAMBIO_CLAVE", recurso="auth", ip=ip, resultado="EXITO")
    sesion.commit()


def generar_clave_temporal() -> str:
    """Clave de un solo uso para una cuenta nueva: se reemplaza en el primer ingreso."""
    alfabeto = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alfabeto) for _ in range(14))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _anular_enlaces(sesion: Session, id_usuario: int) -> None:
    sesion.execute(
        update(TokenRecuperacion)
        .where(TokenRecuperacion.id_usuario == id_usuario, TokenRecuperacion.usado_en.is_(None))
        .values(usado_en=_ahora())
    )


def _cuenta_habilitada(usuario: Optional[Usuario]) -> bool:
    return usuario is not None and usuario.activo and (not usuario.es_demo or settings.entorno == "demo")


def recuperar(sesion: Session, correo: str, ip: Optional[str]) -> Optional[tuple[str, str, str]]:
    """Crea un enlace de un solo uso sin tocar la clave vigente. Devuelve el correo a enviar, si corresponde."""
    usuario = sesion.scalar(select(Usuario).where(Usuario.correo == correo.lower().strip()).with_for_update())
    if not _cuenta_habilitada(usuario):
        auditoria.registrar(sesion, id_usuario=None, accion="RECUPERAR_CLAVE", recurso="auth", ip=ip, resultado="FRACASO")
        sesion.commit()
        return None

    recientes = sesion.scalar(
        select(func.count())
        .select_from(TokenRecuperacion)
        .where(TokenRecuperacion.id_usuario == usuario.id, TokenRecuperacion.creado_en > _ahora() - timedelta(hours=1))
    )
    if recientes >= settings.enlaces_por_hora:
        auditoria.registrar(sesion, id_usuario=usuario.id, accion="RECUPERAR_CLAVE", recurso="auth", ip=ip, resultado="FRACASO")
        sesion.commit()
        return None

    _anular_enlaces(sesion, usuario.id)  # solo vale el ultimo enlace pedido
    token = secrets.token_urlsafe(32)
    sesion.add(
        TokenRecuperacion(
            id_usuario=usuario.id,
            hash_token=_hash_token(token),
            vence_en=_ahora() + timedelta(minutes=settings.validez_enlace_minutos),
        )
    )
    auditoria.registrar(sesion, id_usuario=usuario.id, accion="RECUPERAR_CLAVE", recurso="auth", ip=ip, resultado="EXITO")
    sesion.commit()
    return (
        usuario.correo,
        "Restablecer contraseña — Parque Demo",
        f"Para elegir una contraseña nueva, abra este enlace:\n\n{settings.url_publica}/?restablecer={token}\n\n"
        f"Vence a los {settings.validez_enlace_minutos} minutos y se puede usar una sola vez. "
        "Si usted no lo pidió, ignore este mensaje: su contraseña no cambió.",
    )


def restablecer(sesion: Session, token: str, clave_nueva: str, ip: Optional[str]) -> None:
    """Consume el enlace, reemplaza la clave y cierra todas las sesiones de la cuenta."""
    fila = sesion.scalar(select(TokenRecuperacion).where(TokenRecuperacion.hash_token == _hash_token(token)))
    usuario = None
    if fila is not None:
        # Primero el usuario, en el mismo orden que recuperar(): evita bloqueos cruzados y serializa el uso del enlace
        usuario = sesion.scalar(select(Usuario).where(Usuario.id == fila.id_usuario).with_for_update())
        sesion.refresh(fila)
    if fila is None or fila.usado_en is not None or fila.vence_en < _ahora() or not _cuenta_habilitada(usuario):
        auditoria.registrar(sesion, id_usuario=None, accion="RESTABLECER_CLAVE", recurso="auth", ip=ip, resultado="FRACASO")
        sesion.commit()
        raise ErrorDominio(
            codigo="ENLACE_INVALIDO",
            mensaje="El enlace no es válido o venció. Solicite uno nuevo.",
            estado_http=400,
        )
    seguridad.validar_politica_clave(clave_nueva, correo=usuario.correo, nombre=usuario.nombre)
    usuario.hash_clave = seguridad.hash_clave(clave_nueva)
    usuario.debe_cambiar_clave = False
    usuario.clave_temporal_hasta = None
    usuario.clave_cambiada_en = _ahora()
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.version_sesion += 1
    _anular_enlaces(sesion, usuario.id)
    auditoria.registrar(sesion, id_usuario=usuario.id, accion="RESTABLECER_CLAVE", recurso="auth", ip=ip, resultado="EXITO")
    sesion.commit()


def salir(sesion: Session, usuario: Usuario, ip: Optional[str]) -> None:
    """Cierre explicito: marca inactiva la actividad para invalidar tokens restantes."""
    usuario.ultima_actividad = _ahora() - timedelta(days=1)
    auditoria.registrar(sesion, id_usuario=usuario.id, accion="LOGOUT", recurso="auth", ip=ip, resultado="EXITO")
    sesion.commit()


MENU_POR_ROL: dict[Rol, list[str]] = {
    Rol.ADMIN: ["Inicio", "Unidades", "Alertas", "Sincronización DMS", "Auditoría", "Parámetros"],
    Rol.RESP_MKT_VENTAS: ["Inicio", "Unidades", "Asignaciones", "Altas", "Alertas"],
    Rol.ASESOR: ["Mis unidades", "Test drive"],
    Rol.RESP_POSVENTA: ["Inicio", "Unidades", "Altas", "Préstamos", "Service", "Alertas"],
    Rol.ADMINISTRACION: ["Inicio", "Unidades", "Infracciones", "Alertas"],
    Rol.GERENCIA: ["Tablero", "Unidades", "Alertas"],
    Rol.TECNICO: [],
}


def menu_permitido(usuario: Usuario) -> list[str]:
    return MENU_POR_ROL.get(usuario.rol, [])
