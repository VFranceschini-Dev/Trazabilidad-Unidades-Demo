"""Esquemas de entrada y salida del uso comercial."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.comercial.models import TipoUso
from app.unidades.esquemas import UnidadOut


class SalidaIn(BaseModel):
    id_unidad: int
    tipo_uso: TipoUso
    km_salida: int = Field(ge=0)
    cliente_nombre: Optional[str] = Field(default=None, max_length=120)
    cliente_telefono: Optional[str] = Field(default=None, max_length=160)
    observaciones: Optional[str] = None
    fecha_hora: Optional[datetime] = None  # carga diferida


class RegresoIn(BaseModel):
    km_regreso: int = Field(ge=0)
    observaciones: Optional[str] = None
    fecha_hora: Optional[datetime] = None  # carga diferida


class UsoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_uso: int
    id_unidad: int
    tipo_uso: TipoUso
    id_usuario: int
    id_cliente: Optional[int] = None
    fecha_hora_salida: datetime
    fecha_hora_regreso: Optional[datetime] = None
    km_salida: int
    km_regreso: Optional[int] = None
    observaciones: Optional[str] = None


class MiUnidadOut(BaseModel):
    """Unidad a cargo del asesor, con la salida abierta si esta en uso."""

    unidad: UnidadOut
    uso_abierto: Optional[UsoOut] = None
