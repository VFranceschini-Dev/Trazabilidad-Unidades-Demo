"""Punto de entrada multipágina del frontend Streamlit.

Las páginas viven en `paginas/` (no en `pages/`), así que Streamlit no las descubre solo:
se registran con st.navigation para que st.switch_page("paginas/...") las encuentre.
El menú lateral automático queda oculto; cada página maneja su propia navegación y
llama a st.set_page_config e inyectar_estilos.
"""

import streamlit as st

PAGINAS = [
    st.Page("paginas/p1_inicio_sesion.py", title="Ingreso", default=True),
    st.Page("paginas/p2_cambio_clave.py", title="Cambiar contraseña"),
    st.Page("paginas/p3_ficha_historial.py", title="Ficha de unidad"),
    st.Page("paginas/p4_asignacion.py", title="Asignación"),
    st.Page("paginas/p8_alta_unidad.py", title="Alta de unidad"),
]

st.navigation(PAGINAS, position="hidden").run()
