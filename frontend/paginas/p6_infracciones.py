"""P6. Bandeja y validación de actas de infracción (HU-08 a HU-10). Réplica de P6_validacion_acta.png."""

from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cliente_api import SesionVencida, binario, detalle_error, get, post, put  # noqa: E402
from componentes.ui import (  # noqa: E402
    FAVICON_RUTA,
    P6,
    ZONA,
    inyectar_estilos,
    logo_lateral,
    menu_lateral,
    mostrar_dia,
    mostrar_fecha,
    regla,
    rol_actual,
    tabla,
    titulo_seccion,
)

st.set_page_config(page_title="Infracciones — Parque Demo", layout="wide", page_icon=FAVICON_RUTA)
inyectar_estilos()
logo_lateral()

if not st.session_state.get("token"):
    st.switch_page("paginas/p1_inicio_sesion.py")

ESTADOS = {
    "PENDIENTE_VALIDACION": "Pendiente de validación",
    "VALIDADA": "Validada",
    "IMPUTADA": "Imputada",
    "PAGADA": "Pagada",
    "RECHAZADA": "Rechazada",
}
EVENTOS = {"SALIDA": "Uso comercial", "PRESTAMO": "Préstamo por garantía", "ASIGNACION": "Asignación", "REASIGNACION": "Reasignación"}


def formato_monto(valor: Any) -> str:
    if valor is None:
        return ""
    return f"{Decimal(str(valor)):,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def leer_monto(texto: str) -> Optional[str]:
    try:
        return str(Decimal(texto.strip().replace(".", "").replace(",", ".")))
    except InvalidOperation:
        return None


def leer_fecha(texto: str, formato: str) -> Optional[datetime]:
    try:
        return datetime.strptime(texto.strip(), formato).replace(tzinfo=ZONA)
    except ValueError:
        return None


def rotulo(texto: str, campo: str, acta: dict[str, Any]) -> None:
    """HU-08.2 y HU-09.2: confianza de cada dato; por debajo del umbral se marca para revisar."""
    confianza = acta["confianza_campos"].get(campo)
    if confianza is None:
        marca = '<span class="conf-baja">sin leer · completar</span>'
    elif confianza < acta["umbral_confianza"]:
        marca = f'<span class="conf-baja">{confianza:.0f}% · revisar</span>'
    else:
        marca = f'<span class="conf-ok">{confianza:.0f}%</span>'
    st.markdown(f'<div class="rotulo-campo">{escape(texto)} {marca}</div>', unsafe_allow_html=True)


def campo(texto: str, nombre: str, valor: str, acta: dict[str, Any], editable: bool) -> str:
    rotulo(texto, nombre, acta)
    return st.text_input(
        texto, value=valor, disabled=not editable, label_visibility="collapsed",
        key=f"{nombre}_{acta['id_infraccion']}_{acta['estado']}",
    ).strip()


def fila(rot: str, valor: str) -> str:
    return f'<div class="fila-dato"><div class="rotulo">{escape(rot)}</div><div>{escape(valor)}</div></div>'


def ejecutar(respuesta: tuple[int, Any], aviso: str) -> None:
    estado, cuerpo = respuesta
    if estado == 200:
        st.session_state["p6_aviso"] = aviso
        # La pantalla acompaña al acta: con el filtro anterior dejaría de verse
        st.session_state["p6_filtro_siguiente"] = cuerpo["estado"]
        st.rerun()
    st.error(detalle_error(cuerpo))


def bandeja() -> Optional[dict[str, Any]]:
    if "p6_filtro_siguiente" in st.session_state:
        st.session_state["p6_filtro"] = st.session_state.pop("p6_filtro_siguiente")
    st.session_state.setdefault("p6_filtro", "PENDIENTE_VALIDACION")
    filtro = st.selectbox(
        "Estado", ["TODAS", *ESTADOS],
        format_func=lambda e: "Todas" if e == "TODAS" else ESTADOS[e], key="p6_filtro",
    )
    _, actas = get("/infracciones", None if filtro == "TODAS" else {"estado": filtro})
    if not actas:
        st.info("No hay actas en este estado.")
        return None
    tabla(
        ["Acta", "Patente", "Fecha", "Monto", "Confianza", "Estado"],
        [
            [
                a["nro_acta"] or "Sin datos",
                a["patente_leida"] or "—",
                mostrar_fecha(a["fecha_hora_infraccion"]),
                f"$ {formato_monto(a['monto'])}" if a["monto"] else "—",
                f"{float(a['confianza_ocr']):.0f}%" if a["confianza_ocr"] else "—",
                ESTADOS[a["estado"]],
            ]
            for a in actas
        ],
    )
    por_id = {a["id_infraccion"]: a for a in actas}
    ids = list(por_id)
    guardada = st.session_state.get("p6_acta")
    elegida = st.selectbox(
        "Abrir acta", ids, index=ids.index(guardada) if guardada in por_id else 0,
        format_func=lambda i: f"{por_id[i]['nro_acta'] or 'Sin datos legibles'} · {por_id[i]['patente_leida'] or 'sin patente'}",
        key=f"p6_abrir_{filtro}",
    )
    st.session_state["p6_acta"] = elegida
    return por_id[elegida]


def panel_documento(acta: dict[str, Any]) -> None:
    with st.container(border=True):
        estado, imagen = binario(f"/infracciones/{acta['id_infraccion']}/vista")
        if estado == 200:
            st.image(imagen, use_column_width=True)
        else:
            st.warning("No se puede mostrar la vista del PDF; descárguelo para revisarlo.")
        estado_pdf, pdf = binario(f"/infracciones/{acta['id_infraccion']}/pdf")
        if estado_pdf == 200:
            st.download_button(
                "Descargar PDF", pdf, file_name=f"acta-{acta['id_infraccion']}.pdf", mime="application/pdf",
                key=f"pdf_{acta['id_infraccion']}",
            )


def panel_datos(acta: dict[str, Any]) -> dict[str, str]:
    editable = acta["estado"] == "PENDIENTE_VALIDACION"
    with st.container(border=True):
        titulo_seccion("Datos extraídos")
        return {
            "nro": campo("N° de acta", "nro_acta", acta["nro_acta"] or "", acta, editable),
            "patente": campo("Patente", "patente", acta["patente_leida"] or "", acta, editable),
            "fecha": campo("Fecha y hora", "fecha_hora", mostrar_fecha(acta["fecha_hora_infraccion"]) if acta["fecha_hora_infraccion"] else "", acta, editable),
            "jurisdiccion": campo("Jurisdicción", "jurisdiccion", acta["jurisdiccion"] or "", acta, editable),
            "monto": campo("Monto", "monto", formato_monto(acta["monto"]), acta, editable),
            "vencimiento": campo("Vencimiento", "vencimiento", mostrar_dia(acta["fecha_vencimiento"]) if acta["fecha_vencimiento"] else "", acta, editable),
        }


def acciones_pendiente(acta: dict[str, Any], datos: dict[str, str]) -> None:
    id_acta = acta["id_infraccion"]
    with st.container(border=True):
        titulo_seccion("Validación")
        if not acta["unidad_existente"] and acta["patente_leida"]:
            regla(f"La patente {acta['patente_leida']} no corresponde a ninguna unidad demo: corríjala o rechace el acta.", "error")
        fecha = leer_fecha(datos["fecha"], "%d/%m/%Y %H:%M")
        vencimiento = leer_fecha(datos["vencimiento"], "%d/%m/%Y")
        monto = leer_monto(datos["monto"])
        errores = [
            texto
            for texto, invalido in (
                ("N° de acta", not datos["nro"]),
                ("patente", len(datos["patente"]) < 6),
                ("fecha y hora (DD/MM/AAAA HH:MM)", fecha is None),
                ("jurisdicción", not datos["jurisdiccion"]),
                ("monto (185.400,00)", monto is None),
                ("vencimiento (DD/MM/AAAA)", vencimiento is None),
            )
            if invalido
        ]
        if errores:
            regla("Revise: " + ", ".join(errores) + ".", "aviso")
        if st.button("Confirmar datos", type="primary", disabled=bool(errores), key=f"validar_{id_acta}"):
            ejecutar(
                put(
                    f"/infracciones/{id_acta}/validar",
                    {
                        "nro_acta": datos["nro"],
                        "patente": datos["patente"],
                        "fecha_hora_infraccion": fecha.isoformat(),
                        "jurisdiccion": datos["jurisdiccion"],
                        "monto": monto,
                        "fecha_vencimiento": vencimiento.date().isoformat(),
                    },
                ),
                "Acta validada.",
            )
        rechazo(id_acta)


def rechazo(id_acta: int) -> None:
    motivo = st.text_input("Motivo de rechazo", key=f"motivo_{id_acta}").strip()
    if st.button("Rechazar acta", disabled=not motivo, key=f"rechazar_{id_acta}"):
        ejecutar(put(f"/infracciones/{id_acta}/rechazar", {"motivo": motivo}), "Acta rechazada.")


def acciones_validada(acta: dict[str, Any]) -> None:
    id_acta = acta["id_infraccion"]
    with st.container(border=True):
        titulo_seccion("Responsable sugerido")
        estado, s = get(f"/infracciones/{id_acta}/sugerencia")
        if estado != 200:
            st.error(detalle_error(s))
            return
        periodo = f"{mostrar_fecha(s['desde'])} a {mostrar_fecha(s['hasta'])}" if s["desde"] else ""
        evento = f"{EVENTOS.get(s['evento_tipo'], s['evento_tipo'])} ({periodo})" if s["evento_tipo"] else "Sin evento vigente"
        st.markdown(
            fila("Evento vigente", evento) + fila("Responsable", s["nombre"]) + fila("Posición Traccar", s["posicion"]),
            unsafe_allow_html=True,
        )
        if s["sin_responsable"]:
            regla("Sin responsable identificable: se imputa al responsable del circuito y se genera una alerta.", "aviso")
        if st.button("Confirmar e imputar", type="primary", key=f"imputar_{id_acta}"):
            ejecutar(post(f"/infracciones/{id_acta}/imputar"), f"Acta imputada a {s['nombre']}.")
        rechazo(id_acta)


def acciones_cerradas(acta: dict[str, Any]) -> None:
    with st.container(border=True):
        titulo_seccion("Resolución")
        filas = [fila("Estado", ESTADOS[acta["estado"]])]
        if acta["validada_por"]:
            filas.append(fila("Validada por", f"{acta['validada_por']} · {mostrar_fecha(acta['fecha_validacion'])}"))
        if acta["responsable_nombre"]:
            filas.append(fila("Responsable", acta["responsable_nombre"]))
        if acta["motivo_rechazo"]:
            filas.append(fila("Motivo de rechazo", acta["motivo_rechazo"]))
        st.markdown("".join(filas), unsafe_allow_html=True)
        if acta["estado"] == "IMPUTADA" and st.button("Registrar pago", type="primary", key=f"pagar_{acta['id_infraccion']}"):
            ejecutar(post(f"/infracciones/{acta['id_infraccion']}/pagar"), "Pago registrado.")


try:
    menu_lateral(P6)
    st.markdown('<div class="titulo-pagina">Validación de acta de infracción</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitulo">Actas recibidas por correo · lectura automática (OCR) pendiente de confirmación</div>',
        unsafe_allow_html=True,
    )
    if rol_actual() != "ADMINISTRACION":
        st.error("Las actas las gestiona Administración.")
        st.stop()

    lugar_aviso = st.empty()
    aviso = st.session_state.pop("p6_aviso", None)
    if aviso:
        lugar_aviso.success(aviso)

    acta = bandeja()
    if acta is not None:
        st.caption(f"Recibida el {mostrar_fecha(acta['fecha_recepcion'])}")
        col_documento, col_datos = st.columns(2, gap="medium")
        with col_documento:
            panel_documento(acta)
        with col_datos:
            datos = panel_datos(acta)
            if acta["estado"] == "PENDIENTE_VALIDACION":
                acciones_pendiente(acta, datos)
            elif acta["estado"] == "VALIDADA":
                acciones_validada(acta)
            else:
                acciones_cerradas(acta)
except SesionVencida:
    st.switch_page("paginas/p1_inicio_sesion.py")
