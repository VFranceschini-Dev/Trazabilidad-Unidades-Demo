"""P2. Tablero del parque demo (HU-12 y HU-13). Réplica de P2_tablero.png."""

from __future__ import annotations

import sys
from datetime import datetime
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import SesionVencida, detalle_error, get, post  # noqa: E402
from componentes.ui import (  # noqa: E402
    COLOR_ALERTA,
    FAVICON_RUTA,
    NOMBRE_ALERTA,
    P2,
    P3,
    ZONA,
    chip_estado,
    inyectar_estilos,
    logo_lateral,
    menu_lateral,
    regla,
    rol_actual,
    titulo_seccion,
)

st.set_page_config(page_title="Tablero — Parque Demo", layout="wide", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")

try:
    menu_lateral(P2)
    st.markdown('<div class="titulo-pagina">Tablero del parque demo</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="subtitulo">Estado actualizado al {datetime.now(ZONA):%d/%m/%Y %H:%M}</div>', unsafe_allow_html=True
    )

    _, sucursales = get("/sucursales")
    nombres = {s["codigo"]: s["nombre"] for s in sucursales}
    col_sucursal, col_circuito = st.columns(2)
    id_sucursal = col_sucursal.selectbox(
        "Sucursal", ["", *nombres], format_func=lambda c: nombres.get(c, "Todas las sucursales"), key="p2_sucursal"
    )
    circuito = col_circuito.selectbox(
        "Circuito", ["", "COMERCIAL", "POSVENTA"],
        format_func=lambda c: {"": "Todos los circuitos", "COMERCIAL": "Comercial", "POSVENTA": "Posventa"}[c],
        key="p2_circuito",
    )
    params = {k: v for k, v in (("id_sucursal", id_sucursal), ("circuito", circuito)) if v}
    estado, datos = get("/tablero/indicadores", params or None)
    if estado != 200:
        st.error(detalle_error(datos))
        st.stop()

    tarjetas = (
        (datos["activas"], "Unidades demo activas", "#1B2A41"),
        (datos["disponibles"], "Disponibles", "#1E7B34"),
        (datos["asignadas"] + datos["en_uso"], "Asignadas / en uso", "#1F3864"),
        (datos["en_prestamo"], "En préstamo", "#5B2D9E"),
        (datos["en_service"], "En service", "#4A5568"),
        (datos["en_venta"], "En venta", "#B42318"),
        (datos["multas_pendientes"], "Multas pendientes", "#B42318"),
    )
    for columna, (valor, rotulo, color) in zip(st.columns(len(tarjetas)), tarjetas):
        columna.markdown(
            f'<div class="tarjeta indicador"><div class="numero" style="color:{color}">{valor}</div>'
            f'<div class="etiqueta-unidad">{escape(rotulo)}</div></div>',
            unsafe_allow_html=True,
        )

    with st.container(border=True):
        titulo_seccion("Unidades")
        filas = "".join(
            f"<tr><td>{escape(f['patente'])}</td><td>{escape(f['modelo'])}</td><td>{escape(f['sucursal'] or '—')}</td>"
            f"<td>{f['circuito'].capitalize()}</td><td>{chip_estado(f['estado'])}</td><td>{escape(f['responsable'] or '—')}</td></tr>"
            for f in datos["filas"]
        )
        st.markdown(
            '<table class="tabla-simple"><thead><tr><th>Patente</th><th>Modelo</th><th>Sucursal</th><th>Circuito</th>'
            f"<th>Estado</th><th>Responsable actual</th></tr></thead><tbody>{filas}</tbody></table>",
            unsafe_allow_html=True,
        )
        if datos["filas"]:
            por_id = {f["id"]: f for f in datos["filas"]}
            col_unidad, col_boton = st.columns([3, 1], vertical_alignment="bottom")
            elegida = col_unidad.selectbox(
                "Abrir ficha de", list(por_id), format_func=lambda i: f"{por_id[i]['patente']} · {por_id[i]['modelo']}", key="p2_unidad"
            )
            if col_boton.button("Abrir ficha", use_container_width=True):
                st.session_state["unidad_id"] = elegida
                st.switch_page(P3)
        else:
            st.caption("No hay unidades con estos filtros.")

    with st.container(border=True):
        titulo_seccion("Alertas abiertas")
        _, respuesta = get("/alertas")
        abiertas = [a for a in respuesta["alertas"] if a["estado"] == "ABIERTA"]
        if id_sucursal:
            abiertas = [a for a in abiertas if a["id_sucursal"] == id_sucursal]
        if circuito:
            abiertas = [a for a in abiertas if a["circuito"] == circuito]
        for alerta in abiertas:
            regla(f"{NOMBRE_ALERTA.get(alerta['tipo_alerta'], alerta['tipo_alerta'])} · {alerta['mensaje']}", COLOR_ALERTA.get(alerta["tipo_alerta"], "info"))
        if not abiertas:
            st.caption("No hay alertas abiertas.")
        if rol_actual() == "ADMIN" and st.button("Ejecutar control ahora"):
            codigo, cuerpo = post("/alertas/ejecutar-control")
            if codigo == 200:
                st.rerun()
            st.error(detalle_error(cuerpo))
except SesionVencida:
    st.switch_page("paginas/p1_inicio_sesion.py")
