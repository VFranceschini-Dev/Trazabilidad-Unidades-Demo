"""Tabla infraccion (Tabla 28 del TFG)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.tablas_generales.models import ahora_utc


class EstadoActa(str, Enum):
    PENDIENTE_VALIDACION = "PENDIENTE_VALIDACION"
    VALIDADA = "VALIDADA"
    IMPUTADA = "IMPUTADA"
    PAGADA = "PAGADA"
    RECHAZADA = "RECHAZADA"


class Infraccion(Base):
    __tablename__ = "infraccion"

    id_infraccion: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nro_acta: Mapped[Optional[str]] = mapped_column(String(30), unique=True, nullable=True)
    patente_leida: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)
    fecha_hora_infraccion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    jurisdiccion: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    monto: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    fecha_vencimiento: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    archivo_pdf: Mapped[str] = mapped_column(String(255))
    confianza_ocr: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    confianza_campos: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoActa.PENDIENTE_VALIDACION.value)
    fecha_recepcion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    id_unidad: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("unidad_demo.id"), nullable=True)
    id_resp_usuario: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("usuario.id"), nullable=True)
    id_resp_cliente: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cliente.id"), nullable=True)
    id_usuario_validacion: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("usuario.id"), nullable=True)
    fecha_validacion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_rechazo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
