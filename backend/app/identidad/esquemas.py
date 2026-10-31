"""Esquemas Pydantic v2 de identidad."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.identidad.models import Rol


class IngresarIn(BaseModel):
    correo: str = Field(min_length=3)
    clave: str = Field(min_length=1)


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    legajo: str
    correo: str
    nombre: str
    rol: Rol
    id_sucursal: Optional[str] = None
    activo: bool


class IngresarOut(BaseModel):
    token: str
    debe_cambiar_clave: bool
    usuario: UsuarioOut


class CambiarClaveIn(BaseModel):
    clave_actual: Optional[str] = None
    clave_nueva: str = Field(min_length=10)


class RecuperarIn(BaseModel):
    correo: str


class RestablecerIn(BaseModel):
    token: str = Field(min_length=1)
    clave_nueva: str = Field(min_length=10)


class YoOut(BaseModel):
    usuario: UsuarioOut
    sucursal_nombre: Optional[str] = None
    menu_permitido: list[str] = []
