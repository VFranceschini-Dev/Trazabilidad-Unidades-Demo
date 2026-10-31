"""P7. Registro de uso comercial (HU-04). Réplica de P7_registro_uso_movil.png.

Pensada para un celular de 390 px: una columna, campos grandes y un solo botón principal.
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import SesionVencida, detalle_error, get, post  # noqa: E402
from componentes.ui import (  # noqa: E402
    FAVICON_RUTA,
    P7,
    chip_estado,
    descripcion_unidad,
    fecha_hora_diferida,
    inyectar_estilos,
    logo_lateral,
    menu_lateral,
    mostrar_fecha,
    regla,
    rol_actual,
    tabla,
)

st.set_page_config(page_title="Registrar uso — Parque Demo", layout="centered", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")

TIPOS = {"TEST_DRIVE": "Test drive", "GIRA": "Gira", "GUARDIA": "Guardia", "EVENTO": "Evento"}


def proximo_formulario() -> None:
    """Las claves incluyen este contador: al confirmar, el formulario queda vacío."""
    st.session_state["p7_formulario"] = st.session_state.get("p7_formulario", 0) + 1


try:
    menu_lateral(P7)

    yo = st.session_state.get("yo", {})
    usuario = st.session_state.get("usuario", {})
    st.markdown(
        f'<div class="cabecera-movil">{escape(str(usuario.get("nombre", "")))} · '
        f'{escape(str(yo.get("sucursal_nombre") or "—"))}</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="titulo-pagina">Registrar uso</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitulo">Salida y regreso de unidades asignadas</div>', unsafe_allow_html=True)

    if rol_actual() != "ASESOR":
        st.error("El uso comercial lo registra el asesor responsable de la unidad.")
        st.stop()

    # Lugar fijo: si el aviso aparece y desaparece, las pestañas se recrean y vuelven a la primera
    lugar_aviso = st.empty()
    aviso = st.session_state.pop("p7_aviso", None)
    if aviso:
        lugar_aviso.success(aviso)

    _, mias = get("/usos/mis-unidades")
    if not mias:
        st.info("No tenés unidades asignadas.")
        st.stop()

    por_id = {m["unidad"]["id"]: m for m in mias}
    ids = list(por_id)
    guardada = st.session_state.get("unidad_id")
    if len(ids) > 1:
        id_unidad = st.selectbox(
            "Unidad",
            ids,
            index=ids.index(guardada) if guardada in por_id else 0,
            format_func=lambda i: descripcion_unidad(por_id[i]["unidad"]),
            key="unidad_p7",
        )
    else:
        id_unidad = ids[0]
    st.session_state["unidad_id"] = id_unidad
    u = por_id[id_unidad]["unidad"]
    uso = por_id[id_unidad]["uso_abierto"]

    km_texto = f"{u['km_actual']:,}".replace(",", ".")
    st.markdown(
        f'<div class="tarjeta tarjeta-unidad"><div><div class="valor">{escape(u["patente"])}</div>'
        f'<div class="etiqueta-unidad">{escape(u["modelo"])} {escape(u["version"])} · {km_texto} km</div></div>'
        f'{chip_estado(u["estado_actual"])}</div>',
        unsafe_allow_html=True,
    )

    n = st.session_state.get("p7_formulario", 0)
    # Con una salida abierta, lo proximo es el regreso: esa pestana queda primera
    if uso:
        tab_regreso, tab_salida = st.tabs(["Regreso", "Salida"])
    else:
        tab_salida, tab_regreso = st.tabs(["Salida", "Regreso"])

    with tab_salida:
        if u["estado_actual"] != "ASIGNADA":
            st.info(f"La unidad está en estado {u['estado_actual'].replace('_', ' ')}: registrá primero su regreso.")
        else:
            tipo = st.radio(
                "Tipo de uso", list(TIPOS), format_func=lambda t: TIPOS[t], horizontal=True, key=f"tipo_{n}"
            )
            nombre = telefono = ""
            if tipo == "TEST_DRIVE":
                nombre = st.text_input("Cliente prospecto", key=f"nombre_{n}").strip()
                telefono = st.text_input("Teléfono del prospecto", key=f"telefono_{n}").strip()
            km_salida = st.number_input(
                "Kilometraje de salida", min_value=u["km_actual"], value=u["km_actual"], step=1, key=f"km_{n}_{id_unidad}"
            )
            fecha_hora = fecha_hora_diferida(f"diferida_salida_{n}")
            observaciones = st.text_area("Observaciones", placeholder="Opcional", key=f"obs_{n}", height=80).strip()
            regla("Al confirmar, la unidad pasa a EN USO y queda a tu cargo hasta registrar el regreso.", "info")
            falta_prospecto = tipo == "TEST_DRIVE" and not (nombre and telefono)
            if st.button(
                "Confirmar salida", type="primary", use_container_width=True, disabled=falta_prospecto, key=f"ok_{n}"
            ):
                cuerpo = {
                    "id_unidad": id_unidad,
                    "tipo_uso": tipo,
                    "km_salida": int(km_salida),
                    "cliente_nombre": nombre or None,
                    "cliente_telefono": telefono or None,
                    "observaciones": observaciones or None,
                }
                if fecha_hora:
                    cuerpo["fecha_hora"] = fecha_hora
                estado, resultado = post("/usos/salida", cuerpo)
                if estado == 201:
                    st.session_state["p7_aviso"] = f"Salida registrada: {u['patente']} en uso."
                    proximo_formulario()
                    st.rerun()
                st.error(detalle_error(resultado))

    with tab_regreso:
        if uso is None:
            st.info("La unidad no tiene una salida abierta.")
        else:
            tabla(
                ["Salida", "Tipo", "Km"],
                [[mostrar_fecha(uso["fecha_hora_salida"]), TIPOS[uso["tipo_uso"]], f"{uso['km_salida']:,}".replace(",", ".")]],
            )
            km_regreso = st.number_input(
                "Kilometraje de regreso", min_value=uso["km_salida"], value=uso["km_salida"], step=1, key=f"kmr_{n}_{uso['id_uso']}"
            )
            fecha_regreso = fecha_hora_diferida(f"diferida_regreso_{n}")
            observaciones_regreso = st.text_area(
                "Observaciones", placeholder="Opcional", key=f"obsr_{n}", height=80
            ).strip()
            regla("Al confirmar, la unidad vuelve a ASIGNADA con el kilometraje actualizado.", "info")
            if st.button("Confirmar regreso", type="primary", use_container_width=True, key=f"okr_{n}"):
                cuerpo = {"km_regreso": int(km_regreso), "observaciones": observaciones_regreso or None}
                if fecha_regreso:
                    cuerpo["fecha_hora"] = fecha_regreso
                estado, resultado = post(f"/usos/{uso['id_uso']}/regreso", cuerpo)
                if estado == 200:
                    st.session_state["p7_aviso"] = f"Regreso registrado: {u['patente']} vuelve a ASIGNADA."
                    proximo_formulario()
                    st.rerun()
                st.error(detalle_error(resultado))
except SesionVencida:
    st.switch_page("paginas/p1_inicio_sesion.py")
