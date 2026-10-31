"""Punto de entrada multipágina del frontend Streamlit.

Las páginas viven en `paginas/` (no en `pages/`), así que Streamlit no las descubre solo:
se registran con st.navigation para que st.switch_page("paginas/...") las encuentre.
El menú lateral automático queda oculto; cada página maneja su propia navegación y
llama a st.set_page_config e inyectar_estilos.
"""

import os
import sys

import streamlit as st

if os.environ.get("RECARGA_DESARROLLO"):
    # Streamlit solo invalida su cache de paginas y modulos si hay una sesion conectada al
    # guardar: lo editado con la app cerrada seguiria viejo. Solo en docker-compose.dev.yml.
    from streamlit.runtime import Runtime

    Runtime.instance()._script_cache.clear()
    for modulo in [m for m in sys.modules if m == "cliente_api" or m.split(".")[0] == "componentes"]:
        del sys.modules[modulo]

PAGINAS = [
    st.Page("paginas/p1_inicio_sesion.py", title="Ingreso", default=True),
    st.Page("paginas/p2_cambio_clave.py", title="Cambiar contraseña"),
    st.Page("paginas/p2_tablero.py", title="Tablero"),
    st.Page("paginas/p3_ficha_historial.py", title="Ficha de unidad"),
    st.Page("paginas/p4_asignacion.py", title="Asignación"),
    st.Page("paginas/p5_prestamo_garantia.py", title="Préstamo por garantía"),
    st.Page("paginas/p6_infracciones.py", title="Infracciones"),
    st.Page("paginas/p7_registro_uso.py", title="Registrar uso"),
    st.Page("paginas/p8_alta_unidad.py", title="Alta de unidad"),
    st.Page("paginas/p9_alertas.py", title="Alertas"),
    st.Page("paginas/p10_pase_venta.py", title="Pase a venta y baja"),
]

st.navigation(PAGINAS, position="hidden").run()
