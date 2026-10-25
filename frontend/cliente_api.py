"""Cliente HTTP de la API v1. Maneja el token en st.session_state y redirige al
ingreso cuando la sesion vence (401)."""

from __future__ import annotations

import os
from typing import Any, Optional

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")
TIMEOUT = 15


class SesionVencida(Exception):
    pass


def _token() -> Optional[str]:
    return st.session_state.get("token")


def _redirigir_login(mensaje: str = "La sesión venció. Ingrese nuevamente.") -> None:
    st.session_state.pop("token", None)
    st.session_state.pop("usuario", None)
    st.session_state["aviso_sesion"] = mensaje
    st.switch_page("paginas/p1_inicio_sesion.py")


def request(
    metodo: str,
    ruta: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Devuelve (status, cuerpo_json); lanza SesionVencida en 401 para redirigir."""
    cabeceras: dict[str, str] = {}
    if _token():
        cabeceras["Authorization"] = f"Bearer {_token()}"
    try:
        respuesta = requests.request(
            metodo, f"{API_BASE_URL}{ruta}", json=json_body, params=params, headers=cabeceras, timeout=TIMEOUT
        )
    except requests.ConnectionError:
        st.error("No se puede conectar con la API. Verifique que `make demo` esté corriendo.")
        raise SesionVencida("sin conexion") from None
    if respuesta.status_code == 401 and ruta not in ("/auth/ingresar", "/auth/recuperar"):
        _redirigir_login()
        raise SesionVencida(respuesta.text)
    try:
        return respuesta.status_code, respuesta.json()
    except ValueError:
        return respuesta.status_code, respuesta.text


def get(ruta: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    return request("GET", ruta, params=params)


def post(ruta: str, cuerpo: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    return request("POST", ruta, json_body=cuerpo, params=params)


def detalle_error(cuerpo: Any) -> str:
    if isinstance(cuerpo, dict):
        detalle = cuerpo.get("detalle")
        mensaje = cuerpo.get("mensaje", "Error inesperado.")
        if isinstance(detalle, dict) and detalle.get("campos"):
            mensaje += " Campos: " + ", ".join(detalle["campos"])
        elif isinstance(detalle, list):
            mensaje += " " + "; ".join(str(d) for d in detalle)
        elif isinstance(detalle, str):
            mensaje += f" {detalle}"
        return mensaje
    return str(cuerpo)
