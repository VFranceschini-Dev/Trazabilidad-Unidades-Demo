"""P3. Ficha e historial de la unidad (HU-07, HU-11). Réplica de P3_ficha_historial.png.

En esta etapa: datos actuales, línea de tiempo y botones de asignación y service.
El mapa y los botones de uso, préstamo y pase a venta se completan en etapas siguientes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import SesionVencida, detalle_error, get  # noqa: E402
from componentes.ui import FAVICON_RUTA, chip_estado, inyectar_estilos, logo_lateral, mostrar_fecha, tarjeta  # noqa: E402

st.set_page_config(page_title="Ficha de unidad — Parque Demo", layout="wide", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")


def menu_lateral() -> None:
    with st.sidebar:
        st.markdown('<div class="sb-marca">Parque Demo</div>', unsafe_allow_html=True)
        st.markdown('<div class="sb-sub">Trazabilidad de unidades demo</div>', unsafe_allow_html=True)
        usuario = st.session_state.get("usuario", {})
        st.write(f"**{usuario.get('nombre', '')}** · {usuario.get('rol', '')}")
        for opcion in ["Ficha e historial", "Asignación", "Alta de unidad"]:
            if st.button(opcion, use_container_width=True):
                if opcion == "Asignación":
                    st.switch_page("paginas/p4_asignacion.py")
                elif opcion == "Alta de unidad":
                    st.switch_page("paginas/p8_alta_unidad.py")
        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state.clear()
            st.switch_page("paginas/p1_inicio_sesion.py")


menu_lateral()

st.markdown('<div class="titulo-pagina">Ficha e historial de la unidad</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitulo">Estado actual, responsable vigente y línea de tiempo completa.</div>', unsafe_allow_html=True)

# Seleccion de unidad (busqueda por patente o VIN; sin datos personales en URLs)
estado_lista, lista = get("/unidades-resumen") if False else (None, None)
# La API expone fichas por id; para la demo se ofrece un selector con las primeras ids.
opciones = list(range(1, 16))
col_sel, col_buscar = st.columns([2, 3])
with col_sel:
    id_unidad = st.selectbox("Unidad (id)", opciones, index=st.session_state.get("unidad_idx", 0), key="sel_unidad")
with col_buscar:
    st.text_input("Buscar por patente o VIN", placeholder="AA001BB", key="buscar_patente")

try:
    estado, ficha = get(f"/unidades/{id_unidad}")
    if estado != 200:
        st.error(detalle_error(ficha))
        st.stop()
    estado_hist, historial = get(f"/unidades/{id_unidad}/historial")

    u = ficha["unidad"]
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(chip_estado(u["estado_actual"]), unsafe_allow_html=True)
        st.markdown(f"#### {u['modelo']} {u['version']}")
        st.caption(f"{u['patente']} · VIN {u['vin']} · Circuito {u['circuito']}")
    resp = ficha.get("responsable_actual")
    with c2:
        tarjeta(
            [
                ("Sucursal", u.get("sucursal_nombre") or u["id_sucursal"]),
                ("Responsable actual", f"{resp['nombre']} ({resp['tipo']})" if resp else "—"),
                ("Kilometraje", f"{u['km_actual']:,} km".replace(",", ".")),
                ("Próximo service", f"{u['km_proximo_service']:,} km".replace(",", ".") if u.get("km_proximo_service") else "—"),
                ("Límite de rotación", mostrar_fecha(u.get("fecha_limite_rotacion"))),
            ]
        )

    st.markdown("#### Acciones disponibles")
    acciones = ficha.get("acciones_permitidas", [])
    columnas = st.columns(5)
    with columnas[0]:
        if "ASIGNACION" in acciones and st.button("Asignar", use_container_width=True):
            st.session_state["unidad_idx"] = int(id_unidad) - 1
            st.query_params["unidad"] = str(id_unidad)
            st.switch_page("paginas/p4_asignacion.py")
    with columnas[1]:
        if "LIBERACION" in acciones and st.button("Liberar", use_container_width=True):
            from cliente_api import post

            estado_lib, cuerpo_lib = post(f"/unidades/{id_unidad}/liberar", {})
            if estado_lib == 200:
                st.success("Unidad liberada.")
                st.rerun()
            else:
                st.error(detalle_error(cuerpo_lib))
    with columnas[2]:
        if "INGRESO_SERVICE" in acciones and st.button("Ingresar a service", use_container_width=True):
            from cliente_api import post

            estado_sv, cuerpo_sv = post(f"/unidades/{id_unidad}/service/ingreso", {})
            if estado_sv == 200:
                st.success("Unidad ingresada a service.")
                st.rerun()
            else:
                st.error(detalle_error(cuerpo_sv))
    with columnas[3]:
        if "FIN_SERVICE" in acciones and st.button("Fin de service", use_container_width=True):
            st.session_state["fin_service_unidad"] = id_unidad
    with columnas[4]:
        st.button("Test drive / Préstamo / Pase a venta (etapa siguiente)", disabled=True, use_container_width=True)

    if st.session_state.get("fin_service_unidad") == id_unidad:
        with st.form("form_fin_service"):
            km = st.number_input("Kilometraje al egreso", min_value=u["km_actual"], value=u["km_actual"], step=1)
            prox = st.number_input("Próximo service (km)", min_value=int(km), value=int(km) + 10000, step=100)
            if st.form_submit_button("Confirmar fin de service", type="primary"):
                from cliente_api import post

                estado_fs, cuerpo_fs = post(
                    f"/unidades/{id_unidad}/service/fin", {"km": int(km), "proximo_service_km": int(prox)}
                )
                if estado_fs == 200:
                    st.success("Service cerrado.")
                    del st.session_state["fin_service_unidad"]
                    st.rerun()
                else:
                    st.error(detalle_error(cuerpo_fs))

    st.markdown("#### Línea de tiempo")
    if estado_hist == 200:
        for ev in historial["eventos"]:
            fecha = mostrar_fecha(ev["fecha_hora"])
            usuario_ev = ev.get("usuario_nombre") or "sistema"
            diferida = " · carga diferida" if ev.get("carga_diferida") else ""
            transicion = f"{ev['estado_anterior'] or '—'} → {ev['estado_nuevo']}"
            st.markdown(
                f'<div class="tarjeta"><b>{ev["tipo_evento"]}</b> · {transicion}<br>'
                f"<span class='etiqueta'>{fecha} · {usuario_ev} · origen {ev['origen']}{diferida}</span></div>",
                unsafe_allow_html=True,
            )
except SesionVencida:
    st.switch_page("paginas/p1_inicio_sesion.py")
