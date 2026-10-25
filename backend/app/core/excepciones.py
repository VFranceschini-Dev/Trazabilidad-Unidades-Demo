"""Errores de dominio con formato comun {codigo, mensaje, detalle}."""

from __future__ import annotations

from typing import Any


class ErrorDominio(Exception):
    """Error de negocio; las rutas lo traducen a la respuesta HTTP correspondiente."""

    def __init__(self, codigo: str, mensaje: str, detalle: Any = None, estado_http: int = 400) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.detalle = detalle
        self.estado_http = estado_http


class TransicionInvalida(ErrorDominio):
    def __init__(self, estado_actual: str, permitidas: list[str], motivo: str) -> None:
        super().__init__(
            codigo="TRANSICION_INVALIDA",
            mensaje=motivo,
            detalle={"estado_actual": estado_actual, "acciones_permitidas": permitidas},
            estado_http=409,
        )


class NoEncontrado(ErrorDominio):
    def __init__(self, recurso: str) -> None:
        super().__init__(codigo="NO_ENCONTRADO", mensaje=f"No existe {recurso}.", estado_http=404)


class SinPermiso(ErrorDominio):
    def __init__(self, mensaje: str = "El rol no tiene permiso para esta operacion.") -> None:
        super().__init__(codigo="SIN_PERMISO", mensaje=mensaje, estado_http=403)
