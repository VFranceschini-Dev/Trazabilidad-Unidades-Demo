"""Componentes visuales compartidos: estilos, chips de estado y tarjetas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

ESTILOS_RUTA = Path(__file__).resolve().parent.parent / "estilos.css"
RECURSOS = Path(__file__).resolve().parent.parent / "recursos"
# Logo de la concesionaria (último cuadro de logo-donnet-animado.gif de donnet.com.ar,
# con fondo transparente) y favicon con la "D" del logo.
LOGO_RUTA = str(RECURSOS / "logo-donnet.png")
FAVICON_RUTA = str(RECURSOS / "favicon-donnet.png")

CHIPS = {
    "DISPONIBLE": ("DISPONIBLE", "verde"),
    "ASIGNADA": ("ASIGNADA", "azul"),
    "EN_USO": ("EN USO", "ámbar"),
    "EN_PRESTAMO": ("EN PRÉSTAMO", "violeta"),
    "EN_SERVICE": ("EN SERVICE", "gris"),
    "EN_VENTA": ("EN VENTA", "rojo"),
    "BAJA": ("BAJA", "oscuro"),
}


def inyectar_estilos() -> None:
    if ESTILOS_RUTA.exists():
        st.markdown(f"<style>{ESTILOS_RUTA.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def logo_ingreso() -> None:
    """Logo sobre el título en las pantallas de ingreso (P1 y P2)."""
    st.image(LOGO_RUTA, width=176)


def logo_lateral() -> None:
    """Logo arriba de la barra lateral (o arriba a la izquierda si la página no tiene barra)."""
    st.logo(LOGO_RUTA)


def chip_estado(estado: str) -> str:
    etiqueta, _color = CHIPS.get(estado, (estado, ""))
    return f'<span class="chip chip-{estado}">{etiqueta}</span>'


def mostrar_fecha(valor: str | None) -> str:
    """Convierte un ISO UTC a America/Argentina/Buenos_Aires para mostrar."""
    if not valor:
        return "—"
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return valor


def tarjeta(campos: list[tuple[str, str]]) -> None:
    columnas = st.columns(len(campos))
    for col, (etiqueta, valor) in zip(columnas, campos):
        with col:
            st.markdown(
                f'<div class="tarjeta"><div class="etiqueta">{etiqueta}</div><div class="valor">{valor}</div></div>',
                unsafe_allow_html=True,
            )
