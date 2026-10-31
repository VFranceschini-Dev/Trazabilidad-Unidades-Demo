"""P10. Pase a venta y baja (HU-14). Réplica de P10_pase_venta_baja.png."""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import SesionVencida, detalle_error, get, post  # noqa: E402
from componentes.ui import (  # noqa: E402
    FAVICON_RUTA,
    P3,
    P10,
    chip_estado,
    inyectar_estilos,
    logo_lateral,
    menu_lateral,
    mostrar_fecha,
    regla,
    rol_actual,
    selector_unidad,
    tabla,
    titulo_seccion,
)

st.set_page_config(page_title="Pase a venta — Parque Demo", layout="wide", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")

MOTIVOS = ["Cumplió el plazo de rotación", "Reemplazo por modelo nuevo", "Kilometraje elevado", "Decisión comercial"]
BAJAS = {"VENTA_USADO": "Venta como usado", "DEVOLUCION_TERMINAL": "Devolución a la terminal"}

try:
    menu_lateral(P10)
    if rol_actual() != "RESP_MKT_VENTAS":
        st.error("El pase a venta y la baja los registra Marketing y Ventas.")
        st.stop()

    lugar_aviso = st.empty()
    aviso = st.session_state.pop("p10_aviso", None)
    if aviso:
        lugar_aviso.success(aviso)

    _, unidades = get("/unidades")
    if not unidades:
        st.info("No hay unidades.")
        st.stop()
    u = selector_unidad(unidades, "Unidad", "p10_unidad")
    estado = u["estado_actual"]
    id_unidad = u["id"]

    st.markdown(f'<div class="titulo-pagina">Pase a venta y baja · {escape(u["patente"])}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="subtitulo">{escape(u["modelo"])} {escape(u["version"])} · Circuito {u["circuito"].lower()} · '
        f'{escape(u.get("sucursal_nombre") or u["id_sucursal"])} · estado actual {chip_estado(estado)}</div>',
        unsafe_allow_html=True,
    )

    _, actas = get(f"/unidades/{id_unidad}/actas-pendientes")
    habilitada = estado in ("DISPONIBLE", "ASIGNADA") and not actas
    _, sucursales = get("/sucursales")
    nombres = {s["codigo"]: s["nombre"] for s in sucursales}

    col_form, col_controles = st.columns(2, gap="medium")
    with col_form:
        with st.container(border=True):
            titulo_seccion("Pase a venta")
            motivo = st.selectbox("Motivo", MOTIVOS, key=f"motivo_{id_unidad}")
            destino = st.selectbox(
                "Destino", list(nombres), index=list(nombres).index("SC04") if "SC04" in nombres else 0,
                format_func=lambda c: nombres[c], key=f"destino_{id_unidad}",
            )
            st.text_input("Kilometraje actual", value=f"{u['km_actual']:,}".replace(",", "."), disabled=True, key=f"km_{id_unidad}")
            c1, c2 = st.columns(2)
            if c1.button("Confirmar pase a venta", type="primary", disabled=not habilitada, use_container_width=True):
                codigo, cuerpo = post(f"/unidades/{id_unidad}/pase-venta", {"motivo": motivo, "id_sucursal": destino})
                if codigo == 200:
                    st.session_state["p10_aviso"] = f"{u['patente']} pasó a EN VENTA."
                    st.rerun()
                st.error(detalle_error(cuerpo))
            if c2.button("Volver a la ficha", use_container_width=True):
                st.switch_page(P3)
        with st.container(border=True):
            titulo_seccion("Baja definitiva")
            st.caption("Disponible solo para unidades EN VENTA.")
            tipo_baja = st.selectbox(
                "Tipo de baja", list(BAJAS), format_func=lambda b: BAJAS[b], disabled=estado != "EN_VENTA", key=f"baja_{id_unidad}"
            )
            if st.button("Registrar baja", disabled=estado != "EN_VENTA"):
                codigo, cuerpo = post(f"/unidades/{id_unidad}/baja", {"motivo": tipo_baja})
                if codigo == 200:
                    st.session_state["p10_aviso"] = f"{u['patente']} pasó a BAJA y conserva su historial."
                    st.rerun()
                st.error(detalle_error(cuerpo))

    with col_controles:
        with st.container(border=True):
            titulo_seccion("Controles previos")
            if estado == "EN_USO":
                regla("La unidad está EN USO: primero debe registrarse el regreso.", "error")
            elif estado == "EN_VENTA":
                regla("La unidad ya está EN VENTA.", "info")
            elif estado == "BAJA":
                regla("La unidad está dada de baja.", "info")
            elif estado in ("EN_PRESTAMO", "EN_SERVICE"):
                regla(f"La unidad está {estado.replace('_', ' ')}: primero debe cerrarse.", "error")
            else:
                regla("No tiene préstamos ni service en curso.")
            if actas:
                regla(f"Tiene {len(actas)} acta(s) pendiente(s) de validación o imputación.", "error")
            else:
                regla("No tiene actas pendientes.")
        if actas:
            with st.container(border=True):
                titulo_seccion("Actas pendientes")
                tabla(
                    ["N.° de acta", "Fecha", "Estado"],
                    [[a["nro_acta"] or "Sin datos", mostrar_fecha(a["fecha_hora_infraccion"]), a["estado"].replace("_", " ")] for a in actas],
                )
                st.caption("Las resuelve Administración en Infracciones.")
        regla("Al registrar la baja, la unidad pasa a BAJA y conserva todo su historial para consulta.", "info")
except SesionVencida:
    st.switch_page("paginas/p1_inicio_sesion.py")
