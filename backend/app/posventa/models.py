"""Tabla prestamo (Tabla 27 del TFG)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Prestamo(Base):
    """Entrega y devolucion; `fecha_hora_devolucion` nula mientras esta abierto."""

    __tablename__ = "prestamo"

    id_prestamo: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_unidad: Mapped[int] = mapped_column(Integer, ForeignKey("unidad_demo.id"))
    id_cliente: Mapped[int] = mapped_column(Integer, ForeignKey("cliente.id"))
    nro_orden_reparacion: Mapped[str] = mapped_column(String(20))
    id_usuario_entrega: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id"))
    id_usuario_recepcion: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("usuario.id"), nullable=True)
    fecha_hora_entrega: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fecha_hora_devolucion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    km_entrega: Mapped[int] = mapped_column(Integer)
    km_devolucion: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    combustible_entrega: Mapped[int] = mapped_column(SmallInteger)
    combustible_devolucion: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    control_previo: Mapped[dict[str, Any]] = mapped_column(JSONB)
    estado_entrega: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estado_devolucion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_devolucion_prevista: Mapped[date] = mapped_column(Date)
