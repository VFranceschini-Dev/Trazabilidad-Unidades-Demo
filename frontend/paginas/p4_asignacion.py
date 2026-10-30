"""P4. Asignación de unidad (HU-03). Réplica de P4_asignacion.png.

La regla sobre infracciones pendientes de la referencia se agrega con las actas (etapa 3).
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
    P4,
    hoy,
    inyectar_estilos,
    logo_lateral,
    menu_lateral,
    mostrar_dia,
    regla,
    rol_actual,
    selector_unidad,
    tabla,
    titulo_seccion,
)

st.set_page_config(page_title="Asignación — Parque Demo", layout="wide", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")

MOTIVOS = [
    "Demanda comercial de la zona",
    "Rotación entre sucursales",
    "Evento o lanzamiento",
    "Reemplazo de otra unidad",
]

try:
    menu_lateral(P4)

    st.markdown('<div class="titulo-pagina">Asignación de unidad demo</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitulo">Circuito comercial · Ventas y Marketing</div>', unsafe_allow_html=True)

    if rol_actual() != "RESP_MKT_VENTAS":
        st.error("Su rol no puede asignar unidades.")
        st.stop()

    _, unidades = get("/unidades", {"estado": ["DISPONIBLE", "ASIGNADA"], "circuito": "COMERCIAL"})
    _, sucursales = get("/sucursales")
    _, responsables = get("/responsables")
    if not unidades:
        st.info("No hay unidades del circuito comercial disponibles o asignadas.")
        st.stop()

    with st.container(border=True):
        titulo_seccion("Nueva asignación")
        u = selector_unidad(unidades, "Unidad", "sel_unidad_p4")
        reasignar = u["estado_actual"] == "ASIGNADA"

        nombres_sucursal = {s["codigo"]: s["nombre"] for s in sucursales}
        codigos = list(nombres_sucursal)
        id_sucursal = st.selectbox(
            "Sucursal de destino",
            codigos,
            index=codigos.index(u["id_sucursal"]) if u["id_sucursal"] in codigos else 0,
            format_func=lambda c: nombres_sucursal[c],
            key=f"suc_{u['id']}",
        )

        por_id = {r["id"]: r for r in responsables}

        def etiqueta_responsable(i: int) -> str:
            r = por_id[i]
            texto = f"{r['nombre']} · {nombres_sucursal.get(r['id_sucursal'], '—')}"
            return texto if r["activo"] else f"{texto} · INACTIVO"

        id_responsable = st.selectbox(
            "Responsable (empleados sincronizados desde el DMS)",
            list(por_id),
            format_func=etiqueta_responsable,
            placeholder="No hay asesores sincronizados",
        )
        motivo = st.selectbox("Motivo", MOTIVOS)
        col_desde, col_limite = st.columns(2)
        col_desde.text_input("Desde", value=hoy(), disabled=True)
        col_limite.text_input(
            "Límite de rotación (según marca)", value=mostrar_dia(u.get("fecha_limite_rotacion")), disabled=True
        )

        responsable = por_id.get(id_responsable)
        responsable_valido = bool(
            responsable and responsable["activo"] and responsable["id_sucursal"] == id_sucursal
        )

        col_confirmar, col_cancelar, _ = st.columns([3, 2, 3])
        confirmada = col_confirmar.button(
            "Confirmar reasignación" if reasignar else "Confirmar asignación",
            type="primary",
            disabled=not responsable_valido,
            use_container_width=True,
        )
        if col_cancelar.button("Cancelar", use_container_width=True):
            st.switch_page(P3)

    if confirmada:
        ruta = f"/unidades/{u['id']}/reasignar" if reasignar else f"/unidades/{u['id']}/asignaciones"
        estado_r, cuerpo_r = post(
            ruta, {"id_responsable": id_responsable, "id_sucursal": id_sucursal, "motivo": motivo}
        )
        if estado_r == 200:
            st.switch_page(P3)
        st.error(detalle_error(cuerpo_r))

    with st.container(border=True):
        titulo_seccion("Reglas verificadas")
        if reasignar:
            regla("La unidad está ASIGNADA: al confirmar se cierra la asignación vigente y se abre la nueva.", "info")
        else:
            regla("La unidad está DISPONIBLE y no tiene préstamo ni service en curso.")
        if responsable is None:
            regla("No hay asesores sincronizados desde el DMS.", "error")
        elif not responsable["activo"]:
            regla("El responsable seleccionado está inactivo: no se puede confirmar.", "error")
        elif responsable["id_sucursal"] != id_sucursal:
            regla(
                f"El responsable pertenece a {nombres_sucursal.get(responsable['id_sucursal'], '—')}, "
                "no a la sucursal de destino: no se puede confirmar.",
                "error",
            )
        else:
            regla("El responsable está activo y pertenece a la sucursal de destino.")
        _, asignadas = get("/unidades", {"estado": "ASIGNADA"})
        cantidad = sum(1 for a in asignadas if a["id_sucursal"] == id_sucursal and a["id"] != u["id"])
        if cantidad:
            regla(f"La sucursal de destino ya tiene {cantidad} unidades asignadas.", "aviso")

    with st.container(border=True):
        titulo_seccion("Asignaciones anteriores de la unidad")
        _, anteriores = get(f"/unidades/{u['id']}/asignaciones")
        if anteriores:
            tabla(
                ["Sucursal", "Responsable", "Desde", "Hasta"],
                [
                    [
                        a.get("sucursal_nombre") or a["id_sucursal"],
                        a.get("responsable_nombre") or "—",
                        mostrar_dia(a["fecha_desde"]),
                        mostrar_dia(a.get("fecha_hasta")),
                    ]
                    for a in anteriores
                ],
            )
        else:
            st.caption("La unidad todavía no tuvo asignaciones.")
except SesionVencida:
    st.switch_page("paginas/p1_inicio_sesion.py")
