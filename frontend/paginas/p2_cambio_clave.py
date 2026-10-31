"""P2. Cambio de clave obligatorio en el primer ingreso (HU-01)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import detalle_error, post  # noqa: E402
from componentes.ui import FAVICON_RUTA, inyectar_estilos, logo_ingreso  # noqa: E402

st.set_page_config(page_title="Cambiar contraseña — Parque Demo", layout="centered", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_ingreso()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")

st.markdown('<div class="titulo-pagina">Primer ingreso: cambie su contraseña</div>', unsafe_allow_html=True)
st.info(
    "Mínimo 10 caracteres, con mayúscula, minúscula y número. "
    "No puede contener su nombre ni su correo.",
    icon="ℹ️",
)

with st.form("cambio_clave"):
    nueva = st.text_input("Nueva contraseña", type="password")
    confirmar = st.text_input("Repetir nueva contraseña", type="password")
    guardar = st.form_submit_button("Guardar y continuar", type="primary", use_container_width=True)

if guardar:
    if nueva != confirmar:
        st.error("Las contraseñas no coinciden.")
    else:
        estado, cuerpo = post("/auth/cambiar-clave", {"clave_nueva": nueva})
        if estado == 200:
            st.success("Contraseña actualizada.")
            st.session_state["usuario"]["debe_cambiar_clave"] = False
            es_asesor = st.session_state["usuario"]["rol"] == "ASESOR"
            st.switch_page("paginas/p7_registro_uso.py" if es_asesor else "paginas/p3_ficha_historial.py")
        else:
            st.error(detalle_error(cuerpo))
