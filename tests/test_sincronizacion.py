"""HU-15: sincronizacion con el DMS mediante adaptadores falsos, HTTP simulado y CSV.

No se sincroniza contra los empleados reales del DMS simulado: sus legajos coinciden con
los del fixture `base` y alterarian a los usuarios compartidos de la suite.
"""

from __future__ import annotations

import itertools
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.identidad.models import Rol, Usuario
from app.sincronizacion.dms import DMSDesdeCSV, DMSDesdeHTTP, EmpleadoDMS, ErrorDMS, UnidadDMS
from app.sincronizacion.service import sincronizar
from app.tablas_generales.models import Auditoria
from app.unidades.models import EventoUnidad, UnidadDemo

_contador = itertools.count(1)
RESPALDO = Path(__file__).resolve().parents[1] / "datos_demo" / "dms_respaldo.csv"


class DMSFalso:
    def __init__(self, empleados: list[EmpleadoDMS] | None = None, unidades: list[UnidadDMS] | None = None) -> None:
        self.empleados = empleados or []
        self.unidades = unidades or []
        self.caido = False

    def traer_empleados(self) -> list[EmpleadoDMS]:
        if self.caido:
            raise ErrorDMS("DMS indisponible")
        return self.empleados

    def traer_unidades(self) -> list[UnidadDMS]:
        return self.unidades


def _empleado(**extra: Any) -> EmpleadoDMS:
    n = next(_contador)
    datos = {
        "legajo": f"5{n:04d}",
        "nombre": f"Empleado {n}",
        "correo": f"dms{n}@pruebas.local",
        "id_sucursal": "SC01",
        "rol": "ASESOR",
        "activo": True,
    }
    return EmpleadoDMS(**{**datos, **extra})


def _unidad() -> UnidadDMS:
    n = next(_contador)
    return UnidadDMS(
        vin=f"1FTFW1E80PFD{n:05d}",
        patente=f"DM{n:04d}S",
        modelo="Ranger",
        version="XLS",
        circuito="COMERCIAL",
        id_sucursal="SC01",
        km_actual=20,
    )


def _usuario(fabrica_sesion: Any, legajo: str) -> Usuario:
    with fabrica_sesion() as ses:
        return ses.scalar(select(Usuario).where(Usuario.legajo == legajo))


def _reemplazar(emp: EmpleadoDMS, **extra: Any) -> EmpleadoDMS:
    return EmpleadoDMS(**{**emp.__dict__, **extra})


def test_crea_empleado_con_clave_temporal_por_correo(sesion, fabrica_sesion, base, client, monkeypatch) -> None:
    enviados: list[tuple[str, str, str]] = []
    monkeypatch.setattr("app.core.correo.enviar", lambda *m: enviados.append(m) or True)
    emp = _empleado(rol="RESP_POSVENTA", id_sucursal="SC02")
    resultado = sincronizar(sesion, DMSFalso([emp]), None)
    assert (resultado.creados, resultado.error) == (1, None)
    usuario = _usuario(fabrica_sesion, emp.legajo)
    assert usuario.rol is Rol.RESP_POSVENTA
    assert usuario.id_sucursal == "SC02"
    assert usuario.debe_cambiar_clave is True
    faltan = usuario.clave_temporal_hasta - datetime.now(timezone.utc)
    assert timedelta(hours=47) < faltan <= timedelta(hours=48)

    [(destino, _, cuerpo)] = enviados
    assert destino == emp.correo
    temporal = re.search(r"temporal es: (\S+)", cuerpo).group(1)
    r = client.post("/api/v1/auth/ingresar", json={"correo": emp.correo, "clave": temporal})
    assert r.status_code == 200
    assert r.json()["debe_cambiar_clave"] is True


def test_empleado_inactivo_no_recibe_clave(sesion, base, monkeypatch) -> None:
    enviados: list[tuple[str, str, str]] = []
    monkeypatch.setattr("app.core.correo.enviar", lambda *m: enviados.append(m) or True)
    sincronizar(sesion, DMSFalso([_empleado(activo=False)]), None)
    assert enviados == []


def test_correo_caido_no_rompe_la_sincronizacion(sesion, fabrica_sesion, base, monkeypatch) -> None:
    def falla(*_: Any, **__: Any) -> None:
        raise OSError("sin servidor")

    monkeypatch.setattr("smtplib.SMTP", falla)
    emp = _empleado()
    assert sincronizar(sesion, DMSFalso([emp]), None).error is None
    assert _usuario(fabrica_sesion, emp.legajo) is not None


def test_rol_desconocido_se_crea_como_asesor(sesion, fabrica_sesion, base) -> None:
    emp = _empleado(rol="OTRO")
    sincronizar(sesion, DMSFalso([emp]), None)
    assert _usuario(fabrica_sesion, emp.legajo).rol is Rol.ASESOR


def test_actualiza_datos_del_empleado(sesion, fabrica_sesion, base) -> None:
    emp = _empleado()
    sincronizar(sesion, DMSFalso([emp]), None)
    cambiado = _reemplazar(emp, nombre="Otro Nombre", correo="nuevo.dms@pruebas.local", id_sucursal="SC03", rol="GERENCIA")
    assert sincronizar(sesion, DMSFalso([cambiado]), None).actualizados == 1
    usuario = _usuario(fabrica_sesion, emp.legajo)
    assert (usuario.nombre, usuario.correo, usuario.id_sucursal, usuario.rol) == (
        "Otro Nombre",
        "nuevo.dms@pruebas.local",
        "SC03",
        Rol.GERENCIA,
    )


def test_sin_cambios_no_cuenta_actualizaciones(sesion, base) -> None:
    """Regresion: rol leido como texto contra enum marcaba a todos como actualizados."""
    emp = _empleado()
    sincronizar(sesion, DMSFalso([emp]), None)
    assert sincronizar(sesion, DMSFalso([emp]), None).actualizados == 0


def test_baja_deja_inactivo_y_conserva_historial(client, sesion, fabrica_sesion, base) -> None:
    """HU-15.2 y HU-01.4: inactivo, sin borrar el historial, y no puede ingresar."""
    emp = _empleado()
    falso = DMSFalso([emp], [_unidad()])
    sincronizar(sesion, falso, None)
    usuario = _usuario(fabrica_sesion, emp.legajo)

    resultado = sincronizar(sesion, DMSFalso([_reemplazar(emp, activo=False)]), None)
    assert resultado.dados_de_baja == 1
    assert _usuario(fabrica_sesion, emp.legajo).activo is False
    assert _usuario(fabrica_sesion, emp.legajo).id == usuario.id
    r = client.post("/api/v1/auth/ingresar", json={"correo": emp.correo, "clave": "cualquiera"})
    assert r.status_code == 401

    # Vuelve a estar activo en el DMS: se reactiva sin contarse como baja
    resultado = sincronizar(sesion, DMSFalso([emp]), None)
    assert (resultado.dados_de_baja, resultado.actualizados) == (0, 1)
    assert _usuario(fabrica_sesion, emp.legajo).activo is True


def test_error_de_comunicacion_se_registra_y_reintenta(sesion, fabrica_sesion, base) -> None:
    """HU-15.3: registra el error, no cambia datos y el ciclo siguiente funciona."""
    emp = _empleado()
    falso = DMSFalso([emp])
    falso.caido = True
    resultado = sincronizar(sesion, falso, base.admin)
    assert resultado.error == "DMS indisponible"
    assert _usuario(fabrica_sesion, emp.legajo) is None
    with fabrica_sesion() as ses:
        ultima = ses.scalars(
            select(Auditoria).where(Auditoria.accion == "SYNC_DMS").order_by(Auditoria.id.desc())
        ).first()
    assert (ultima.resultado, ultima.id_usuario) == ("FRACASO", base.admin.id)

    falso.caido = False
    assert sincronizar(sesion, falso, None).creados == 1


def test_unidad_nueva_entra_por_el_motor_y_la_repetida_se_omite(sesion, fabrica_sesion, base) -> None:
    uni = _unidad()
    resultado = sincronizar(sesion, DMSFalso(unidades=[uni]), None)
    assert resultado.unidades_alta == 1
    with fabrica_sesion() as ses:
        unidad = ses.scalar(select(UnidadDemo).where(UnidadDemo.vin == uni.vin))
        evento = ses.scalar(select(EventoUnidad).where(EventoUnidad.id_unidad == unidad.id))
    assert unidad.estado_actual == "DISPONIBLE"
    assert (evento.tipo_evento, evento.origen) == ("ALTA", "DMS")

    resultado = sincronizar(sesion, DMSFalso(unidades=[uni]), None)
    assert (resultado.unidades_alta, resultado.unidades_omitidas) == (0, 1)


def test_ruta_manual_informa_el_error_del_dms(client, sesion, hash_pruebas, base) -> None:
    r = client.post("/api/v1/auth/ingresar", json={"correo": base.admin.correo, "clave": "Demo-Pruebas-2026!"})
    r = client.post(
        "/api/v1/sincronizacion/dms",
        params={"fallar": True},
        headers={"Authorization": f"Bearer {r.json()['token']}"},
    )
    assert r.status_code == 200, r.text
    assert "No se pudo comunicar con el DMS" in r.json()["error"]


def test_adaptador_http_interpreta_las_filas(monkeypatch) -> None:
    filas = {
        "http://dms/empleados": [
            {"legajo": 1, "nombre": "A", "correo": "A@X.LOCAL", "id_sucursal": "SC01", "rol": "ADMIN", "activo": True}
        ],
        "http://dms/unidades": [
            {"vin": "abc", "patente": "P", "modelo": "M", "version": "V", "circuito": "POSVENTA", "id_sucursal": "SC02", "km_actual": "7"}
        ],
    }

    def falso_get(url: str, timeout: int) -> httpx.Response:
        return httpx.Response(200, json=filas[url], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", falso_get)
    adaptador = DMSDesdeHTTP("http://dms/")
    assert adaptador.traer_empleados()[0].correo == "a@x.local"
    assert adaptador.traer_empleados()[0].legajo == "1"
    assert adaptador.traer_unidades()[0].vin == "ABC"
    assert adaptador.traer_unidades()[0].km_actual == 7


def test_adaptador_http_traduce_errores_a_error_dms(monkeypatch) -> None:
    def caido(url: str, timeout: int) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(httpx, "get", caido)
    with pytest.raises(ErrorDMS, match="No se pudo comunicar"):
        DMSDesdeHTTP("http://dms").traer_empleados()


def test_respaldo_csv_del_repositorio_coincide_con_el_dms_simulado() -> None:
    adaptador = DMSDesdeCSV(RESPALDO)
    empleados = {e.legajo: e for e in adaptador.traer_empleados()}
    assert len(empleados) == 9
    assert empleados["1002"].rol == "RESP_MKT_VENTAS"
    assert empleados["1007"].activo is False
    assert adaptador.traer_unidades() == []


def test_adaptador_csv_lee_unidades(tmp_path) -> None:
    ruta = tmp_path / "dms.csv"
    ruta.write_text(
        "tipo,legajo,nombre,correo,id_sucursal,rol,activo,vin,patente,modelo,version,circuito,km_actual\n"
        "UNIDAD,,,,SC01,,,abc,P1,Ranger,XLS,COMERCIAL,15\n",
        encoding="utf-8",
    )
    adaptador = DMSDesdeCSV(ruta)
    assert adaptador.traer_empleados() == []
    unidad = adaptador.traer_unidades()[0]
    assert (unidad.vin, unidad.km_actual) == ("ABC", 15)


def test_adaptador_csv_sin_archivo_es_error_de_dms(tmp_path) -> None:
    with pytest.raises(ErrorDMS, match="No existe el respaldo"):
        DMSDesdeCSV(tmp_path / "no.csv").traer_empleados()
