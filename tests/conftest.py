"""Fixtures de pruebas: base PostgreSQL efimera en el servicio `db` (nunca SQLite).

Al iniciar la sesion se crea la base `demo_unidades_test`, se migran las tablas con el
rol dueño (`DATABASE_URL_MIGRACIONES`) y se otorgan al rol de aplicacion (`demo_app`)
los mismos permisos que en produccion; al terminar se elimina la base completa.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

DUENO = os.environ.get("DEMO_DB_OWNER", "demo_migraciones")
DUENO_CLAVE = os.environ["DEMO_DB_OWNER_PASSWORD"]
APP_USUARIO = os.environ.get("DEMO_DB_APP_USER", "demo_app")
APP_CLAVE = os.environ["DEMO_DB_APP_PASSWORD"]
HOST = os.environ.get("TEST_DB_HOST", "db")
BD_TEST = os.environ.get("TEST_DB_NAME", "demo_unidades_test")
BACKEND_DIR = os.environ.get("BACKEND_DIR", "/srv/backend")

URL_DUENO_TEST = f"postgresql+psycopg://{DUENO}:{DUENO_CLAVE}@{HOST}:5432/{BD_TEST}"
URL_APP_TEST = f"postgresql+psycopg://{APP_USUARIO}:{APP_CLAVE}@{HOST}:5432/{BD_TEST}"
URL_MANTENIMIENTO = f"postgresql+psycopg://{DUENO}:{DUENO_CLAVE}@{HOST}:5432/postgres"


def _crear_base() -> None:
    motor = create_engine(URL_MANTENIMIENTO, isolation_level="AUTOCOMMIT")
    with motor.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {BD_TEST} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {BD_TEST}"))
    motor.dispose()


def _eliminar_base() -> None:
    motor = create_engine(URL_MANTENIMIENTO, isolation_level="AUTOCOMMIT")
    with motor.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {BD_TEST} WITH (FORCE)"))
    motor.dispose()


@pytest.fixture(scope="session")
def bd_test() -> Iterator[dict[str, str]]:
    """Base de pruebas migrada y con permisos del rol de aplicacion otorgados."""
    _crear_base()
    # Volumenes inicializados con el init antiguo tenian la clave de demo_app hardcodeada:
    # se alinea el rol con DEMO_DB_APP_PASSWORD (el mismo que usa la API via compose).
    # ALTER ROLE no admite parametros ($1): se escapa el literal a mano.
    clave_sql = APP_CLAVE.replace("'", "''")
    dueno_mant = create_engine(URL_MANTENIMIENTO, isolation_level="AUTOCOMMIT")
    with dueno_mant.connect() as conn:
        conn.execute(text(f"ALTER ROLE {APP_USUARIO} WITH LOGIN PASSWORD '{clave_sql}'"))
    dueno_mant.dispose()
    # Mismos permisos que produccion: los privilegios por defecto (equivalentes a
    # init_db_roles.sh) se otorgan ANTES de migrar; la migracion 0002 revoca UPDATE y
    # DELETE sobre evento_unidad y otorga el uso de secuencias.
    dueno = create_engine(URL_DUENO_TEST, isolation_level="AUTOCOMMIT")
    with dueno.connect() as conn:
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_USUARIO}"))
        conn.execute(
            text(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA public"
                f" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_USUARIO}"
            )
        )
        conn.execute(
            text(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA public"
                f" GRANT USAGE, SELECT ON SEQUENCES TO {APP_USUARIO}"
            )
        )
    dueno.dispose()
    entorno = dict(
        os.environ,
        DATABASE_URL=URL_APP_TEST,
        DATABASE_URL_MIGRACIONES=URL_DUENO_TEST,
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=entorno,
        check=True,
    )
    yield {"dueno": URL_DUENO_TEST, "app": URL_APP_TEST}
    _eliminar_base()


@pytest.fixture(scope="session")
def motor_app(bd_test: dict[str, str]) -> Iterator[Engine]:
    """Motor con el rol de aplicacion, igual que la API en produccion."""
    motor = create_engine(URL_APP_TEST, pool_pre_ping=True)
    yield motor
    motor.dispose()


@pytest.fixture(scope="session")
def fabrica_sesion(motor_app: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=motor_app, expire_on_commit=False, autoflush=False)


@pytest.fixture()
def sesion(fabrica_sesion: sessionmaker[Session]) -> Iterator[Session]:
    ses = fabrica_sesion()
    try:
        yield ses
    finally:
        ses.close()


@pytest.fixture(scope="session")
def motor_dueno(bd_test: dict[str, str]) -> Iterator[Engine]:
    """Motor con el rol dueno: permite intentar modificaciones que el trigger rechaza
    (el rol de aplicacion ya no tiene UPDATE ni DELETE sobre evento_unidad)."""
    motor = create_engine(bd_test["dueno"], pool_pre_ping=True)
    yield motor
    motor.dispose()


@pytest.fixture()
def sesion_dueno(motor_dueno: Engine) -> Iterator[Session]:
    ses = sessionmaker(bind=motor_dueno, expire_on_commit=False, autoflush=False)()
    try:
        yield ses
    finally:
        ses.close()


@pytest.fixture(scope="session")
def client(bd_test: dict[str, str]):
    """Cliente HTTP de la API real (FastAPI) contra la base de pruebas."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def hash_pruebas() -> str:
    """Hash bcrypt unico para todos los usuarios de prueba (costo 12, se calcula una vez)."""
    from app.core.seguridad import hash_clave

    return hash_clave("Demo-Pruebas-2026!")


@pytest.fixture(scope="session")
def base(fabrica_sesion: sessionmaker[Session], hash_pruebas: str):
    """Datos base de la sesion: sedes, parametros y un usuario por rol de prueba."""
    from types import SimpleNamespace

    from app.identidad.models import Rol, Usuario
    from app.tablas_generales.models import Parametro, Sucursal

    ses = fabrica_sesion()
    for codigo, nombre in (
        ("SC01", "Casa Central"),
        ("SC02", "Formosa"),
        ("SC03", "Sáenz Peña"),
        ("SC04", "División Usados"),
    ):
        ses.add(Sucursal(codigo=codigo, nombre=nombre))
    # Sin relationship() el flush no ordena los inserts por FK: las sedes deben
    # existir antes del insert por lote de usuario.
    ses.flush()
    for clave, circuito, valor in (
        ("plazo_rotacion_meses", "COMERCIAL", "6"),
        ("plazo_rotacion_meses", "POSVENTA", "12"),
        ("service_intervalo_km", None, "10000"),
        ("aviso_service_km", None, "500"),
        ("umbral_ocr", None, "80"),
        ("aviso_multa_dias", None, "5"),
        ("duracion_token_horas", None, "8"),
        ("intentos_maximos", None, "5"),
    ):
        ses.add(Parametro(clave=clave, valor=valor, circuito=circuito))
    usuarios = {}
    for legajo, correo, rol, sucursal in (
        ("1001", "admin@pruebas.local", Rol.ADMIN, "SC01"),
        ("1002", "mkt@pruebas.local", Rol.RESP_MKT_VENTAS, "SC01"),
        ("1003", "asesor@pruebas.local", Rol.ASESOR, "SC01"),
        ("1004", "posventa@pruebas.local", Rol.RESP_POSVENTA, "SC01"),
        ("1005", "inactivo@pruebas.local", Rol.ASESOR, "SC01"),
        ("1006", "asesor2@pruebas.local", Rol.ASESOR, "SC02"),
    ):
        usuario = Usuario(
            legajo=legajo,
            correo=correo,
            nombre=f"Prueba {legajo}",
            rol=rol,
            id_sucursal=sucursal,
            hash_clave=hash_pruebas,
            activo=legajo != "1005",
        )
        ses.add(usuario)
        usuarios[correo.split("@")[0]] = usuario
    ses.commit()
    datos = SimpleNamespace(**usuarios)
    yield datos
    ses.close()
