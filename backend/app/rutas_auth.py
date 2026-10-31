"""Rutas de identidad (HU-01): /auth/* y /yo."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import auditoria, correo
from app.core.db import get_session
from app.core.seguridad import obtener_usuario
from app.identidad import service
from app.identidad.esquemas import CambiarClaveIn, IngresarIn, IngresarOut, RecuperarIn, RestablecerIn, UsuarioOut, YoOut
from app.tablas_generales.models import Sucursal

router = APIRouter(tags=["identidad"])


@router.post("/auth/ingresar", response_model=IngresarOut)
def ingresar(datos: IngresarIn, request: Request, sesion: Session = Depends(get_session)) -> IngresarOut:
    ip = auditoria.ip_desde_request(request)
    resultado = service.ingresar(sesion, datos.correo, datos.clave, ip)
    usuario = resultado["usuario"]
    return IngresarOut(
        token=resultado["token"],
        debe_cambiar_clave=resultado["debe_cambiar_clave"],
        usuario=UsuarioOut.model_validate(usuario),
    )


@router.post("/auth/salir")
def salir(
    request: Request,
    usuario=Depends(obtener_usuario),
    sesion: Session = Depends(get_session),
) -> dict[str, str]:
    service.salir(sesion, usuario, auditoria.ip_desde_request(request))
    return {"estado": "sesion cerrada"}


@router.post("/auth/cambiar-clave")
def cambiar_clave(
    datos: CambiarClaveIn,
    request: Request,
    usuario=Depends(obtener_usuario),
    sesion: Session = Depends(get_session),
) -> dict[str, str]:
    service.cambiar_clave(sesion, usuario, datos.clave_nueva, auditoria.ip_desde_request(request))
    return {"estado": "clave actualizada"}


@router.post("/auth/recuperar")
def recuperar(
    datos: RecuperarIn, request: Request, tareas: BackgroundTasks, sesion: Session = Depends(get_session)
) -> dict[str, str]:
    """Respuesta identica exista o no el correo: el envio va en segundo plano para que tampoco la demora lo revele."""
    mensaje = service.recuperar(sesion, datos.correo, auditoria.ip_desde_request(request))
    if mensaje is not None:
        tareas.add_task(correo.enviar, *mensaje)
    return {"estado": "si el correo existe se envió un enlace válido por 30 minutos"}


@router.post("/auth/restablecer")
def restablecer(datos: RestablecerIn, request: Request, sesion: Session = Depends(get_session)) -> dict[str, str]:
    service.restablecer(sesion, datos.token, datos.clave_nueva, auditoria.ip_desde_request(request))
    return {"estado": "clave actualizada"}


@router.get("/yo", response_model=YoOut)
def yo(usuario=Depends(obtener_usuario), sesion: Session = Depends(get_session)) -> YoOut:
    sucursal = sesion.scalar(select(Sucursal).where(Sucursal.codigo == usuario.id_sucursal)) if usuario.id_sucursal else None
    return YoOut(
        usuario=UsuarioOut.model_validate(usuario),
        sucursal_nombre=sucursal.nombre if sucursal is not None else None,
        menu_permitido=service.menu_permitido(usuario),
    )
