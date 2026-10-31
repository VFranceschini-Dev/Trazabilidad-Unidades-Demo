"""Esquemas de entrada y salida del circuito de actas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import AwareDatetime, BaseModel, Field

from app.infracciones.models import EstadoActa


class ActaOut(BaseModel):
    id_infraccion: int
    nro_acta: Optional[str] = None
    patente_leida: Optional[str] = None
    fecha_hora_infraccion: Optional[datetime] = None
    jurisdiccion: Optional[str] = None
    monto: Optional[Decimal] = None
    fecha_vencimiento: Optional[date] = None
    confianza_ocr: Optional[Decimal] = None
    confianza_campos: dict[str, float] = {}
    estado: EstadoActa
    fecha_recepcion: datetime
    id_unidad: Optional[int] = None
    unidad_existente: bool = False
    responsable_nombre: Optional[str] = None
    validada_por: Optional[str] = None
    fecha_validacion: Optional[datetime] = None
    motivo_rechazo: Optional[str] = None
    umbral_confianza: int = 80


class LecturaIn(BaseModel):
    """Lo que envia n8n: el PDF que guardo y los datos que extrajo; cualquier dato puede faltar
    (HU-08.4: carga manual)."""

    archivo_pdf: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}\.pdf$")
    nro_acta: Optional[str] = Field(default=None, max_length=30)
    patente: Optional[str] = Field(default=None, max_length=12)
    fecha_hora: Optional[AwareDatetime] = None
    jurisdiccion: Optional[str] = Field(default=None, max_length=80)
    monto: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    vencimiento: Optional[date] = None
    confianza_campos: dict[str, float] = {}

    @property
    def confianza(self) -> Optional[float]:
        if not self.confianza_campos:
            return None
        return round(sum(self.confianza_campos.values()) / len(self.confianza_campos), 2)


class ValidarIn(BaseModel):
    nro_acta: str = Field(min_length=1, max_length=30)
    patente: str = Field(min_length=6, max_length=12)
    fecha_hora_infraccion: datetime
    jurisdiccion: str = Field(min_length=1, max_length=80)
    monto: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    fecha_vencimiento: date


class RechazarIn(BaseModel):
    motivo: str = Field(min_length=1)


class SugerenciaOut(BaseModel):
    tipo: str  # USUARIO | CLIENTE
    identificador: int
    nombre: str
    sin_responsable: bool = False
    evento_tipo: Optional[str] = None
    desde: Optional[datetime] = None
    hasta: Optional[datetime] = None
    posicion: str
