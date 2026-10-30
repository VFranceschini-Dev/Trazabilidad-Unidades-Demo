"""Catalogos de lectura para las pantallas: sucursales y responsables (HU-03)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.seguridad import obtener_usuario
from app.identidad.models import Rol, Usuario
from app.tablas_generales.models import Sucursal
from app.unidades.esquemas import ResponsableOpcionOut, SucursalOut

router = APIRouter(tags=["catalogos"])


@router.get("/sucursales", response_model=list[SucursalOut])
def sucursales(usuario: Any = Depends(obtener_usuario), sesion: Session = Depends(get_session)) -> list[Sucursal]:
    return list(sesion.scalars(select(Sucursal).where(Sucursal.activa.is_(True)).order_by(Sucursal.codigo)))


@router.get("/responsables", response_model=list[ResponsableOpcionOut])
def responsables(
    usuario: Any = Depends(obtener_usuario), sesion: Session = Depends(get_session)
) -> list[Usuario]:
    """Asesores sincronizados desde el DMS. Incluye inactivos: HU-03.3 pide advertir la
    inconsistencia al seleccionarlos, no ocultarlos."""
    return list(sesion.scalars(select(Usuario).where(Usuario.rol == Rol.ASESOR).order_by(Usuario.nombre)))
