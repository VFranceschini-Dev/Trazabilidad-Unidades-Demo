"""Tabla uso_comercial (Tabla 26 del TFG)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TipoUso(str, Enum):
    TEST_DRIVE = "TEST_DRIVE"
    GIRA = "GIRA"
    GUARDIA = "GUARDIA"
    EVENTO = "EVENTO"


class UsoComercial(Base):
    """Salida y regreso de una unidad; `fecha_hora_regreso` nula mientras esta en uso."""

    __tablename__ = "uso_comercial"

    id_uso: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_unidad: Mapped[int] = mapped_column(Integer, ForeignKey("unidad_demo.id"))
    tipo_uso: Mapped[str] = mapped_column(String(15))
    id_usuario: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id"))
    id_cliente: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cliente.id"), nullable=True)
    fecha_hora_salida: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_hora_regreso: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    km_salida: Mapped[int] = mapped_column(Integer)
    km_regreso: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    observaciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
