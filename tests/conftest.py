"""Fixtures de la suite: motor de base, tablas por prueba y cliente HTTP de prueba.

Sin Docker en el entorno de desarrollo, las pruebas de integracion usan SQLite como
huesped (los datos del motor de estados son portables); las caracteristicas exclusivas
de PostgreSQL (trigger de inmutabilidad, GRANTs, indice unico parcial) se prueban
directamente sobre la migracion 0001_nucleo.py y quedan cubiertas ademas por
`make demo` en una maquina con Docker.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from sqlalchemy import BigInteger, Integer, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "clave-de-prueba")
os.environ.setdefault("SYNC_DMS_CADA_MINUTOS", "0")

from app.core.db import Base, get_session  # noqa: E402
from app.core.seguridad import hash_clave  # noqa: E402
from app.identidad.models import Rol, Usuario  # noqa: E402
from app.tablas_generales.models import Cliente, Parametro, Sucursal  # noqa: E402

# Compatibilidad SQLite para tipos exclusivos de PostgreSQL (ver docs/decisiones.md)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(TIMESTAMP, "sqlite")
def _timestamp_sqlite(type_, compiler, **kw):
    return "DATETIME"


# SQLite no guarda la zona horaria: al releer, los datetimes vuelven "naive".
# `TimestampUTC` re-etiqueta como UTC al leer, y el listener convierte aware->naive-UTC
# al bindear parametros. Con eso el motor de estados, responsable_vigente y las pruebas
# comparables funcionan igual que en PostgreSQL. Las caracteristicas exclusivas de
# Postgres (FOR UPDATE real, trigger, GRANTs) se verifican sobre la migracion 0001 y
# quedan cubiertas por `make demo` (ver docs/decisiones.md).
from sqlalchemy import DateTime as SADateTime, event as sa_event  # noqa: E402
from sqlalchemy import inspect as sa_inspect  # noqa: E402
from sqlalchemy.types import TypeDecorator  # noqa: E402

import app.unidades.models  # noqa: E402,F401  (registra unidad_demo/evento_unidad/asignacion)


class TimestampUTC(TypeDecorator):
    """DateTime con zona: normaliza a aware-UTC al leer (portabilidad SQLite)."""

    impl = SADateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class BigIntAutoinc(TypeDecorator):
    """BigInteger con autoincremento: en SQLite el AUTOINCREMENT solo aplica a
    INTEGER PRIMARY KEY; en PostgreSQL delega en BIGSERIAL sin cambios."""

    impl = BigInteger
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(Integer)
        return dialect.type_descriptor(BigInteger())


def _aplicar_tipos_prueba() -> None:
    """Sustituye los tipos TIMESTAMP/DateTime(timezone=True) de los modelos por
    TimestampUTC y los BIGINT autoincrementales por BigIntAutoinc. Es inocuo en
    PostgreSQL (TypeDecorator pasa a traves del dialecto)."""
    from app.identidad.models import Usuario
    from app.tablas_generales.models import Auditoria
    from app.unidades.models import Asignacion, EventoUnidad, UnidadDemo

    for modelo in (Usuario, Auditoria, Asignacion, EventoUnidad, UnidadDemo):
        mapper = sa_inspect(modelo)
        for columna in mapper.columns:
            tipo = columna.type
            if isinstance(tipo, TIMESTAMP) or (
                isinstance(tipo, SADateTime) and getattr(tipo, "timezone", False)
            ):
                columna.type = TimestampUTC()
            elif isinstance(tipo, BigInteger) and mapper.primary_key and columna in mapper.primary_key:
                columna.type = BigIntAutoinc()


_aplicar_tipos_prueba()


@pytest.fixture()
def motor() -> Generator:
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def sesion(motor) -> Generator[Session, None, None]:
    with Session(motor) as s:
        yield s


@pytest.fixture()
def seed_basico(sesion: Session) -> Session:
    """Sucursales, parametros y usuarios minimos para las pruebas."""
    for codigo, nombre in [("CC", "Casa Central"), ("FOR", "Formosa"), ("SP", "Sáenz Peña"), ("USO", "División Usados")]:
        sesion.add(Sucursal(codigo=codigo, nombre=nombre))
    sesion.add_all(
        [
            Parametro(clave="plazo_rotacion_meses", valor="24", circuito="COMERCIAL"),
            Parametro(clave="plazo_rotacion_meses", valor="18", circuito="POSVENTA"),
            Parametro(clave="umbral_ocr", valor="80"),
            Parametro(clave="aviso_service_km", valor="500"),
            Parametro(clave="aviso_multa_dias", valor="5"),
            Parametro(clave="service_intervalo_km", valor="10000"),
        ]
    )
    clave = "DemoPass123!"
    usuarios = [
        Usuario(legajo="L001", correo="admin@demo.local", nombre="Admin Demo", rol=Rol.ADMIN, id_sucursal="CC", hash_clave=hash_clave(clave)),
        Usuario(legajo="L002", correo="mkt@demo.local", nombre="Rosa Mercado", rol=Rol.RESP_MKT_VENTAS, id_sucursal="CC", hash_clave=hash_clave(clave)),
        Usuario(legajo="L003", correo="asesor@demo.local", nombre="Ana Asesora", rol=Rol.ASESOR, id_sucursal="CC", hash_clave=hash_clave(clave)),
        Usuario(legajo="L004", correo="posventa@demo.local", nombre="Pedro Posventa", rol=Rol.RESP_POSVENTA, id_sucursal="CC", hash_clave=hash_clave(clave)),
        Usuario(legajo="L005", correo="baja@demo.local", nombre="Baja DMS", rol=Rol.ASESOR, id_sucursal="CC", hash_clave=hash_clave(clave), activo=False),
        Usuario(legajo="L006", correo="tecnico@demo.local", nombre="Tecnico N8N", rol=Rol.TECNICO, id_sucursal="CC", hash_clave=hash_clave(clave)),
    ]
    sesion.add_all(usuarios)
    sesion.add(Cliente(documento="20-00000001-9", nombre="Cliente Ficticio", contacto="tel 000"))
    sesion.commit()
    return sesion


@pytest.fixture()
def client(seed_basico: Session):
    """TestClient con la dependencia de sesion redirigida al motor de prueba."""
    from fastapi.testclient import TestClient

    from app.main import crear_aplicacion

    app = crear_aplicacion(sin_planificador=True)

    def _sesion_prueba() -> Generator[Session, None, None]:
        yield seed_basico

    app.dependency_overrides[get_session] = _sesion_prueba
    with TestClient(app) as c:
        yield c


def token_para(client, correo: str, clave: str = "DemoPass123!") -> str:
    r = client.post("/api/v1/auth/ingresar", json={"correo": correo, "clave": clave})
    assert r.status_code == 200, r.text
    return r.json()["token"]
