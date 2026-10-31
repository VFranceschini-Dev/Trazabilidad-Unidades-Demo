"""Rutas de uso comercial (HU-04): solo el Asesor comercial registra salidas y regresos."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.comercial import service
from app.comercial.esquemas import MiUnidadOut, RegresoIn, SalidaIn, UsoOut
from app.core import auditoria
from app.core.db import get_session
from app.core.seguridad import requerir_rol
from app.identidad.models import Rol
from app.rutas_unidades import _out

router = APIRouter(prefix="/usos", tags=["uso comercial"])


@router.get("/mis-unidades", response_model=list[MiUnidadOut])
def mis_unidades(
    usuario: Any = Depends(requerir_rol(Rol.ASESOR.value)),
    sesion: Session = Depends(get_session),
) -> list[MiUnidadOut]:
    return [
        MiUnidadOut(unidad=_out(sesion, unidad), uso_abierto=UsoOut.model_validate(uso) if uso else None)
        for unidad, uso in service.unidades_a_cargo(sesion, usuario.id)
    ]


@router.post("/salida", response_model=UsoOut, status_code=201)
def salida(
    datos: SalidaIn,
    request: Request,
    usuario: Any = Depends(requerir_rol(Rol.ASESOR.value)),
    sesion: Session = Depends(get_session),
) -> UsoOut:
    """HU-04.1 y HU-04.2: ASIGNADA -> EN_USO."""
    with sesion.begin_nested():
        _, uso = service.registrar_salida(
            sesion, datos.id_unidad,
            tipo_uso=datos.tipo_uso, km_salida=datos.km_salida, usuario=usuario,
            cliente_nombre=datos.cliente_nombre, cliente_telefono=datos.cliente_telefono,
            observaciones=datos.observaciones, fecha_hora=datos.fecha_hora,
            ip=auditoria.ip_desde_request(request),
        )
    sesion.commit()
    return UsoOut.model_validate(uso)


@router.post("/{id_uso}/regreso", response_model=UsoOut)
def regreso(
    id_uso: int,
    datos: RegresoIn,
    request: Request,
    usuario: Any = Depends(requerir_rol(Rol.ASESOR.value)),
    sesion: Session = Depends(get_session),
) -> UsoOut:
    """HU-04.3 y HU-04.4: EN_USO -> ASIGNADA con el kilometraje actualizado."""
    with sesion.begin_nested():
        _, uso = service.registrar_regreso(
            sesion, id_uso,
            km_regreso=datos.km_regreso, usuario=usuario, observaciones=datos.observaciones,
            fecha_hora=datos.fecha_hora, ip=auditoria.ip_desde_request(request),
        )
    sesion.commit()
    return UsoOut.model_validate(uso)
