"""Tabla usuario (Tabla 24 del TFG) con los seis perfiles de la Tabla 30."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.tablas_generales.models import ahora_utc


class Rol(str, Enum):
    ADMIN = "ADMIN"                       # Administrador del sistema
    RESP_MKT_VENTAS = "RESP_MKT_VENTAS"   # Responsable de Marketing y Ventas
    ASESOR = "ASESOR"                     # Asesor comercial
    RESP_POSVENTA = "RESP_POSVENTA"      # Responsable de Posventa
    ADMINISTRACION = "ADMINISTRACION"     # Administración (actas de infracción)
    GERENCIA = "GERENCIA"                 # Gerencia (solo consulta)
    TECNICO = "TECNICO"                   # Usuario técnico (n8n, API key)


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    legajo: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    correo: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    # VARCHAR en la base; SAEnum convierte al leer para que usuario.rol sea Rol y no str
    rol: Mapped[Rol] = mapped_column(SAEnum(Rol, native_enum=False, length=30), default=Rol.ASESOR)
    id_sucursal: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    hash_clave: Mapped[str] = mapped_column(String(120))
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    debe_cambiar_clave: Mapped[bool] = mapped_column(Boolean, default=False)
    clave_temporal_hasta: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ultima_actividad: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    # Cuenta de demostracion: solo ingresa con ENTORNO=demo (ver docs/decisiones.md)
    es_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Va en el token: al restablecer la clave se incrementa y se cierran todas las sesiones
    version_sesion: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    clave_cambiada_en: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class TokenRecuperacion(Base):
    """Enlace de recuperacion de un solo uso: solo se guarda el hash del codigo."""

    __tablename__ = "token_recuperacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    hash_token: Mapped[str] = mapped_column(String(64), unique=True)
    vence_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_en: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
