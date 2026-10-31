"""P3. Ficha e historial de la unidad (HU-07, HU-11). Réplica de P3_ficha_historial.png.

Datos actuales, línea de tiempo y botones de asignación, service, uso y préstamo.
El mapa y el pase a venta se completan en etapas siguientes.
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import SesionVencida, detalle_error, get, post  # noqa: E402
from componentes.ui import (  # noqa: E402
    FAVICON_RUTA,
    P3,
    P4,
    P5,
    P7,
    chip_estado,
    inyectar_estilos,
    logo_lateral,
    menu_lateral,
    mostrar_dia,
    mostrar_fecha,
    rol_actual,
    selector_unidad,
    titulo_seccion,
)

st.set_page_config(page_title="Ficha de unidad — Parque Demo", layout="wide", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")

ROLES_ASIGNACION = {"RESP_MKT_VENTAS"}
ROLES_SERVICE = {"RESP_MKT_VENTAS", "RESP_POSVENTA"}

TITULOS_EVENTO = {
    "ALTA": "Alta de unidad demo",
    "ASIGNACION": "Asignación",
    "REASIGNACION": "Reasignación",
    "LIBERACION": "Liberación",
    "SALIDA": "Salida",
    "REGRESO": "Regreso",
    "PRESTAMO": "Préstamo",
    "DEVOLUCION": "Devolución",
    "INGRESO_SERVICE": "Ingreso a service",
    "FIN_SERVICE": "Fin de service",
    "PASE_VENTA": "Pase a venta",
    "BAJA": "Baja",
    "POSICION": "Posición recibida",
    "INFRACCION": "Infracción",
}


TIPOS_USO = {"TEST_DRIVE": "test drive", "GIRA": "gira", "GUARDIA": "guardia", "EVENTO": "evento"}


def km(valor: Any) -> str:
    return f"{valor:,} km".replace(",", ".") if valor is not None else "—"


def fila(rotulo: str, valor_html: str) -> str:
    return f'<div class="fila-dato"><div class="rotulo">{escape(rotulo)}</div><div>{valor_html}</div></div>'


def detalle_evento(ev: dict[str, Any]) -> str:
    datos = ev.get("datos") or {}
    partes = [TITULOS_EVENTO.get(ev["tipo_evento"], ev["tipo_evento"])]
    if datos.get("tipo_uso"):
        partes.append(TIPOS_USO.get(datos["tipo_uso"], datos["tipo_uso"]))
    if datos.get("nombre_cliente"):
        partes.append(str(datos["nombre_cliente"]))
    if datos.get("nro_orden_reparacion"):
        partes.append(str(datos["nro_orden_reparacion"]))
    if datos.get("con_danos"):
        partes.append("con daños")
    if datos.get("id_sucursal"):
        partes.append(f"sucursal {datos['id_sucursal']}")
    if datos.get("motivo"):
        partes.append(str(datos["motivo"]))
    kilometraje = datos.get("km", datos.get("km_inicial"))
    if kilometraje is not None:
        partes.append(km(kilometraje))
    return " · ".join(partes)


def post_y_recargar(ruta: str, cuerpo: dict[str, Any], exito: str) -> None:
    estado, respuesta = post(ruta, cuerpo)
    if estado == 200:
        st.toast(exito)
        st.session_state.pop("fin_service_unidad", None)
        st.rerun()
    st.error(detalle_error(respuesta))


try:
    menu_lateral(P3)

    busqueda = st.text_input("Buscar por patente o VIN", placeholder="AA001BB", key="buscar_patente")
    estado_lista, unidades = get("/unidades", {"q": busqueda} if busqueda else None)
    if estado_lista != 200:
        st.error(detalle_error(unidades))
        st.stop()
    if not unidades:
        st.info("No hay unidades que coincidan con la búsqueda.")
        st.stop()
    u_lista = selector_unidad(unidades, "Unidad", "sel_unidad")
    id_unidad = u_lista["id"]

    estado, ficha = get(f"/unidades/{id_unidad}")
    if estado != 200:
        st.error(detalle_error(ficha))
        st.stop()
    estado_hist, historial = get(f"/unidades/{id_unidad}/historial")
    u = ficha["unidad"]
    resp = ficha.get("responsable_actual")
    acciones = ficha.get("acciones_permitidas", [])
    rol = rol_actual()

    st.markdown(f'<div class="titulo-pagina">Ficha de unidad · {escape(u["patente"])}</div>', unsafe_allow_html=True)
    circuito = "Circuito comercial" if u["circuito"] == "COMERCIAL" else "Circuito posventa"
    st.markdown(
        f'<div class="subtitulo">{escape(u["modelo"])} {escape(u["version"])} · VIN {escape(u["vin"])} · '
        f'{circuito} · {escape(u.get("sucursal_nombre") or u["id_sucursal"])}</div>',
        unsafe_allow_html=True,
    )

    col_datos, col_historial = st.columns(2, gap="medium")

    with col_datos, st.container(border=True):
        titulo_seccion("Datos actuales")
        responsable = f"{resp['nombre']} ({'cliente' if resp['tipo'] == 'CLIENTE' else 'usuario'})" if resp else "—"
        st.markdown(
            fila("Estado", chip_estado(u["estado_actual"]))
            + fila("Responsable", escape(responsable))
            + fila("Kilometraje", km(u["km_actual"]))
            + fila("Próximo service", km(u.get("km_proximo_service")))
            + fila("Alta", mostrar_dia(u.get("fecha_alta")))
            + fila("Límite de rotación", mostrar_dia(u.get("fecha_limite_rotacion"))),
            unsafe_allow_html=True,
        )

        botones = st.columns(2)
        if rol in ROLES_ASIGNACION and u["circuito"] == "COMERCIAL":
            if "ASIGNACION" in acciones and botones[0].button("Asignar", type="primary", use_container_width=True):
                st.switch_page(P4)
            if "REASIGNACION" in acciones and botones[0].button("Reasignar", type="primary", use_container_width=True):
                st.switch_page(P4)
            if "LIBERACION" in acciones and botones[1].button("Liberar", use_container_width=True):
                post_y_recargar(f"/unidades/{id_unidad}/liberar", {}, "Unidad liberada.")
        if rol == "ASESOR":
            if "SALIDA" in acciones and botones[0].button("Registrar salida", type="primary", use_container_width=True):
                st.switch_page(P7)
            if "REGRESO" in acciones and botones[0].button("Registrar regreso", type="primary", use_container_width=True):
                st.switch_page(P7)
        if rol == "RESP_POSVENTA" and u["circuito"] == "POSVENTA":
            if "PRESTAMO" in acciones and botones[0].button("Prestar", type="primary", use_container_width=True):
                st.switch_page(P5)
            if "DEVOLUCION" in acciones and botones[0].button("Registrar devolución", type="primary", use_container_width=True):
                st.switch_page(P5)
        if rol in ROLES_SERVICE:
            if "INGRESO_SERVICE" in acciones and botones[1].button("Ingresar a service", use_container_width=True):
                post_y_recargar(f"/unidades/{id_unidad}/service/ingreso", {}, "Unidad ingresada a service.")
            if "FIN_SERVICE" in acciones and botones[0].button("Fin de service", type="primary", use_container_width=True):
                st.session_state["fin_service_unidad"] = id_unidad

        if st.session_state.get("fin_service_unidad") == id_unidad:
            with st.form("form_fin_service"):
                km_egreso = st.number_input("Kilometraje al egreso", min_value=u["km_actual"], value=u["km_actual"], step=1)
                proximo = st.number_input("Próximo service (km)", min_value=0, value=int(u["km_actual"]) + 10000, step=100)
                if st.form_submit_button("Confirmar fin de service", type="primary"):
                    post_y_recargar(
                        f"/unidades/{id_unidad}/service/fin",
                        {"km": int(km_egreso), "proximo_service_km": int(proximo)},
                        "Service cerrado.",
                    )

    with col_historial, st.container(border=True):
        titulo_seccion("Historial de eventos")
        if estado_hist == 200:
            eventos = "".join(
                '<div class="evento">'
                f"<div>{escape(detalle_evento(ev))}</div>"
                f'<div class="evento-meta">{mostrar_fecha(ev["fecha_hora"])} · '
                f'{escape(ev.get("usuario_nombre") or "Sistema")} · {escape(ev["origen"])}'
                f'{" · carga diferida" if ev.get("carga_diferida") else ""}</div>'
                "</div>"
                for ev in historial["eventos"]
            )
            st.markdown(f'<div class="linea-tiempo">{eventos}</div>', unsafe_allow_html=True)
        else:
            st.error(detalle_error(historial))
except SesionVencida:
    st.switch_page("paginas/p1_inicio_sesion.py")
