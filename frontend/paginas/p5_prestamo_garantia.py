"""P5. Préstamo por garantía (HU-05 y HU-06). Réplica de P5_prestamo_garantia.png."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import SesionVencida, detalle_error, get, post  # noqa: E402
from componentes.ui import (  # noqa: E402
    FAVICON_RUTA,
    P3,
    P5,
    ZONA,
    fecha_hora_diferida,
    inyectar_estilos,
    logo_lateral,
    menu_lateral,
    mostrar_dia,
    mostrar_fecha,
    regla,
    rol_actual,
    selector_unidad,
    tabla,
    titulo_seccion,
)

st.set_page_config(page_title="Préstamo por garantía — Parque Demo", layout="wide", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")

COMBUSTIBLE = {
    0: "Vacío",
    1: "1/8",
    2: "1/4",
    3: "3/8",
    4: "1/2",
    5: "5/8",
    6: "3/4",
    7: "7/8",
    8: "Lleno",
}


def selector_combustible(etiqueta: str, clave: str) -> int:
    return st.selectbox(etiqueta, list(COMBUSTIBLE), index=6, format_func=lambda n: COMBUSTIBLE[n], key=clave)


def proximo_formulario() -> None:
    """Las claves incluyen este contador: al confirmar, el formulario queda vacío."""
    st.session_state["p5_formulario"] = st.session_state.get("p5_formulario", 0) + 1


try:
    menu_lateral(P5)

    st.markdown('<div class="titulo-pagina">Préstamo por garantía</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitulo">Registro de entrega y devolución de unidades demo a clientes con vehículo en garantía</div>',
        unsafe_allow_html=True,
    )

    if rol_actual() != "RESP_POSVENTA":
        st.error("Su rol no puede registrar préstamos.")
        st.stop()

    # Lugar fijo: si el aviso aparece y desaparece, las pestañas se recrean y vuelven a la primera
    lugar_aviso = st.empty()
    aviso = st.session_state.pop("p5_aviso", None)
    if aviso:
        lugar_aviso.success(aviso)

    n = st.session_state.get("p5_formulario", 0)
    _, activos = get("/prestamos", {"activos": "true"})
    tab_entrega, tab_devolucion, tab_activos = st.tabs(["Nueva entrega", "Devolución", f"Préstamos activos ({len(activos)})"])

    with tab_entrega:
        _, disponibles = get("/unidades", {"estado": "DISPONIBLE", "circuito": "POSVENTA"})
        if not disponibles:
            st.info("No hay unidades del circuito Posventa disponibles.")
        else:
            col_datos, col_control = st.columns(2, gap="medium")
            with col_datos, st.container(border=True):
                titulo_seccion("Datos del préstamo")
                orden = st.text_input("Orden de reparación del vehículo del cliente", max_chars=20, key=f"orden_{n}").strip()
                documento = st.text_input("Cliente (DNI / CUIT)", max_chars=20, key=f"documento_{n}").strip()
                nombre = st.text_input("Nombre del cliente (si es nuevo)", max_chars=120, key=f"nombre_{n}").strip()
                unidad = selector_unidad(disponibles, "Unidad demo disponible (circuito Posventa)", f"unidad_{n}")
                fecha_hora = fecha_hora_diferida(f"diferida_entrega_{n}")
                prevista = st.date_input(
                    "Devolución prevista", value=datetime.now(ZONA).date() + timedelta(days=3), format="DD/MM/YYYY", key=f"prevista_{n}"
                )
                km = st.number_input(
                    "Kilometraje de entrega", min_value=unidad["km_actual"], value=unidad["km_actual"], step=1,
                    key=f"km_{n}_{unidad['id']}",
                )
                combustible = selector_combustible("Combustible", f"combustible_{n}")

            with col_control, st.container(border=True):
                titulo_seccion("Control previo a la entrega")
                proximo = unidad.get("km_proximo_service")
                texto_service = f"Service al día (próximo a {proximo:,} km)".replace(",", ".") if proximo else "Service al día"
                control = {
                    "service_al_dia": st.checkbox(texto_service, key=f"c1_{n}"),
                    "documentacion_y_seguro": st.checkbox("Documentación y seguro en la unidad", key=f"c2_{n}"),
                    "sin_danos_visibles": st.checkbox("Sin daños visibles en carrocería", key=f"c3_{n}"),
                    "accesorios_completos": st.checkbox("Accesorios completos (auxilio, gato, llave de rueda)", key=f"c4_{n}"),
                }
                observaciones = st.text_area("Observaciones del estado de la unidad", key=f"obs_{n}").strip()

                vencido = proximo is not None and km >= proximo
                sin_marcar = not all(control.values())
                faltan = [t for t, v in (("orden", orden), ("cliente", documento)) if not v]
                if vencido:
                    regla(f"La unidad tiene el service vencido ({int(km):,} km): no se puede prestar.".replace(",", "."), "error")
                if sin_marcar and not observaciones:
                    regla("Hay ítems sin marcar: indique una observación que lo justifique.", "aviso")
                if faltan:
                    regla("Faltan datos: " + ", ".join(faltan) + ".", "aviso")
                regla(
                    "Al confirmar, la unidad pasa a EN PRÉSTAMO y el cliente queda como responsable desde la hora de entrega.",
                    "info",
                )
                valido = not vencido and not faltan and (not sin_marcar or bool(observaciones))
                col_confirmar, col_cancelar = st.columns([3, 2])
                confirmar = col_confirmar.button(
                    "Confirmar entrega", type="primary", disabled=not valido, use_container_width=True, key=f"ok_{n}"
                )
                if col_cancelar.button("Cancelar", use_container_width=True, key=f"cancelar_{n}"):
                    st.switch_page(P3)

            if confirmar:
                cuerpo = {
                    "id_unidad": unidad["id"],
                    "nro_orden_reparacion": orden,
                    "cliente_documento": documento,
                    "cliente_nombre": nombre or None,
                    "fecha_devolucion_prevista": prevista.isoformat(),
                    "km_entrega": int(km),
                    "combustible_entrega": combustible,
                    "control_previo": control,
                    "observaciones": observaciones or None,
                }
                if fecha_hora:
                    cuerpo["fecha_hora"] = fecha_hora
                estado, resultado = post("/prestamos", cuerpo)
                if estado == 201:
                    st.session_state["p5_aviso"] = f"Préstamo registrado: {unidad['patente']} a {resultado['cliente_nombre']}."
                    proximo_formulario()
                    st.rerun()
                st.error(detalle_error(resultado))

    with tab_devolucion:
        if not activos:
            st.info("No hay préstamos activos.")
        else:
            por_id = {p["id_prestamo"]: p for p in activos}
            with st.container(border=True):
                titulo_seccion("Datos de la devolución")
                elegido = st.selectbox(
                    "Préstamo activo",
                    list(por_id),
                    format_func=lambda i: f"{por_id[i]['unidad_patente']} · {por_id[i]['unidad_modelo']} · "
                    f"{por_id[i]['cliente_nombre']} · {por_id[i]['nro_orden_reparacion']}",
                    key=f"prestamo_{n}",
                )
                p = por_id[elegido]
                st.caption(
                    f"Entregada el {mostrar_fecha(p['fecha_hora_entrega'])} con {p['km_entrega']:,} km · ".replace(",", ".")
                    + f"prevista para el {mostrar_dia(p['fecha_devolucion_prevista'])}"
                )
                if p["demorado"]:
                    regla("Este préstamo está demorado: la fecha prevista ya pasó.", "aviso")
                fecha_devolucion = fecha_hora_diferida(f"diferida_devolucion_{n}")
                c1, c2 = st.columns(2)
                km_devolucion = c1.number_input(
                    "Kilometraje de devolución", min_value=p["km_entrega"], value=p["km_entrega"], step=1,
                    key=f"kmd_{n}_{elegido}",
                )
                with c2:
                    combustible_devolucion = selector_combustible("Combustible", f"combd_{n}")
                con_danos = st.checkbox("La unidad vuelve con daños", key=f"danos_{n}")
                estado_devolucion = st.text_area(
                    "Estado de la unidad al devolverla", key=f"estado_{n}", placeholder="Sin novedades"
                ).strip()
                if con_danos:
                    regla("Al confirmar se genera una alerta para el responsable de Posventa.", "aviso")
                    if not estado_devolucion:
                        regla("Describa los daños para poder confirmar.", "error")
                confirmar_devolucion = st.button(
                    "Confirmar devolución",
                    type="primary",
                    disabled=con_danos and not estado_devolucion,
                    key=f"okd_{n}",
                )
            if confirmar_devolucion:
                cuerpo = {
                    "km_devolucion": int(km_devolucion),
                    "combustible_devolucion": combustible_devolucion,
                    "estado_devolucion": estado_devolucion or "Sin novedades",
                    "con_danos": con_danos,
                }
                if fecha_devolucion:
                    cuerpo["fecha_hora"] = fecha_devolucion
                estado, resultado = post(f"/prestamos/{elegido}/devolucion", cuerpo)
                if estado == 200:
                    st.session_state["p5_aviso"] = f"Devolución registrada: {p['unidad_patente']} vuelve a DISPONIBLE."
                    proximo_formulario()
                    st.rerun()
                st.error(detalle_error(resultado))

    with tab_activos:
        if not activos:
            st.info("No hay préstamos activos.")
        else:
            demorados = [p for p in activos if p["demorado"]]
            for p in demorados:
                regla(
                    f"{p['unidad_patente']} demorada: debía volver el {mostrar_dia(p['fecha_devolucion_prevista'])}.",
                    "aviso",
                )
            tabla(
                ["Unidad", "Cliente", "Orden", "Entrega", "Prevista", "Situación"],
                [
                    [
                        f"{p['unidad_patente']} · {p['unidad_modelo']}",
                        p["cliente_nombre"],
                        p["nro_orden_reparacion"],
                        mostrar_fecha(p["fecha_hora_entrega"]),
                        mostrar_dia(p["fecha_devolucion_prevista"]),
                        "DEMORADO" if p["demorado"] else "En término",
                    ]
                    for p in activos
                ],
            )
except SesionVencida:
    st.switch_page("paginas/p1_inicio_sesion.py")
