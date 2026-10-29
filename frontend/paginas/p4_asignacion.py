"""P4. Asignación de unidad (HU-03). Réplica de P4_asignacion.png."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import SesionVencida, detalle_error, get, post  # noqa: E402
from componentes.ui import FAVICON_RUTA, chip_estado, inyectar_estilos, logo_lateral  # noqa: E402

st.set_page_config(page_title="Asignación — Parque Demo", layout="wide", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")

st.markdown('<div class="titulo-pagina">Asignación de unidad demo</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitulo">Asigne una unidad disponible a una sucursal y su asesor responsable (HU-03).</div>', unsafe_allow_html=True)

try:
    id_inicial = int(st.query_params.get("unidad", ["1"])[0])
except ValueError:
    id_inicial = 1

unidad_id = st.number_input("Id de unidad", min_value=1, max_value=999, value=id_inicial, step=1)

try:
    estado, ficha = get(f"/unidades/{int(unidad_id)}")
    if estado != 200:
        st.error(detalle_error(ficha))
        st.stop()
    u = ficha["unidad"]
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(chip_estado(u["estado_actual"]), unsafe_allow_html=True)
        st.markdown(f"#### {u['modelo']} {u['version']}")
        st.caption(f"{u['patente']} · Circuito {u['circuito']}")
    with c2:
        if u["estado_actual"] not in ("DISPONIBLE", "ASIGNADA"):
            st.error(f"La unidad está en estado {u['estado_actual']} y no admite asignación (HU-03.2).")
        elif u["circuito"] != "COMERCIAL":
            st.warning("Solo las unidades del circuito COMERCIAL se asignan a un responsable comercial.")

    sucursales = [("SC01", "Casa Central"), ("SC02", "Formosa"), ("SC03", "Sáenz Peña"), ("SC04", "División Usados")]
    nombres = {
        3: "Alberto Asesor (asesor@demo.local · SC02)",
        2: "Marta Marketing (mkt@demo.local · SC01)",
        4: "Paula Posventa (posventa@demo.local · SC01)",
    }
    with st.form("formulario_asignacion"):
        col_a, col_b = st.columns(2)
        with col_a:
            suc_cod = st.selectbox("Sucursal destino", [f"{c} — {n}" for c, n in sucursales])
        with col_b:
            resp_opciones = {int(k): v for k, v in nombres.items()}
            resp_idx = st.selectbox("Responsable asignado", list(resp_opciones.values()))
            id_responsable = [k for k, v in resp_opciones.items() if v == resp_idx][0]
        reasignar = u["estado_actual"] == "ASIGNADA"
        texto = "Reasignar" if reasignar else "Confirmar asignación"
        confirmada = st.form_submit_button(texto, type="primary", use_container_width=True)

    if confirmada:
        suc = suc_cod.split(" — ")[0]
        ruta = f"/unidades/{int(unidad_id)}/reasignar" if reasignar else f"/unidades/{int(unidad_id)}/asignaciones"
        estado_r, cuerpo_r = post(ruta, {"id_responsable": id_responsable, "id_sucursal": suc})
        if estado_r == 200:
            st.success("Asignación registrada. Volviendo a la ficha…")
            st.query_params["unidad"] = str(int(unidad_id))
            st.switch_page("paginas/p3_ficha_historial.py")
        else:
            st.error(detalle_error(cuerpo_r))
except SesionVencida:
    st.switch_page("paginas/p1_inicio_sesion.py")
