"""Modelos SQLAlchemy de las tablas generales (diccionario de datos del TFG)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Sucursal(Base):
    __tablename__ = "sucursal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(100))
    domicilio: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class Cliente(Base):
    __tablename__ = "cliente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Opcional: el prospecto de un test drive solo deja nombre y telefono
    documento: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True, nullable=True)
    nombre: Mapped[str] = mapped_column(String(120))
    contacto: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)


class Alerta(Base):
    """Alertas (Tabla 29 del TFG). DEVOLUCION_CON_DANOS se suma a los tipos del diccionario
    (docs/decisiones.md); la pantalla y los controles diarios llegan en la etapa 4."""

    __tablename__ = "alerta"

    id_alerta: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo_alerta: Mapped[str] = mapped_column(String(30))
    id_unidad: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("unidad_demo.id"), nullable=True)
    id_infraccion: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("infraccion.id_infraccion"), nullable=True)
    mensaje: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(10), default="ABIERTA", server_default="ABIERTA")
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    id_usuario_cierre: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("usuario.id"), nullable=True)
    fecha_cierre: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accion_realizada: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Parametro(Base):
    """Parametros de negocio. `circuito` y `id_sucursal` opcionales: gana la regla
    mas especifica (sucursal+circuito > circuito > global)."""

    __tablename__ = "parametro"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clave: Mapped[str] = mapped_column(String(60), index=True)
    valor: Mapped[str] = mapped_column(String(200))
    circuito: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    id_sucursal: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_usuario: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    accion: Mapped[str] = mapped_column(String(80))       # LOGIN_OK, LOGIN_FALLIDO, ALTA_UNIDAD, ...
    recurso: Mapped[str] = mapped_column(String(160))     # ej. "auth", "unidad:12"
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    resultado: Mapped[str] = mapped_column(String(20))    # EXITO | FRACASO


def buscar_parametro(
    sesion: Session, clave: str, *, circuito: Optional[str] = None, id_sucursal: Optional[int] = None
) -> Optional[Parametro]:
    """Regla mas especifica primero: sucursal+circuito, circuito, global."""
    consultas: list[list[object]] = []
    if circuito is not None and id_sucursal is not None:
        consultas.append([Parametro.clave == clave, Parametro.circuito == circuito, Parametro.id_sucursal == id_sucursal])
    if circuito is not None:
        consultas.append([Parametro.clave == clave, Parametro.circuito == circuito, Parametro.id_sucursal.is_(None)])
    if id_sucursal is not None:
        consultas.append([Parametro.clave == clave, Parametro.circuito.is_(None), Parametro.id_sucursal == id_sucursal])
    consultas.append([Parametro.clave == clave, Parametro.circuito.is_(None), Parametro.id_sucursal.is_(None)])
    for filtro in consultas:
        fila = sesion.scalar(select(Parametro).where(*filtro))
        if fila is not None:
            return fila
    return None


def valor_parametro(
    sesion: Session,
    clave: str,
    valor_por_defecto: str,
    *,
    circuito: Optional[str] = None,
    id_sucursal: Optional[int] = None,
) -> str:
    fila = buscar_parametro(sesion, clave, circuito=circuito, id_sucursal=id_sucursal)
    return fila.valor if fila is not None else valor_por_defecto
