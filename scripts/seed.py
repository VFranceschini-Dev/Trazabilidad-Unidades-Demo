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

from app.comercial.models import TipoUso  # noqa: E402
from app.comercial.service import registrar_regreso, registrar_salida  # noqa: E402
from app.core import estados  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.seguridad import hash_clave  # noqa: E402
from app.identidad.models import Rol, Usuario  # noqa: E402
from app.tablas_generales.models import Parametro, Sucursal  # noqa: E402
from app.unidades.models import Circuito, UnidadDemo  # noqa: E402
from app.posventa.service import ITEMS_CONTROL_PREVIO, registrar_devolucion, registrar_entrega  # noqa: E402
from app.unidades.models import EventoUnidad  # noqa: E402
from app.unidades.service import alta_unidad, asignar  # noqa: E402

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
    ("1008", "asesor.central@demo.local", "Carla Central", Rol.ASESOR, "SC01", "DEMO_CLAVE_ASESOR_CENTRAL", "DemoCentral2026!"),
    ("1009", "asesor.saenz@demo.local", "Sergio Saenz", Rol.ASESOR, "SC03", "DEMO_CLAVE_ASESOR_SAENZ", "DemoSaenz2026!"),
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


# Proximo service de las unidades de Posventa; AO015PQ queda vencida para mostrar el bloqueo (HU-05.2)
PROXIMO_SERVICE = {"AK011LM": 25000, "AL012MN": 25000, "AM013NO": 30000, "AN014OP": 15000, "AO015PQ": 10500}

# Patente -> (dia de asignacion y usos: dias hacia atras, tipo, km recorridos)
USOS = {
    "AA001BB": [(26, TipoUso.GIRA, 310), (19, TipoUso.TEST_DRIVE, 25), (11, TipoUso.EVENTO, 60), (4, TipoUso.GUARDIA, 18)],
    "AB002CD": [(24, TipoUso.TEST_DRIVE, 30), (15, TipoUso.GUARDIA, 12), (6, TipoUso.GIRA, 420)],
    "AC003DE": [(27, TipoUso.GIRA, 280), (17, TipoUso.TEST_DRIVE, 22), (8, TipoUso.EVENTO, 75)],
    "AD004EF": [(23, TipoUso.TEST_DRIVE, 28), (12, TipoUso.GUARDIA, 15), (1, TipoUso.GIRA, None)],  # sigue en uso
    "AE005FG": [(25, TipoUso.EVENTO, 90), (13, TipoUso.TEST_DRIVE, 35), (5, TipoUso.GIRA, 260)],
    "AF006GH": [(20, TipoUso.GUARDIA, 10), (9, TipoUso.TEST_DRIVE, 20)],
    "AG007HI": [(22, TipoUso.GIRA, 350), (10, TipoUso.GUARDIA, 14)],
    "AH008IJ": [(21, TipoUso.TEST_DRIVE, 26), (7, TipoUso.EVENTO, 55)],
    "AJ010KL": [(18, TipoUso.GIRA, 190), (3, TipoUso.TEST_DRIVE, 24)],
}
RESPONSABLE_POR_SUCURSAL = {"SC01": "1008", "SC02": "1003", "SC03": "1009"}

# Patente -> prestamos: documento, dias de entrega y devolucion hacia atras (None: sigue abierto),
# dias de la fecha prevista respecto de hoy, km recorridos y danos
PRESTAMOS = {
    "AK011LM": [("20222333445", 26, 21, -22, 180, None), ("27111222335", 14, 9, -9, 240, "Rayón en paragolpes trasero")],
    "AL012MN": [("20222333445", 18, 15, -15, 95, None), ("27111222335", 6, None, -2, 0, None)],  # demorado
    "AM013NO": [("30111222334", 1, None, 3, 0, None)],
    "AN014OP": [("27111222335", 12, 8, -8, 150, None)],
}


def _sin_movimientos(sesion, unidad: UnidadDemo) -> bool:
    """Solo se siembra historia en unidades que todavia tienen unicamente su ALTA."""
    return (
        sesion.scalar(
            select(EventoUnidad.id_evento)
            .where(EventoUnidad.id_unidad == unidad.id, EventoUnidad.tipo_evento != estados.TipoEvento.ALTA.value)
            .limit(1)
        )
        is None
    )


def sembrar_historia(sesion, ahora: datetime) -> None:
    """Unos 30 dias de usos y prestamos con carga diferida, siempre por los servicios y el motor."""
    usuarios = {u.legajo: u for u in sesion.scalars(select(Usuario))}
    mkt, posventa = usuarios["1002"], usuarios["1004"]
    unidades = {u.patente: u for u in sesion.scalars(select(UnidadDemo))}

    for patente, proximo in PROXIMO_SERVICE.items():
        unidades[patente].km_proximo_service = proximo

    for patente, usos in USOS.items():
        unidad = unidades[patente]
        if not _sin_movimientos(sesion, unidad):
            continue
        asesor = usuarios[RESPONSABLE_POR_SUCURSAL[unidad.id_sucursal]]
        asignar(
            sesion, unidad.id, id_responsable=asesor.id, id_sucursal=unidad.id_sucursal, usuario=mkt,
            motivo="Demanda comercial de la zona", fecha_hora=ahora - timedelta(days=29),
        )
        for i, (dias, tipo, recorrido) in enumerate(usos):
            prospecto = {}
            if tipo is TipoUso.TEST_DRIVE:
                prospecto = {"cliente_nombre": f"Prospecto {patente[:2]}{i}", "cliente_telefono": f"362-400000{i}"}
            salida = ahora - timedelta(days=dias, hours=3)
            _, uso = registrar_salida(
                sesion, unidad.id, tipo_uso=tipo, km_salida=unidad.km_actual, usuario=asesor, fecha_hora=salida, **prospecto
            )
            if recorrido is not None:
                registrar_regreso(
                    sesion, uso.id_uso, km_regreso=uso.km_salida + recorrido, usuario=asesor,
                    fecha_hora=salida + timedelta(hours=2),
                )

    control = dict.fromkeys(ITEMS_CONTROL_PREVIO, True)
    for patente, prestamos in PRESTAMOS.items():
        unidad = unidades[patente]
        if not _sin_movimientos(sesion, unidad):
            continue
        for i, (documento, dias_entrega, dias_devolucion, prevista, recorrido, danos) in enumerate(prestamos):
            _, prestamo = registrar_entrega(
                sesion, unidad.id, nro_orden_reparacion=f"OR {55100 + unidad.id * 10 + i}", cliente_documento=documento,
                fecha_devolucion_prevista=(ahora + timedelta(days=max(prevista, -dias_entrega))).date(),
                km_entrega=unidad.km_actual, combustible_entrega=6, control_previo=control, usuario=posventa,
                fecha_hora=ahora - timedelta(days=dias_entrega),
            )
            if dias_devolucion is not None:
                registrar_devolucion(
                    sesion, prestamo.id_prestamo, km_devolucion=prestamo.km_entrega + recorrido, combustible_devolucion=5,
                    estado_devolucion=danos or "Sin novedades", con_danos=danos is not None, usuario=posventa,
                    fecha_hora=ahora - timedelta(days=dias_devolucion),
                )


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
        sesion.flush()
        sembrar_historia(sesion, ahora)
        sesion.commit()
        print("== semilla aplicada ==")
    finally:
        sesion.close()


if __name__ == "__main__":
    sembrar()
