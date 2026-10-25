"""Servicio de identidad: login con bloqueo, cambio de clave y recuperacion (HU-01)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import auditoria, seguridad
from app.core.config import settings
from app.identidad.models import Rol, Usuario


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def obtener_por_correo(sesion: Session, correo: str) -> Optional[Usuario]:
    return sesion.scalar(select(Usuario).where(Usuario.correo == correo.lower().strip()))


def bloqueado_hasta(usuario: Usuario) -> bool:
    return usuario.bloqueado_hasta is not None and usuario.bloqueado_hasta > _ahora()


def ingresar(sesion: Session, correo: str, clave: str, ip: Optional[str], request: Any = None) -> dict[str, Any]:
    """HU-01.1..4: mensaje unico 'Usuario o contraseña incorrectos' con el numero de intento;
    5 intentos fallidos -> bloqueo de 15 minutos; baja en DMS -> acceso rechazado."""
    usuario = obtener_por_correo(sesion, correo)

    if usuario is None or not usuario.activo:
        # HU-01.4 y no-existente: mismo mensaje generico, sin revelar cual dato fallo
        auditoria.registrar(sesion, id_usuario=None, accion="LOGIN_FALLIDO", recurso="auth", ip=ip, resultado="FRACASO")
        sesion.commit()
        raise HTTPException(
            status_code=401,
            detail=auditoria_error("Usuario o contraseña incorrectos.", None),
        )

    if bloqueado_hasta(usuario):
        restante = int((usuario.bloqueado_hasta - _ahora()).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=423,
            detail={
                "codigo": "CUENTA_BLOQUEADA",
                "mensaje": f"Usuario o contraseña incorrectos. La cuenta está bloqueada por 15 minutos por intentos fallidos ({restante} min restantes).",
                "detalle": {"bloqueado_hasta": usuario.bloqueado_hasta.isoformat()},
            },
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
        raise HTTPException(
            status_code=401,
            detail=auditoria_error(
                f"Usuario o contraseña incorrectos (intento {usuario.intentos_fallidos + 1} de {settings.intentos_maximos})."
                if detalle_extra is None
                else f"Usuario o contraseña incorrectos. {detalle_extra}",
                None,
            ),
        )

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultima_actividad = _ahora()
    auditoria.registrar(sesion, id_usuario=usuario.id, accion="LOGIN_OK", recurso="auth", ip=ip, resultado="EXITO")
    sesion.commit()
    token = seguridad.crear_token(usuario.id, usuario.rol.value)
    return {
        "token": token,
        "debe_cambiar_clave": usuario.debe_cambiar_clave,
        "usuario": usuario,
    }


def auditoria_error(mensaje: str, detalle: Any) -> dict[str, Any]:
    return {"codigo": "CREDENCIALES_INVALIDAS", "mensaje": mensaje, "detalle": detalle}


def cambiar_clave(sesion: Session, usuario: Usuario, clave_nueva: str, ip: Optional[str]) -> None:
    """HU-01: cambio obligatorio en el primer ingreso; politica de claves eauditoria."""
    seguridad.validar_politica_clave(clave_nueva, correo=usuario.correo, nombre=usuario.nombre)
    usuario.hash_clave = seguridad.hash_clave(clave_nueva)
    usuario.debe_cambiar_clave = False
    usuario.clave_temporal_hasta = None
    auditoria.registrar(sesion, id_usuario=usuario.id, accion="CAMBIO_CLAVE", recurso="auth", ip=ip, resultado="EXITO")
    sesion.commit()


def recuperar(sesion: Session, correo: str, ip: Optional[str]) -> None:
    """Emite una contraseña temporal de un uso valida 48 h (sin revelarla por respuesta)."""
    usuario = obtener_por_correo(sesion, correo)
    if usuario is not None and usuario.activo:
        import secrets
        import string

        alfabeto = string.ascii_letters + string.digits + "!@#$%"
        temporal = "".join(secrets.choice(alfabeto) for _ in range(14))
        usuario.hash_clave = seguridad.hash_clave(temporal)
        usuario.debe_cambiar_clave = True
        usuario.clave_temporal_hasta = _ahora() + timedelta(hours=settings.validez_clave_temporal_horas)
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        # En la demo el envio de correo esta fuera de alcance: la clave se comunicaria
        # por canal corporativo. Ver docs/decisiones.md.
        auditoria.registrar(sesion, id_usuario=usuario.id, accion="RECUPERAR_CLAVE", recurso="auth", ip=ip, resultado="EXITO")
        sesion.commit()
    else:
        auditoria.registrar(sesion, id_usuario=None, accion="RECUPERAR_CLAVE", recurso="auth", ip=ip, resultado="FRACASO")
        sesion.commit()


def salir(sesion: Session, usuario: Usuario, ip: Optional[str]) -> None:
    """Cierre explicito: marca inactiva la actividad para invalidar tokens restantes."""
    usuario.ultima_actividad = _ahora() - timedelta(days=1)
    auditoria.registrar(sesion, id_usuario=usuario.id, accion="LOGOUT", recurso="auth", ip=ip, resultado="EXITO")
    sesion.commit()


MENU_POR_ROL: dict[Rol, list[str]] = {
    Rol.ADMIN: ["Inicio", "Unidades", "Sincronización DMS", "Auditoría", "Parámetros"],
    Rol.RESP_MKT_VENTAS: ["Inicio", "Unidades", "Asignaciones", "Altas"],
    Rol.ASESOR: ["Mis unidades", "Test drive"],
    Rol.RESP_POSVENTA: ["Inicio", "Unidades", "Préstamos", "Service"],
    Rol.TECNICO_TALLER: ["Service"],
    Rol.RESP_USADOS: ["Inicio", "Unidades", "Pases a venta"],
    Rol.TECNICO: [],
}


def menu_permitido(usuario: Usuario) -> list[str]:
    return MENU_POR_ROL.get(usuario.rol, [])
