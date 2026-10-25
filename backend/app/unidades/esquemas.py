"""Esquemas Pydantic v2 de entrada y salida del núcleo de trazabilidad."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.estados import EstadoUnidad, TipoEvento
from app.unidades.models import Circuito


class AltaUnidadIn(BaseModel):
    vin: str = Field(min_length=17, max_length=17, description="17 caracteres")
    patente: str = Field(min_length=5, max_length=10)
    modelo: str
    version: str
    circuito: Circuito
    id_sucursal: str
    km_inicial: int = Field(ge=0)
    fecha_hora: Optional[datetime] = None  # carga diferida

    @field_validator("vin")
    @classmethod
    def _vin_mayusculas(cls, v: str) -> str:
        return v.upper()


class UnidadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vin: str
    patente: str
    modelo: str
    version: str
    circuito: Circuito
    estado_actual: EstadoUnidad
    id_sucursal: str
    sucursal_nombre: Optional[str] = None
    km_actual: int
    km_proximo_service: Optional[int] = None
    fecha_alta: datetime
    fecha_limite_rotacion: Optional[datetime] = None
    id_dispositivo_traccar: Optional[int] = None


class ResponsableOut(BaseModel):
    tipo: str
    identificador: int
    nombre: str
    evento_id: int
    desde: datetime
    hasta: Optional[datetime] = None


class FichaUnidadOut(BaseModel):
    unidad: UnidadOut
    responsable_actual: Optional[ResponsableOut] = None
    acciones_permitidas: list[str] = []


class EventoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_evento: int
    tipo_evento: TipoEvento
    estado_anterior: Optional[str] = None
    estado_nuevo: str
    fecha_hora: datetime
    id_usuario: Optional[int] = None
    usuario_nombre: Optional[str] = None
    origen: str
    carga_diferida: bool
    datos: dict[str, Any] = {}


class HistorialOut(BaseModel):
    id_unidad: int
    eventos: list[EventoOut]


class AsignacionIn(BaseModel):
    id_responsable: int
    id_sucursal: str
    fecha_hora: Optional[datetime] = None


class LiberacionIn(BaseModel):
    fecha_hora: Optional[datetime] = None
    motivo: Optional[str] = None


class ServiceIngresoIn(BaseModel):
    fecha_hora: Optional[datetime] = None
    observaciones: Optional[str] = None


class ServiceFinIn(BaseModel):
    km: int = Field(ge=0)
    proximo_service_km: Optional[int] = Field(default=None, ge=0)
    fecha_hora: Optional[datetime] = None


class MovimientoOut(BaseModel):
    unidad: UnidadOut
    evento: EventoOut
