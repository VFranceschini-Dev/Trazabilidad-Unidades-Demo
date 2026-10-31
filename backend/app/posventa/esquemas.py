"""Esquemas de entrada y salida de los prestamos por garantia."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class PrestamoIn(BaseModel):
    id_unidad: int
    nro_orden_reparacion: str = Field(min_length=1, max_length=20)
    cliente_documento: str = Field(min_length=1, max_length=20)
    cliente_nombre: Optional[str] = Field(default=None, max_length=120)  # obligatorio si el cliente es nuevo
    fecha_devolucion_prevista: date
    km_entrega: int = Field(ge=0)
    combustible_entrega: int = Field(ge=0, le=8, description="Octavos de tanque")
    control_previo: dict[str, bool]
    observaciones: Optional[str] = None
    fecha_hora: Optional[datetime] = None  # carga diferida


class DevolucionIn(BaseModel):
    km_devolucion: int = Field(ge=0)
    combustible_devolucion: int = Field(ge=0, le=8, description="Octavos de tanque")
    estado_devolucion: str = Field(min_length=1)
    con_danos: bool = False
    fecha_hora: Optional[datetime] = None  # carga diferida


class PrestamoOut(BaseModel):
    id_prestamo: int
    id_unidad: int
    unidad_patente: str
    unidad_modelo: str
    id_cliente: int
    cliente_nombre: str
    nro_orden_reparacion: str
    fecha_hora_entrega: datetime
    fecha_hora_devolucion: Optional[datetime] = None
    fecha_devolucion_prevista: date
    km_entrega: int
    km_devolucion: Optional[int] = None
    combustible_entrega: int
    combustible_devolucion: Optional[int] = None
    control_previo: dict[str, bool]
    estado_entrega: Optional[str] = None
    estado_devolucion: Optional[str] = None
    demorado: bool = False
