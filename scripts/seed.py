"""Semilla inicial de la demo: sedes, parametros, usuarios y unidades.

Los eventos de la semilla se generan a traves del motor de estados (nunca con inserts
directos). Reejecutable: si algo ya existe, no lo duplica. Datos ficticios (Ley 25.326).
Solo corre con ENTORNO=demo: en produccion las cuentas se crean desde el DMS.
"""

from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from sqlalchemy import select  # noqa: E402

from app.core import estados  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.seguridad import hash_clave  # noqa: E402
from app.identidad.models import Rol, Usuario  # noqa: E402
from app.tablas_generales.models import Parametro, Sucursal  # noqa: E402
from app.unidades.models import Circuito, UnidadDemo  # noqa: E402
from app.unidades.service import alta_unidad  # noqa: E402

SEDES = [
    ("SC01", "Casa Central"),
    ("SC02", "Formosa"),
    ("SC03", "Sáenz Peña"),
    ("SC04", "División Usados"),
]

PARAMETROS = [
    ("plazo_rotacion_meses", "COMERCIAL", None, "6"),
    ("plazo_rotacion_meses", "POSVENTA", None, "12"),
    ("umbral_ocr", None, None, "80"),
    ("aviso_service_km", None, None, "500"),
    ("service_intervalo_km", None, None, "10000"),
    ("aviso_multa_dias", None, None, "5"),
    ("duracion_token_horas", None, None, "8"),
    ("intentos_maximos", None, None, "5"),
]

USUARIOS = [
    # legajo, correo, nombre, rol, sucursal, variable de entorno con la clave, clave temporal del README
    ("1001", "admin@demo.local", "Ana Administradora", Rol.ADMIN, "SC01", "DEMO_CLAVE_ADMIN", "DemoAdmin2026!"),
    ("1002", "mkt@demo.local", "Marta Marketing", Rol.RESP_MKT_VENTAS, "SC01", "DEMO_CLAVE_MARKETING", "DemoMkt2026!"),
    ("1003", "asesor@demo.local", "Alberto Asesor", Rol.ASESOR, "SC02", "DEMO_CLAVE_ASESOR", "DemoAsesor2026!"),
    ("1004", "posventa@demo.local", "Paula Posventa", Rol.RESP_POSVENTA, "SC01", "DEMO_CLAVE_POSVENTA", "DemoPosventa2026!"),
    ("1005", "taller@demo.local", "Tomas Taller", Rol.TECNICO_TALLER, "SC03", "DEMO_CLAVE_TALLER", "DemoTaller2026!"),
    ("1006", "usados@demo.local", "Uriel Usados", Rol.RESP_USADOS, "SC04", "DEMO_CLAVE_USADOS", "DemoUsados2026!"),
]

# 15 unidades Ford del mercado argentino, repartidas entre circuitos
UNIDADES = [
    # patente, vin, modelo, version, circuito, sucursal, km
    ("AA001BB", "1FTFW1E80PFA00001", "Ranger", "XLS 4x4 CD 3.2", Circuito.COMERCIAL, "SC01", 12500),
    ("AB002CD", "1FTFW1E80PFA00002", "Ranger", "Limited 4x4 CD 3.0T", Circuito.COMERCIAL, "SC01", 9800),
    ("AC003DE", "1FTFW1E80PFA00003", "Ranger", "Wildtrak 4x4 CD 3.0T", Circuito.COMERCIAL, "SC02", 15300),
    ("AD004EF", "1FMUK8DH5SGA00004", "Explorer", "Limited 3.3 Hybrid", Circuito.COMERCIAL, "SC02", 7400),
    ("AE005FG", "1FMCU9JZ0NUA00005", "Bronco Sport", "Badlands 2.0T 4x4", Circuito.COMERCIAL, "SC03", 11200),
    ("AF006GH", "1FMCU9JZ0NUA00006", "Bronco Sport", "Big Bend 1.5T", Circuito.COMERCIAL, "SC01", 5600),
    ("AG007HI", "WF0XXXTG0KTA00007", "Kuga", "ST-Line 2.5 Hybrid", Circuito.COMERCIAL, "SC02", 8900),
    ("AH008IJ", "MAJKL1FHXNNA00008", "Territory", "Titanium 1.5T", Circuito.COMERCIAL, "SC03", 6700),
    ("AI009JK", "MAJKL1FHXNNA00009", "Territory", "Sport 1.5T", Circuito.COMERCIAL, "SC04", 13400),
    ("AJ010KL", "1FTER4FH2LLA00010", "Maverick", "Lariat 2.0T AWD", Circuito.COMERCIAL, "SC01", 4300),
    ("AK011LM", "1FMUK8KH7SEA00011", "Everest", "Limited 3.0T 4x4", Circuito.POSVENTA, "SC01", 18200),
    ("AL012MN", "1FMUK8KH7SEA00012", "Everest", "Sport 3.0T 4x4", Circuito.POSVENTA, "SC02", 16800),
    ("AM013NO", "NM0AX9KB2M1A00013", "Transit", "Van Larga 2.2 TDCi", Circuito.POSVENTA, "SC01", 22400),
    ("AN014OP", "1FTFW1E80PFA00014", "Ranger", "Raptor 3.0T V6", Circuito.POSVENTA, "SC03", 9100),
    ("AO015PQ", "1FTER4FH2LLA00015", "Maverick", "XLT 2.0T AWD", Circuito.POSVENTA, "SC04", 10700),
]

CLIENTES = [
    ("30111222334", "Concesionaria El Faro S.A.", "contacto@elfaro.example"),
    ("27111222335", "María López Test", "maria.lopez@example.com"),
    ("20222333445", "Juan Pérez Test", "jperez@example.com"),
]


class EntornoNoDemo(SystemExit):
    """La semilla se niega a correr fuera de ENTORNO=demo."""


def sembrar() -> None:
    if settings.entorno != "demo":
        raise EntornoNoDemo(
            f"La semilla solo corre con ENTORNO=demo (actual: {settings.entorno}). "
            "En produccion las cuentas se crean desde el DMS con contraseña temporal."
        )
    sesion = SessionLocal()
    try:
        for codigo, nombre in SEDES:
            if sesion.scalar(select(Sucursal).where(Sucursal.codigo == codigo)) is None:
                sesion.add(Sucursal(codigo=codigo, nombre=nombre))
        sesion.flush()

        for clave, circuito, id_sucursal, valor in PARAMETROS:
            existe = sesion.scalar(
                select(Parametro).where(Parametro.clave == clave, Parametro.circuito == circuito)
            )
            if existe is None:
                sesion.add(Parametro(clave=clave, valor=valor, circuito=circuito, id_sucursal=id_sucursal))

        # Cuentas de demo (es_demo): sin cambio de clave obligatorio en el primer ingreso para
        # que el guion no se corte; el resto de la politica de seguridad se aplica igual.
        for legajo, correo, nombre, rol, sucursal, var_env, clave_readme in USUARIOS:
            existente = sesion.scalar(select(Usuario).where(Usuario.correo == correo))
            if existente is None:
                clave = os.environ.get(var_env) or clave_readme
                sesion.add(
                    Usuario(
                        legajo=legajo,
                        correo=correo,
                        nombre=nombre,
                        rol=rol,
                        id_sucursal=sucursal,
                        hash_clave=hash_clave(clave),
                        debe_cambiar_clave=False,
                        es_demo=True,
                    )
                )
            elif not existente.es_demo:  # cuentas creadas antes de existir es_demo
                existente.es_demo = True
                existente.debe_cambiar_clave = False
        # usuario tecnico n8n: autenticado solo por API key; clave aleatoria que nadie conoce
        if sesion.scalar(select(Usuario).where(Usuario.legajo == "9000")) is None:
            sesion.add(
                Usuario(
                    legajo="9000",
                    correo="tecnico-n8n@demo.local",
                    nombre="Usuario Técnico n8n",
                    rol=Rol.TECNICO,
                    id_sucursal="SC01",
                    hash_clave=hash_clave(secrets.token_urlsafe(32)),
                    debe_cambiar_clave=False,
                )
            )
        from app.tablas_generales.models import Cliente

        for documento, nombre, contacto in CLIENTES:
            if sesion.scalar(select(Cliente).where(Cliente.documento == documento)) is None:
                sesion.add(Cliente(documento=documento, nombre=nombre, contacto=contacto))
        sesion.flush()

        mkt = sesion.scalar(select(Usuario).where(Usuario.legajo == "1002"))
        ahora = datetime.now(timezone.utc)
        for i, (patente, vin, modelo, version, circuito, sucursal, km) in enumerate(UNIDADES):
            if sesion.scalar(select(UnidadDemo).where(UnidadDemo.patente == patente)) is None:
                alta_unidad(
                    sesion,
                    vin=vin,
                    patente=patente,
                    modelo=modelo,
                    version=version,
                    circuito=circuito,
                    id_sucursal=sucursal,
                    km_inicial=km,
                    usuario=mkt,
                    origen=estados.Origen.WEB,
                    fecha_hora=ahora - timedelta(days=45 - i),
                )
        sesion.commit()
        print("== semilla aplicada ==")
    finally:
        sesion.close()


if __name__ == "__main__":
    sembrar()
