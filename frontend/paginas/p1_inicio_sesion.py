"""P1. Inicio de sesión (HU-01). Réplica de referencia_pantallas/P1_inicio_sesion.png."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import detalle_error, post  # noqa: E402
from componentes.ui import FAVICON_RUTA, inyectar_estilos, logo_ingreso  # noqa: E402

st.set_page_config(page_title="Ingreso — Parque Demo", layout="centered", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_ingreso()

if st.session_state.get("token"):
    st.switch_page("paginas/p3_ficha_historial.py")

st.markdown('<div class="titulo-pagina">Parque Demo</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitulo">Plataforma de gestión y trazabilidad de unidades demo</div>', unsafe_allow_html=True)

aviso = st.session_state.pop("aviso_sesion", None)
if aviso:
    st.warning(aviso)

with st.form("formulario_ingreso"):
    correo = st.text_input("Correo corporativo", placeholder="asesor@demo.local")
    clave = st.text_input("Contraseña", type="password", placeholder="••••••••••")
    enviado = st.form_submit_button("Ingresar", use_container_width=True, type="primary")

if enviado:
    if not correo or not clave:
        st.error("Complete correo y contraseña.")
    else:
        estado, cuerpo = post("/auth/ingresar", {"correo": correo, "clave": clave})
        if estado == 200 and isinstance(cuerpo, dict) and "token" in cuerpo:
            st.session_state["token"] = cuerpo["token"]
            st.session_state["usuario"] = cuerpo["usuario"]
            if cuerpo.get("debe_cambiar_clave"):
                st.switch_page("paginas/p2_cambio_clave.py")
            elif cuerpo["usuario"]["rol"] == "ASESOR":
                st.switch_page("paginas/p7_registro_uso.py")
            else:
                st.switch_page("paginas/p3_ficha_historial.py")
        elif estado == 423:
            st.error(detalle_error(cuerpo))
        elif estado == 401:
            st.error(detalle_error(cuerpo))
        else:
            st.error(detalle_error(cuerpo))

st.markdown("---")
st.caption("Recuperar contraseña · Datos ficticios de demostración (Ley 25.326)")
recuperar = st.button("¿Olvidó su contraseña?", use_container_width=False)
if recuperar:
    with st.form("recuperar"):
        correo_rec = st.text_input("Correo corporativo")
        if st.form_submit_button("Enviar solicitud"):
            _, cuerpo = post("/auth/recuperar", {"correo": correo_rec})
            st.info("Si el correo existe, se emitió una contraseña temporal válida 48 h.")
