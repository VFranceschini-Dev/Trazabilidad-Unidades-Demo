"""P8. Alta de unidad demo (HU-02). Réplica de P8_alta_unidad.png.

Sin búsqueda en el DMS (el DMS simulado no publica unidades) ni dispositivo Traccar (etapa 4):
ver docs/decisiones.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import SesionVencida, detalle_error, get, post  # noqa: E402
from componentes.ui import (  # noqa: E402
    FAVICON_RUTA,
    P3,
    P8,
    inyectar_estilos,
    logo_lateral,
    menu_lateral,
    mostrar_dia,
    regla,
    rol_actual,
    tabla,
    titulo_seccion,
)

st.set_page_config(page_title="Alta de unidad — Parque Demo", layout="wide", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")

CIRCUITO_POR_ROL = {"RESP_MKT_VENTAS": "COMERCIAL", "RESP_POSVENTA": "POSVENTA"}
NOMBRE_CIRCUITO = {"COMERCIAL": "Comercial (Ventas y Marketing)", "POSVENTA": "Posventa"}

try:
    menu_lateral(P8)

    st.markdown('<div class="titulo-pagina">Alta de unidad demo</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitulo">La unidad comienza su historial en estado DISPONIBLE</div>', unsafe_allow_html=True)

    circuito = CIRCUITO_POR_ROL.get(rol_actual())
    if circuito is None:
        st.error("Su rol no puede dar de alta unidades.")
        st.stop()

    _, sucursales = get("/sucursales")
    nombres_sucursal = {s["codigo"]: s["nombre"] for s in sucursales}
    _, limite = get("/unidades/limite-rotacion", {"circuito": circuito})

    col_form, col_lateral = st.columns([3, 2], gap="medium")

    with col_form, st.container(border=True):
        titulo_seccion("Datos de la unidad")
        c1, c2 = st.columns(2)
        vin = c1.text_input("VIN (17 caracteres)", max_chars=17).strip().upper()
        patente = c2.text_input("Patente", max_chars=10).strip().upper()
        c1, c2 = st.columns(2)
        modelo = c1.text_input("Modelo").strip()
        version = c2.text_input("Versión").strip()
        c1, c2 = st.columns(2)
        c1.text_input("Circuito", value=NOMBRE_CIRCUITO[circuito], disabled=True)
        id_sucursal = c2.selectbox("Sucursal", list(nombres_sucursal), format_func=lambda c: nombres_sucursal[c])
        c1, c2 = st.columns(2)
        km_inicial = c1.number_input("Kilometraje inicial", min_value=0, value=0, step=10)
        proximo = c2.number_input("Próximo service (km)", min_value=0, value=10000, step=500)
        st.text_input("Límite de rotación (calculado)", value=mostrar_dia(limite["fecha_limite"]), disabled=True)
        diferida = st.checkbox("Carga diferida (fecha y hora del movimiento real)")
        fecha_txt = st.text_input("Fecha y hora (ISO 8601)", disabled=not diferida, placeholder="2026-10-30T09:00:00-03:00")

        # Controles en vivo contra las unidades ya registradas (HU-02.2)
        vin_repetido = len(vin) == 17 and any(u["vin"] == vin for u in get("/unidades", {"q": vin})[1])
        patente_repetida = bool(patente) and any(u["patente"] == patente for u in get("/unidades", {"q": patente})[1])
        faltantes = [
            nombre
            for nombre, valor in (("VIN", vin), ("patente", patente), ("modelo", modelo), ("versión", version))
            if not valor
        ]
        valido = not faltantes and len(vin) == 17 and len(patente) >= 5 and not vin_repetido and not patente_repetida

        col_confirmar, col_cancelar, _ = st.columns([3, 2, 3])
        confirmar = col_confirmar.button("Confirmar alta", type="primary", disabled=not valido, use_container_width=True)
        if col_cancelar.button("Cancelar", use_container_width=True):
            st.switch_page(P3)

        if confirmar:
            cuerpo = {
                "vin": vin,
                "patente": patente,
                "modelo": modelo,
                "version": version,
                "circuito": circuito,
                "id_sucursal": id_sucursal,
                "km_inicial": int(km_inicial),
                "km_proximo_service": int(proximo),
            }
            if diferida and fecha_txt:
                cuerpo["fecha_hora"] = fecha_txt
            estado, resultado = post("/unidades", cuerpo)
            if estado == 201:
                st.session_state["unidad_id"] = resultado["unidad"]["id"]
                st.switch_page(P3)
            st.error(detalle_error(resultado))

    with col_lateral:
        with st.container(border=True):
            titulo_seccion("Controles")
            if vin_repetido:
                regla("Ya existe una unidad con ese VIN.", "error")
            elif len(vin) == 17:
                regla("El VIN tiene 17 caracteres y no está registrado.")
            else:
                regla(f"El VIN debe tener 17 caracteres (tiene {len(vin)}).", "aviso")
            if patente_repetida:
                regla("La patente corresponde a otra unidad.", "error")
            elif len(patente) >= 5:
                regla("La patente no corresponde a otra unidad.")
            else:
                regla("Complete la patente (mínimo 5 caracteres).", "aviso")
            if faltantes:
                regla("Faltan datos obligatorios: " + ", ".join(faltantes) + ".", "aviso")
            nombre = "comercial" if circuito == "COMERCIAL" else "posventa"
            regla(
                f"El límite de rotación surge del plazo configurado para el circuito {nombre}: {limite['meses']} meses.",
                "info",
            )
        with st.container(border=True):
            titulo_seccion("Altas recientes")
            _, recientes = get("/unidades/recientes", {"limite": 5})
            tabla(
                ["Patente", "Fecha", "Origen"],
                [[r["patente"], mostrar_dia(r["fecha_hora"]), r["origen"]] for r in recientes],
            )
except SesionVencida:
    st.switch_page("paginas/p1_inicio_sesion.py")
