"""Aceptacion de HU-08, HU-09 y HU-10, lector de actas y acceso a unidades por perfil."""

from __future__ import annotations

import io
import itertools
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.core.config import settings
from app.identidad.models import Rol, Usuario
from app.infracciones.service import normalizar_patente
from app.tablas_generales.models import Alerta
from lector_actas import LectorTesseract, a_json

CLAVE = "Demo-Pruebas-2026!"
AR = ZoneInfo("America/Argentina/Buenos_Aires")
_contador = itertools.count(1)


def _lineas(nro: str, patente: str, cuando: datetime) -> list[str]:
    return [
        "Organismo de Transito - Municipalidad de Resistencia",
        f"Acta N: {nro}",
        f"Dominio: {patente}",
        f"Fecha: {cuando:%d/%m/%Y} Hora: {cuando:%H:%M}",
        "Jurisdiccion: Municipalidad de Resistencia",
        "Lugar: Av. Sarmiento 1200",
        "Importe de la multa: $ 185.400,00",
        f"Vencimiento pago voluntario: {cuando + timedelta(days=30):%d/%m/%Y}",
    ]


def _pdf_texto(lineas: list[str]) -> bytes:
    salida = io.BytesIO()
    c = canvas.Canvas(salida, pagesize=A4)
    y = 780
    for linea in lineas:
        c.drawString(60, y, linea)
        y -= 24
    c.save()
    return salida.getvalue()


def _pdf_rasterizado(lineas: list[str]) -> bytes:
    """Sin capa de texto: la pagina es una imagen con rotacion leve."""
    salida = io.BytesIO()
    c = canvas.Canvas(salida, pagesize=A4)
    y = 780
    for linea in lineas:
        c.setFont("Courier-Bold", 13)
        c.drawString(60, y, linea)
        y -= 30
    c.save()
    from pdf2image import convert_from_bytes

    imagen = convert_from_bytes(salida.getvalue(), dpi=200)[0].rotate(0.6, fillcolor="white")
    final = io.BytesIO()
    imagen.convert("RGB").save(final, format="PDF", resolution=200)
    return final.getvalue()


def _pdf_ilegible() -> bytes:
    final = io.BytesIO()
    Image.effect_noise((500, 700), 90).convert("RGB").filter(ImageFilter.GaussianBlur(2)).save(final, format="PDF")
    return final.getvalue()


@pytest.fixture(autouse=True)
def _carpeta_actas(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "actas_dir", str(tmp_path))


def _usuario(client: Any, sesion: Any, hash_pruebas: str, rol: Rol) -> tuple[dict[str, str], Usuario]:
    n = next(_contador)
    usuario = Usuario(
        legajo=f"3{n:04d}", correo=f"actas{n}@pruebas.local", nombre=f"Actas {n}",
        rol=rol, id_sucursal="SC01", hash_clave=hash_pruebas,
    )
    sesion.add(usuario)
    sesion.commit()
    r = client.post("/api/v1/auth/ingresar", json={"correo": usuario.correo, "clave": CLAVE})
    return {"Authorization": f"Bearer {r.json()['token']}"}, usuario


def _ingesta(client: Any, contenido: bytes, clave: str | None = None) -> Any:
    """Lo mismo que hace el flujo de n8n: guarda el PDF, lo lee y envia los datos con el nombre."""
    nombre = f"acta-{next(_contador)}.pdf"
    (Path(settings.actas_dir) / nombre).write_bytes(contenido)
    return client.post(
        "/api/v1/infracciones/ingesta",
        json={**json.loads(a_json(LectorTesseract().leer(contenido))), "archivo_pdf": nombre},
        headers={"X-API-Key": clave or settings.n8n_api_key},
    )


def _nro() -> str:
    return f"2026-{next(_contador):06d}"


@pytest.fixture()
def admin(client, sesion, hash_pruebas, base) -> dict[str, str]:
    return _usuario(client, sesion, hash_pruebas, Rol.ADMINISTRACION)[0]


@pytest.fixture()
def mkt(client, sesion, hash_pruebas, base) -> dict[str, str]:
    return _usuario(client, sesion, hash_pruebas, Rol.RESP_MKT_VENTAS)[0]


def _alta(client: Any, cab: dict[str, str], circuito: str = "COMERCIAL") -> dict[str, Any]:
    n = next(_contador)
    r = client.post(
        "/api/v1/unidades",
        json={
            "vin": f"1FTFW1E80PFI{n:05d}", "patente": f"IN{n:03d}FR", "modelo": "Ranger", "version": "XLS",
            "circuito": circuito, "id_sucursal": "SC01", "km_inicial": 1000,
        },
        headers=cab,
    )
    assert r.status_code == 201, r.text
    return r.json()["unidad"]


def _datos_validos(nro: str, patente: str, cuando: datetime | None = None) -> dict[str, Any]:
    cuando = cuando or datetime.now(AR) - timedelta(minutes=1)
    return {
        "nro_acta": nro,
        "patente": patente,
        "fecha_hora_infraccion": cuando.isoformat(),
        "jurisdiccion": "Resistencia",
        "monto": "185400.00",
        "fecha_vencimiento": (cuando + timedelta(days=30)).date().isoformat(),
    }


def _acta_validada(client: Any, admin: dict[str, str], patente: str, cuando: datetime | None = None) -> dict[str, Any]:
    nro = _nro()
    acta = _ingesta(client, _pdf_texto(_lineas(nro, patente, datetime.now(AR) - timedelta(days=1)))).json()
    r = client.put(f"/api/v1/infracciones/{acta['id_infraccion']}/validar", json=_datos_validos(nro, patente, cuando), headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


# --- Lector -------------------------------------------------------------------------


def test_lector_capa_de_texto_con_confianza_99() -> None:
    cuando = datetime(2026, 10, 6, 11, 47, tzinfo=AR)
    lectura = LectorTesseract().leer(_pdf_texto(_lineas("2026-114587", "AE 512 KT", cuando)))
    assert lectura.nro_acta == "2026-114587"
    assert lectura.patente == "AE512KT"
    assert lectura.fecha_hora == cuando
    assert lectura.monto == Decimal("185400.00")
    assert lectura.vencimiento == (cuando + timedelta(days=30)).date()
    assert lectura.jurisdiccion == "Municipalidad de Resistencia"
    assert set(lectura.confianza_campos.values()) == {99.0}
    assert lectura.confianza == 99.0


def test_lector_formato_viejo_de_patente() -> None:
    lectura = LectorTesseract().leer(_pdf_texto(_lineas("A-1", "ABC 123", datetime(2026, 1, 2, 3, 4, tzinfo=AR)) + ["relleno de texto"]))
    assert lectura.patente == "ABC123"


def test_lector_no_toma_la_fecha_de_emision() -> None:
    lineas = ["Fecha de emision: 01/01/2026 09:00"] + _lineas("A-2", "AE 512 KT", datetime(2026, 10, 6, 11, 47, tzinfo=AR))
    assert LectorTesseract().leer(_pdf_texto(lineas)).fecha_hora == datetime(2026, 10, 6, 11, 47, tzinfo=AR)


def test_lector_ocr_en_pdf_sin_texto() -> None:
    cuando = datetime(2026, 10, 6, 11, 47, tzinfo=AR)
    lectura = LectorTesseract().leer(_pdf_rasterizado(_lineas("2026-114588", "AE 512 KT", cuando)))
    assert lectura.nro_acta == "2026-114588"
    assert lectura.patente == "AE512KT"
    assert lectura.monto == Decimal("185400.00")
    assert 0 < lectura.confianza_campos["patente"] <= 100
    assert lectura.confianza is not None


def test_lector_pdf_ilegible_o_danado_no_falla() -> None:
    assert LectorTesseract().leer(_pdf_ilegible()).confianza_campos == {}
    assert LectorTesseract().leer(b"%PDF-1.4 roto").nro_acta is None


def test_lector_prefiere_jurisdiccion_y_usa_el_lugar_si_falta() -> None:
    momento = datetime(2026, 10, 6, 11, 47, tzinfo=AR)
    lineas = ["Lugar: Ruta Nacional 11 km 1003", *_lineas("A-3", "AE 512 KT", momento)]
    assert LectorTesseract().leer(_pdf_texto(lineas)).jurisdiccion == "Municipalidad de Resistencia"
    solo_lugar = [l for l in lineas if not l.startswith("Jurisdiccion")]
    assert LectorTesseract().leer(_pdf_texto(solo_lugar)).jurisdiccion == "Ruta Nacional 11 km 1003"


def test_normalizar_patente() -> None:
    assert normalizar_patente("ae 512-kt") == "AE512KT"


# --- HU-08 --------------------------------------------------------------------------


def test_ingesta_exige_api_key(client, base) -> None:
    assert _ingesta(client, _pdf_texto(["x"]), clave="incorrecta").status_code == 401


def _enviar_datos(client: Any, **datos: Any) -> Any:
    return client.post("/api/v1/infracciones/ingesta", json=datos, headers={"X-API-Key": settings.n8n_api_key})


def test_ingesta_rechaza_datos_invalidos(client, base, tmp_path) -> None:
    (tmp_path / "valido.pdf").write_bytes(_pdf_ilegible())
    assert _enviar_datos(client, archivo_pdf="valido.pdf", fecha_hora="no es fecha").status_code == 422


@pytest.mark.parametrize("nombre", ["../secreto.pdf", "/etc/passwd", "sin-extension", "a b.pdf"])
def test_ingesta_rechaza_rutas_fuera_de_la_carpeta(client, base, nombre) -> None:
    assert _enviar_datos(client, archivo_pdf=nombre).status_code == 422


def test_ingesta_exige_que_el_pdf_exista(client, base) -> None:
    r = _enviar_datos(client, archivo_pdf="no-existe.pdf")
    assert (r.status_code, r.json()["codigo"]) == (422, "PDF_NO_ENCONTRADO")


def test_ingesta_rechaza_lo_que_no_es_pdf(client, base) -> None:
    r = _ingesta(client, b"no soy un pdf")
    assert (r.status_code, r.json()["codigo"]) == (422, "ARCHIVO_NO_PDF")


def test_hu08_1_y_2_extrae_datos_y_queda_pendiente_con_confianza(client, base, fabrica_sesion) -> None:
    nro = _nro()
    r = _ingesta(client, _pdf_texto(_lineas(nro, "AE 512 KT", datetime(2026, 10, 6, 11, 47, tzinfo=AR))))
    assert r.status_code == 201, r.text
    acta = r.json()
    assert acta["estado"] == "PENDIENTE_VALIDACION"
    assert (acta["nro_acta"], acta["patente_leida"]) == (nro, "AE512KT")
    assert Decimal(acta["monto"]) == Decimal("185400.00")
    assert set(acta["confianza_campos"]) == {"nro_acta", "patente", "fecha_hora", "jurisdiccion", "monto", "vencimiento"}
    with fabrica_sesion() as ses:
        alerta = ses.scalars(select(Alerta).where(Alerta.id_infraccion == acta["id_infraccion"])).one()
    assert (alerta.tipo_alerta, alerta.estado) == ("ACTA_A_VALIDAR", "ABIERTA")


def test_hu08_3_numero_repetido_no_duplica(client, base, tmp_path) -> None:
    nro = _nro()
    pdf = _pdf_texto(_lineas(nro, "AE 512 KT", datetime(2026, 10, 6, 11, 47, tzinfo=AR)))
    primera = _ingesta(client, pdf)
    archivos = len(list(tmp_path.iterdir()))
    segunda = _ingesta(client, pdf)  # n8n guarda otra copia: la API borra la repetida
    assert (primera.status_code, segunda.status_code) == (201, 200)
    assert primera.json()["id_infraccion"] == segunda.json()["id_infraccion"]
    assert len(list(tmp_path.iterdir())) == archivos


def test_hu08_4_ilegible_queda_para_carga_manual(client, base, tmp_path) -> None:
    r = _ingesta(client, _pdf_ilegible())
    assert r.status_code == 201, r.text
    acta = r.json()
    assert acta["estado"] == "PENDIENTE_VALIDACION"
    assert acta["nro_acta"] is None
    assert acta["confianza_campos"] == {}
    assert any(tmp_path.iterdir())


# --- HU-09 --------------------------------------------------------------------------


def test_hu09_1_detalle_y_pdf(client, admin) -> None:
    pdf = _pdf_texto(_lineas(_nro(), "AE 512 KT", datetime(2026, 10, 6, 11, 47, tzinfo=AR)))
    acta = _ingesta(client, pdf).json()
    ruta = f"/api/v1/infracciones/{acta['id_infraccion']}"
    assert client.get(ruta, headers=admin).json()["umbral_confianza"] == 80
    r = client.get(f"{ruta}/pdf", headers=admin)
    assert (r.status_code, r.content) == (200, pdf)
    r = client.get(f"{ruta}/vista", headers=admin)
    assert (r.status_code, r.headers["content-type"]) == (200, "image/png")
    ids = [a["id_infraccion"] for a in client.get("/api/v1/infracciones", params={"estado": "PENDIENTE_VALIDACION"}, headers=admin).json()]
    assert acta["id_infraccion"] in ids


def test_hu09_3_patente_sin_unidad_informa_y_permite_rechazar(client, admin, fabrica_sesion) -> None:
    nro = _nro()
    acta = _ingesta(client, _pdf_texto(_lineas(nro, "ZZ 999 ZZ", datetime(2026, 10, 6, 11, 47, tzinfo=AR)))).json()
    ruta = f"/api/v1/infracciones/{acta['id_infraccion']}"
    assert client.get(ruta, headers=admin).json()["unidad_existente"] is False
    r = client.put(f"{ruta}/validar", json=_datos_validos(nro, "ZZ 999 ZZ"), headers=admin)
    assert (r.status_code, r.json()["codigo"]) == (409, "PATENTE_SIN_UNIDAD")
    r = client.put(f"{ruta}/rechazar", json={"motivo": "No es una unidad demo"}, headers=admin)
    assert (r.json()["estado"], r.json()["motivo_rechazo"]) == ("RECHAZADA", "No es una unidad demo")
    with fabrica_sesion() as ses:
        assert ses.scalars(select(Alerta).where(Alerta.id_infraccion == acta["id_infraccion"])).one().estado == "CERRADA"


def test_hu09_4_validar_corrige_y_registra_quien(client, sesion, hash_pruebas, mkt, base, fabrica_sesion) -> None:
    cab, usuario = _usuario(client, sesion, hash_pruebas, Rol.ADMINISTRACION)
    unidad = _alta(client, mkt)
    acta = _ingesta(client, _pdf_ilegible()).json()  # carga manual completa
    nro = _nro()
    r = client.put(f"/api/v1/infracciones/{acta['id_infraccion']}/validar", json=_datos_validos(nro, unidad["patente"].lower()), headers=cab)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["estado"], cuerpo["nro_acta"], cuerpo["id_unidad"]) == ("VALIDADA", nro, unidad["id"])
    assert cuerpo["validada_por"] == usuario.nombre
    assert cuerpo["fecha_validacion"] is not None
    with fabrica_sesion() as ses:
        alerta = ses.scalars(select(Alerta).where(Alerta.id_infraccion == acta["id_infraccion"])).one()
    assert (alerta.estado, alerta.id_usuario_cierre) == ("CERRADA", usuario.id)
    r = client.put(f"/api/v1/infracciones/{acta['id_infraccion']}/validar", json=_datos_validos(nro, unidad["patente"]), headers=cab)
    assert (r.status_code, r.json()["codigo"]) == (409, "ESTADO_ACTA_INVALIDO")


def test_validar_rechaza_numero_de_otra_acta_y_fecha_futura(client, admin, mkt) -> None:
    unidad = _alta(client, mkt)
    existente = _acta_validada(client, admin, unidad["patente"])
    acta = _ingesta(client, _pdf_ilegible()).json()
    ruta = f"/api/v1/infracciones/{acta['id_infraccion']}/validar"
    r = client.put(ruta, json=_datos_validos(existente["nro_acta"], unidad["patente"]), headers=admin)
    assert r.json()["codigo"] == "ACTA_DUPLICADA"
    futura = datetime.now(AR) + timedelta(hours=1)
    r = client.put(ruta, json=_datos_validos(_nro(), unidad["patente"], futura), headers=admin)
    assert r.json()["codigo"] == "FECHA_FUTURA"


def test_solo_administracion_gestiona_actas(client, mkt) -> None:
    assert client.get("/api/v1/infracciones", headers=mkt).status_code == 403


# --- HU-10 --------------------------------------------------------------------------


def test_hu10_1_y_3_imputa_al_asesor_en_uso_y_deja_evento(client, sesion, hash_pruebas, admin, mkt) -> None:
    unidad = _alta(client, mkt)
    cab_asesor, asesor = _usuario(client, sesion, hash_pruebas, Rol.ASESOR)
    client.post(f"/api/v1/unidades/{unidad['id']}/asignaciones", json={"id_responsable": asesor.id, "id_sucursal": "SC01"}, headers=mkt)
    r = client.post("/api/v1/usos/salida", json={"id_unidad": unidad["id"], "tipo_uso": "GIRA", "km_salida": 1000}, headers=cab_asesor)
    assert r.status_code == 201, r.text

    acta = _acta_validada(client, admin, unidad["patente"], datetime.now(AR))
    ruta = f"/api/v1/infracciones/{acta['id_infraccion']}"
    sugerencia = client.get(f"{ruta}/sugerencia", headers=admin).json()
    assert (sugerencia["tipo"], sugerencia["identificador"]) == ("USUARIO", asesor.id)
    assert (sugerencia["evento_tipo"], sugerencia["sin_responsable"]) == ("SALIDA", False)
    assert sugerencia["posicion"] == "sin posición"

    r = client.post(f"{ruta}/imputar", headers=admin)
    assert r.status_code == 200, r.text
    assert (r.json()["estado"], r.json()["responsable_nombre"]) == ("IMPUTADA", asesor.nombre)
    eventos = client.get(f"/api/v1/unidades/{unidad['id']}/historial", headers=mkt).json()["eventos"]
    assert eventos[0]["tipo_evento"] == "INFRACCION"
    assert eventos[0]["datos"]["nro_acta"] == acta["nro_acta"]
    assert client.get(f"/api/v1/unidades/{unidad['id']}", headers=mkt).json()["unidad"]["estado_actual"] == "EN_USO"

    assert client.post(f"{ruta}/imputar", headers=admin).status_code == 409
    assert client.post(f"{ruta}/pagar", headers=admin).json()["estado"] == "PAGADA"
    assert client.post(f"{ruta}/pagar", headers=admin).status_code == 409


def test_hu10_1_imputa_al_cliente_del_prestamo(client, sesion, hash_pruebas, admin) -> None:
    cab, _ = _usuario(client, sesion, hash_pruebas, Rol.RESP_POSVENTA)
    unidad = _alta(client, cab, "POSVENTA")
    r = client.post(
        "/api/v1/prestamos",
        json={
            "id_unidad": unidad["id"], "nro_orden_reparacion": "OR 1", "cliente_documento": f"20{next(_contador):09d}",
            "cliente_nombre": "Cliente Multado", "fecha_devolucion_prevista": (datetime.now(AR) + timedelta(days=2)).date().isoformat(),
            "km_entrega": 1000, "combustible_entrega": 6,
            "control_previo": dict.fromkeys(("service_al_dia", "documentacion_y_seguro", "sin_danos_visibles", "accesorios_completos"), True),
        },
        headers=cab,
    )
    assert r.status_code == 201, r.text
    acta = _acta_validada(client, admin, unidad["patente"], datetime.now(AR))
    r = client.post(f"/api/v1/infracciones/{acta['id_infraccion']}/imputar", headers=admin)
    assert r.json()["responsable_nombre"] == "Cliente Multado"


def test_hu10_4_sin_responsable_imputa_al_del_circuito_y_alerta(client, sesion, hash_pruebas, admin, mkt, fabrica_sesion) -> None:
    unidad = _alta(client, mkt)  # DISPONIBLE: nadie responde por ella
    acta = _acta_validada(client, admin, unidad["patente"], datetime.now(AR))
    ruta = f"/api/v1/infracciones/{acta['id_infraccion']}"
    sugerencia = client.get(f"{ruta}/sugerencia", headers=admin).json()
    assert sugerencia["sin_responsable"] is True
    r = client.post(f"{ruta}/imputar", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["responsable_nombre"] is not None
    with fabrica_sesion() as ses:
        tipos = ses.scalars(select(Alerta.tipo_alerta).where(Alerta.id_infraccion == acta["id_infraccion"], Alerta.estado == "ABIERTA")).all()
        responsable = ses.scalar(select(Usuario).where(Usuario.nombre == r.json()["responsable_nombre"]))
    assert tipos == ["SIN_RESPONSABLE"]
    assert responsable.rol is Rol.RESP_MKT_VENTAS


def test_sugerencia_exige_acta_validada(client, admin) -> None:
    acta = _ingesta(client, _pdf_ilegible()).json()
    assert client.get(f"/api/v1/infracciones/{acta['id_infraccion']}/sugerencia", headers=admin).status_code == 409


def test_acta_inexistente(client, admin) -> None:
    assert client.get("/api/v1/infracciones/999999", headers=admin).status_code == 404


# --- Alertas sin duplicar ------------------------------------------------------------


def test_alerta_abierta_no_se_duplica(sesion, fabrica_sesion, base, mkt, client) -> None:
    from app.core import alertas

    unidad = _alta(client, mkt)
    primera = alertas.generar(sesion, "SERVICE_PROXIMO", "uno", id_unidad=unidad["id"])
    segunda = alertas.generar(sesion, "SERVICE_PROXIMO", "dos", id_unidad=unidad["id"])
    sesion.commit()
    assert primera.id_alerta == segunda.id_alerta
    assert segunda.mensaje == "dos"
    alertas.cerrar(sesion, "SERVICE_PROXIMO", base.mkt, "Hecho", id_unidad=unidad["id"])
    tercera = alertas.generar(sesion, "SERVICE_PROXIMO", "tres", id_unidad=unidad["id"])
    sesion.commit()
    assert tercera.id_alerta != primera.id_alerta


# --- Acceso a unidades segun la Tabla 30 --------------------------------------------


def test_asesor_solo_ve_sus_unidades(client, sesion, hash_pruebas, mkt) -> None:
    propia, ajena = _alta(client, mkt), _alta(client, mkt)
    cab, asesor = _usuario(client, sesion, hash_pruebas, Rol.ASESOR)
    client.post(f"/api/v1/unidades/{propia['id']}/asignaciones", json={"id_responsable": asesor.id, "id_sucursal": "SC01"}, headers=mkt)
    assert [u["id"] for u in client.get("/api/v1/unidades", headers=cab).json()] == [propia["id"]]
    assert client.get(f"/api/v1/unidades/{propia['id']}", headers=cab).status_code == 200
    for ruta in ("", "/historial", "/responsable", "/asignaciones"):
        assert client.get(f"/api/v1/unidades/{ajena['id']}{ruta}", headers=cab).status_code == 403


def test_posventa_solo_ve_su_circuito(client, sesion, hash_pruebas, mkt) -> None:
    comercial = _alta(client, mkt)
    cab, _ = _usuario(client, sesion, hash_pruebas, Rol.RESP_POSVENTA)
    propia = _alta(client, cab, "POSVENTA")
    ids = [u["id"] for u in client.get("/api/v1/unidades", headers=cab).json()]
    assert propia["id"] in ids and comercial["id"] not in ids
    assert client.get(f"/api/v1/unidades/{comercial['id']}", headers=cab).status_code == 403
    recientes = [r["id"] for r in client.get("/api/v1/unidades/recientes", params={"limite": 50}, headers=cab).json()]
    assert comercial["id"] not in recientes


@pytest.mark.parametrize("rol", [Rol.GERENCIA, Rol.ADMINISTRACION])
def test_gerencia_y_administracion_consultan_todo_sin_operar(client, sesion, hash_pruebas, mkt, rol) -> None:
    unidad = _alta(client, mkt)
    cab, _ = _usuario(client, sesion, hash_pruebas, rol)
    assert client.get(f"/api/v1/unidades/{unidad['id']}/historial", headers=cab).status_code == 200
    assert client.post(f"/api/v1/unidades/{unidad['id']}/liberar", json={}, headers=cab).status_code == 403
