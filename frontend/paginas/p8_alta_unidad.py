"""P8. Alta de unidad demo (HU-02). Réplica de P8_alta_unidad.png."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import SesionVencida, detalle_error, post  # noqa: E402
from componentes.ui import FAVICON_RUTA, inyectar_estilos, logo_lateral  # noqa: E402

st.set_page_config(page_title="Alta de unidad — Parque Demo", layout="wide", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")

st.markdown('<div class="titulo-pagina">Alta de unidad demo</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitulo">Registre una nueva unidad con sus datos identificatorios; comienza su historial en estado DISPONIBLE.</div>', unsafe_allow_html=True)

sucursales = [("SC01", "Casa Central"), ("SC02", "Formosa"), ("SC03", "Sáenz Peña"), ("SC04", "División Usados")]

with st.form("formulario_alta"):
    col1, col2 = st.columns(2)
    with col1:
        vin = st.text_input("VIN (17 caracteres)", max_chars=17)
        patente = st.text_input("Patente", max_chars=10)
        modelo = st.text_input("Modelo", value="Ranger")
        version = st.text_input("Versión", value="XLS 4x4 CD 3.2")
    with col2:
        circuito = st.radio("Circuito", ["COMERCIAL", "POSVENTA"], horizontal=True)
        suc = st.selectbox("Sucursal", [f"{c} — {n}" for c, n in sucursales])
        km = st.number_input("Kilometraje inicial", min_value=0, value=0, step=10)
        diferida = st.checkbox("Carga diferida (fecha/hora del movimiento real)")
        fecha_txt = st.text_input("Fecha y hora (ISO 8601, solo si es diferida)", disabled=not diferida)

    confirmar = st.form_submit_button("Confirmar alta", type="primary", use_container_width=True)

if confirmar:
    faltantes = []
    if len(vin) != 17:
        faltantes.append("VIN de 17 caracteres")
    if not patente:
        faltantes.append("patente")
    if not modelo or not version:
        faltantes.append("modelo/versión")
    if km is None:
        faltantes.append("kilometraje inicial")
    if faltantes:
        st.error("Campos obligatorios: " + ", ".join(faltantes) + ".")
    else:
        cuerpo = {
            "vin": vin.upper(),
            "patente": patente.upper(),
            "modelo": modelo,
            "version": version,
            "circuito": circuito,
            "id_sucursal": suc.split(" — ")[0],
            "km_inicial": int(km),
        }
        if diferida and fecha_txt:
            cuerpo["fecha_hora"] = fecha_txt
        try:
            estado, resultado = post("/unidades", cuerpo)
            if estado == 201:
                st.success(f"Unidad {resultado['unidad']['patente']} dada de alta en estado DISPONIBLE.")
                st.query_params["unidad"] = str(resultado["unidad"]["id"])
                st.switch_page("paginas/p3_ficha_historial.py")
            else:
                st.error(detalle_error(resultado))
        except SesionVencida:
            st.switch_page("paginas/p1_inicio_sesion.py")
