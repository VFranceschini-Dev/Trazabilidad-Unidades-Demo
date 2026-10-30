"""Componentes visuales compartidos: estilos, menú lateral, chips, reglas y tablas."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st

from cliente_api import get, post

ESTILOS_RUTA = Path(__file__).resolve().parent.parent / "estilos.css"
RECURSOS = Path(__file__).resolve().parent.parent / "recursos"
# Logo de la concesionaria (último cuadro de logo-donnet-animado.gif de donnet.com.ar,
# con fondo transparente) y favicon con la "D" del logo.
LOGO_RUTA = str(RECURSOS / "logo-donnet.png")
FAVICON_RUTA = str(RECURSOS / "favicon-donnet.png")

ZONA = ZoneInfo("America/Argentina/Buenos_Aires")

P3 = "paginas/p3_ficha_historial.py"
P4 = "paginas/p4_asignacion.py"
P8 = "paginas/p8_alta_unidad.py"

# Opciones construidas y las entradas de /yo (menu_permitido) que las habilitan.
# Las demás entradas de ese menú pertenecen a etapas siguientes y todavía no se muestran.
MENU = (
    ("Unidades demo", P3, {"Unidades", "Mis unidades", "Service"}),
    ("Asignación", P4, {"Asignaciones"}),
    ("Alta de unidad", P8, {"Altas"}),
)

ROLES = {
    "ADMIN": "Administrador del sistema",
    "RESP_MKT_VENTAS": "Resp. Marketing y Ventas",
    "ASESOR": "Asesor comercial",
    "RESP_POSVENTA": "Resp. Posventa",
    "TECNICO_TALLER": "Técnico de Taller",
    "RESP_USADOS": "Resp. División Usados",
}

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
    """Logo arriba de la barra lateral."""
    st.logo(LOGO_RUTA)


def rol_actual() -> str:
    return str(st.session_state.get("usuario", {}).get("rol", ""))


def menu_lateral(pagina_actual: str) -> None:
    """Menú común de las pantallas internas, según el rol que informa la API en /yo."""
    if "yo" not in st.session_state:
        estado, cuerpo = get("/yo")
        st.session_state["yo"] = cuerpo if estado == 200 else {}
    yo = st.session_state["yo"]
    permitido = set(yo.get("menu_permitido", []))
    usuario = st.session_state.get("usuario", {})

    with st.sidebar:
        st.markdown('<div class="sb-marca">Parque Demo</div>', unsafe_allow_html=True)
        st.markdown('<div class="sb-sub">Trazabilidad de unidades demo</div>', unsafe_allow_html=True)
        for etiqueta, pagina, entradas in MENU:
            if not permitido & entradas:
                continue
            actual = pagina == pagina_actual
            if st.button(etiqueta, use_container_width=True, type="primary" if actual else "secondary") and not actual:
                st.switch_page(pagina)
        st.divider()
        st.markdown(
            f'<div class="sb-usuario">Usuario: {escape(str(usuario.get("nombre", "")))}<br>'
            f'{escape(ROLES.get(rol_actual(), rol_actual()))}<br>'
            f'Sucursal: {escape(str(yo.get("sucursal_nombre") or "—"))}</div>',
            unsafe_allow_html=True,
        )
        if st.button("Cerrar sesión", use_container_width=True):
            post("/auth/salir")
            st.session_state.clear()
            st.switch_page("paginas/p1_inicio_sesion.py")


def descripcion_unidad(u: dict[str, Any]) -> str:
    km = f"{u['km_actual']:,}".replace(",", ".")
    return f"{u['patente']} · {u['modelo']} · {u.get('sucursal_nombre') or u['id_sucursal']} · {km} km"


def selector_unidad(unidades: list[dict[str, Any]], etiqueta: str, clave: str) -> dict[str, Any]:
    """Selector por patente y modelo; la unidad elegida se conserva entre pantallas."""
    por_id = {u["id"]: u for u in unidades}
    ids = list(por_id)
    guardada = st.session_state.get("unidad_id")
    indice = ids.index(guardada) if guardada in por_id else 0
    elegida = st.selectbox(etiqueta, ids, index=indice, key=clave, format_func=lambda i: descripcion_unidad(por_id[i]))
    st.session_state["unidad_id"] = elegida
    return por_id[elegida]


def titulo_seccion(texto: str) -> None:
    st.markdown(f'<div class="titulo-seccion">{escape(texto)}</div>', unsafe_allow_html=True)


def regla(texto: str, tipo: str = "ok") -> None:
    """Regla verificada con barra lateral: ok (verde), aviso (ámbar), info (azul) o error (rojo)."""
    st.markdown(f'<div class="regla regla-{tipo}">{escape(texto)}</div>', unsafe_allow_html=True)


def tabla(columnas: list[str], filas: list[list[str]]) -> None:
    encabezado = "".join(f"<th>{escape(c)}</th>" for c in columnas)
    cuerpo = "".join("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in fila) + "</tr>" for fila in filas)
    st.markdown(
        f'<table class="tabla-simple"><thead><tr>{encabezado}</tr></thead><tbody>{cuerpo}</tbody></table>',
        unsafe_allow_html=True,
    )


def chip_estado(estado: str) -> str:
    etiqueta, _color = CHIPS.get(estado, (estado, ""))
    return f'<span class="chip chip-{estado}">{etiqueta}</span>'


def _a_local(valor: str) -> datetime:
    dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZONA)


def mostrar_fecha(valor: str | None) -> str:
    """Convierte un ISO UTC a America/Argentina/Buenos_Aires para mostrar."""
    if not valor:
        return "—"
    try:
        return _a_local(valor).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return valor


def mostrar_dia(valor: str | None) -> str:
    """Igual que mostrar_fecha, sin la hora."""
    if not valor:
        return "—"
    try:
        return _a_local(valor).strftime("%d/%m/%Y")
    except ValueError:
        return valor


def hoy() -> str:
    return datetime.now(ZONA).strftime("%d/%m/%Y")
