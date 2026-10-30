"""Ruta de sincronización manual con el DMS (HU-15); la programada corre en un task interno."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.seguridad import requerir_rol
from app.identidad.models import Rol
from app.sincronizacion.dms import DMSDesdeHTTP
from app.sincronizacion.service import ResultadoSync, sincronizar

router = APIRouter(prefix="/sincronizacion", tags=["sincronizacion"])


@router.post("/dms")
def sync_dms(
    fallar: bool = Query(default=False, description="?fallar=1 fuerza el error de comunicación (HU-15.3)"),
    usuario: Any = Depends(requerir_rol(Rol.ADMIN.value)),
    sesion: Session = Depends(get_session),
) -> dict[str, Any]:
    resultado = sincronizar(sesion, DMSDesdeHTTP(fallar=fallar), usuario)
    return {
        "creados": resultado.creados,
        "actualizados": resultado.actualizados,
        "dados_de_baja": resultado.dados_de_baja,
        "unidades_alta": resultado.unidades_alta,
        "unidades_omitidas": resultado.unidades_omitidas,
        "error": resultado.error,
    }
