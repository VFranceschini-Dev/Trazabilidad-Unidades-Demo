"""P9. Alertas de gestión (HU-13). Réplica de P9_alertas.png."""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import SesionVencida, detalle_error, get, post  # noqa: E402
from componentes.ui import (  # noqa: E402
    COLOR_ALERTA,
    FAVICON_RUTA,
    NOMBRE_ALERTA,
    P3,
    P5,
    P6,
    P9,
    inyectar_estilos,
    logo_lateral,
    menu_lateral,
    mostrar_fecha,
    rol_actual,
    tabla,
    titulo_seccion,
)

st.set_page_config(page_title="Alertas — Parque Demo", layout="wide", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")


def destino(alerta: dict[str, Any]) -> tuple[str, str] | None:
    """Pantalla donde se resuelve la alerta, si el perfil puede entrar."""
    rol = rol_actual()
    tipo = alerta["tipo_alerta"]
    if tipo in ("ACTA_A_VALIDAR", "MULTA_POR_VENCER", "SIN_RESPONSABLE") and alerta["id_infraccion"] and rol == "ADMINISTRACION":
        return ("Ver acta", P6)
    if tipo in ("PRESTAMO_DEMORADO", "DEVOLUCION_CON_DANOS") and rol == "RESP_POSVENTA":
        return ("Ver préstamos", P5)
    if alerta["id_unidad"]:
        return ("Ver ficha", P3)
    return None


try:
    menu_lateral(P9)
    _, datos = get("/alertas")
    alertas = datos["alertas"]
    abiertas_total = sum(1 for a in alertas if a["estado"] == "ABIERTA")
    control = mostrar_fecha(datos["ultimo_control"]) if datos["ultimo_control"] else "todavía no ejecutado"

    st.markdown('<div class="titulo-pagina">Alertas de gestión</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="subtitulo">Control diario: {control} · {abiertas_total} alertas abiertas</div>', unsafe_allow_html=True
    )
    if rol_actual() == "ADMIN" and st.button("Ejecutar control ahora"):
        codigo, cuerpo = post("/alertas/ejecutar-control")
        if codigo == 200:
            st.rerun()
        st.error(detalle_error(cuerpo))

    _, sucursales = get("/sucursales")
    nombres = {s["codigo"]: s["nombre"] for s in sucursales}
    tipos = sorted({a["tipo_alerta"] for a in alertas})
    col_tipo, col_sucursal = st.columns(2)
    tipo = col_tipo.selectbox("Tipo", ["", *tipos], format_func=lambda t: NOMBRE_ALERTA.get(t, t) if t else "Todas", key="p9_tipo")
    sucursal = col_sucursal.selectbox(
        "Sucursal", ["", *nombres], format_func=lambda c: nombres.get(c, "Todas las sucursales"), key="p9_sucursal"
    )
    visibles = [
        a for a in alertas if (not tipo or a["tipo_alerta"] == tipo) and (not sucursal or a["id_sucursal"] == sucursal)
    ]
    abiertas = [a for a in visibles if a["estado"] == "ABIERTA"]
    cerradas = [a for a in visibles if a["estado"] == "CERRADA"]

    with st.container(border=True):
        titulo_seccion("Alertas abiertas")
        if not abiertas:
            st.caption("No hay alertas abiertas.")
        for alerta in abiertas:
            col_chip, col_detalle, col_fecha, col_accion = st.columns([2, 5, 1.4, 1.4], vertical_alignment="center")
            nombre = NOMBRE_ALERTA.get(alerta["tipo_alerta"], alerta["tipo_alerta"])
            col_chip.markdown(
                f'<span class="chip chip-alerta-{COLOR_ALERTA.get(alerta["tipo_alerta"], "info")}">{escape(nombre.upper())}</span>',
                unsafe_allow_html=True,
            )
            col_detalle.write(alerta["mensaje"])
            col_fecha.caption(mostrar_fecha(alerta["fecha_creacion"]))
            enlace = destino(alerta)
            if enlace and col_accion.button(enlace[0], key=f"ir_{alerta['id_alerta']}", use_container_width=True):
                if alerta["id_unidad"]:
                    st.session_state["unidad_id"] = alerta["id_unidad"]
                if enlace[1] == P6:
                    st.session_state["p6_acta"] = alerta["id_infraccion"]
                    st.session_state["p6_filtro_siguiente"] = "TODAS"
                st.switch_page(enlace[1])

    propias = [a for a in abiertas if a["puede_cerrar"]]
    if propias:
        with st.container(border=True):
            titulo_seccion("Cerrar alerta")
            por_id = {a["id_alerta"]: a for a in propias}
            elegida = st.selectbox(
                "Alerta", list(por_id),
                format_func=lambda i: f"{NOMBRE_ALERTA.get(por_id[i]['tipo_alerta'], por_id[i]['tipo_alerta'])} · {por_id[i]['mensaje'][:80]}",
                key="p9_cerrar",
            )
            accion = st.text_input("Acción realizada", key=f"p9_accion_{elegida}").strip()
            if st.button("Cerrar alerta", type="primary", disabled=not accion):
                codigo, cuerpo = post(f"/alertas/{elegida}/cerrar", {"accion": accion})
                if codigo == 200:
                    st.rerun()
                st.error(detalle_error(cuerpo))
            st.caption("Al cerrarla queda registrado quién la cerró y en qué fecha y hora.")

    with st.container(border=True):
        titulo_seccion("Cerradas recientemente")
        if cerradas:
            tabla(
                ["Tipo", "Detalle", "Acción", "Cerrada por", "Fecha"],
                [
                    [
                        NOMBRE_ALERTA.get(a["tipo_alerta"], a["tipo_alerta"]),
                        a["mensaje"],
                        a["accion_realizada"] or "—",
                        a["cerrada_por"] or "—",
                        mostrar_fecha(a["fecha_cierre"]),
                    ]
                    for a in cerradas[:10]
                ],
            )
        else:
            st.caption("No hay alertas cerradas.")
except SesionVencida:
    st.switch_page("paginas/p1_inicio_sesion.py")
