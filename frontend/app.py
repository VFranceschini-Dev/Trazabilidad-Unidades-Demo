"""Punto de entrada multipágina del frontend Streamlit."""

import streamlit as st

st.set_page_config(page_title="Parque Demo", layout="wide")

from componentes.ui import inyectar_estilos  # noqa: E402

inyectar_estilos()

if "pagina" not in st.session_state:
    st.session_state["pagina"] = "p1_inicio_sesion"

st.switch_page("paginas/p1_inicio_sesion.py")
