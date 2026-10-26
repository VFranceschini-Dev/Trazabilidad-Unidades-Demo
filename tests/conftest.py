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
    dueno = create_engine(URL_DUENO_TEST, isolation_level="AUTOCOMMIT")
    with dueno.connect() as conn:
        conn.execute(text(f"GRANT CONNECT ON DATABASE {BD_TEST} TO {APP_USUARIO}"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {APP_USUARIO}"))
        conn.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_USUARIO}")
        )
        conn.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_USUARIO}"))
    dueno.dispose()
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
def client(bd_test: dict[str, str]):
    """Cliente HTTP de la API real (FastAPI) contra la base de pruebas."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
