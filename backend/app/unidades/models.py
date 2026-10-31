"""Tablas unidad_demo, evento_unidad y asignacion (Tablas 26-28 del TFG)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CHAR,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.tablas_generales.models import ahora_utc


class Circuito(str, Enum):
    COMERCIAL = "COMERCIAL"
    POSVENTA = "POSVENTA"


class UnidadDemo(Base):
    __tablename__ = "unidad_demo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vin: Mapped[str] = mapped_column(CHAR(17), unique=True)
    patente: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    modelo: Mapped[str] = mapped_column(String(60))
    version: Mapped[str] = mapped_column(String(80))
    # VARCHAR en la base; SAEnum convierte al leer para que unidad.circuito sea Circuito y no str
    circuito: Mapped[Circuito] = mapped_column(SAEnum(Circuito, native_enum=False, length=20), index=True)
    estado_actual: Mapped[str] = mapped_column(String(20), default="DISPONIBLE", index=True)
    id_sucursal: Mapped[str] = mapped_column(String(10), ForeignKey("sucursal.codigo"))
    km_actual: Mapped[int] = mapped_column(Integer, default=0)
    km_proximo_service: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fecha_alta: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    fecha_limite_rotacion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    id_dispositivo_traccar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class EventoUnidad(Base):
    """Historial inmutable: solo SELECT e INSERT para el rol de aplicación;
    un trigger BEFORE UPDATE OR DELETE rechaza cualquier modificación."""

    __tablename__ = "evento_unidad"
    

    id_evento: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_unidad: Mapped[int] = mapped_column(Integer, ForeignKey("unidad_demo.id"), index=True)
    tipo_evento: Mapped[str] = mapped_column(String(30))
    estado_anterior: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    estado_nuevo: Mapped[str] = mapped_column(String(20))
    fecha_hora: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    id_usuario: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("usuario.id"), nullable=True)
    origen: Mapped[str] = mapped_column(String(10))            # API | N8N | TRACCAR | DMS
    carga_diferida: Mapped[bool] = mapped_column(Boolean, default=False)
    datos: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PosicionCache(Base):
    """Ultima posicion conocida, para responder cuando Traccar no esta disponible (HU-11.3)."""

    __tablename__ = "posicion_cache"

    id_unidad: Mapped[int] = mapped_column(Integer, ForeignKey("unidad_demo.id"), primary_key=True)
    latitud: Mapped[float] = mapped_column(Float)
    longitud: Mapped[float] = mapped_column(Float)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Asignacion(Base):
    """Asignacion vigente: `fecha_hasta` nula mientras esta abierta.
    El indice unico parcial (creado en la migracion) garantiza una sola abierta por unidad."""

    __tablename__ = "asignacion"
    __table_args__ = (Index("ix_asignacion_unidad_desde", "id_unidad", "fecha_desde"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_unidad: Mapped[int] = mapped_column(Integer, ForeignKey("unidad_demo.id"), index=True)
    id_responsable: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id"))
    id_sucursal: Mapped[str] = mapped_column(String(10), ForeignKey("sucursal.codigo"))
    fecha_desde: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    fecha_hasta: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    id_evento_apertura: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
