"""Pruebas de humo de la infraestructura: API viva, esquema del nucleo y trigger.

Validan que la base efimera del servicio `db` queda migrada y con las dos capas de
inmutabilidad operativas antes de correr el resto de la suite.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session


def test_salud_ok(client) -> None:
    respuesta = client.get("/api/v1/salud")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "ok"
    assert cuerpo["base"] == "ok"


def test_tablas_del_nucleo_presentes(sesion: Session) -> None:
    tablas = set(
        sesion.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalars().all()
    )
    esperadas = {
        "sucursal",
        "usuario",
        "cliente",
        "unidad_demo",
        "evento_unidad",
        "asignacion",
        "parametro",
        "auditoria",
    }
    assert esperadas <= tablas


def test_trigger_rechaza_update_y_delete(sesion: Session) -> None:
    sesion.execute(text("INSERT INTO sucursal (codigo, nombre, activa) VALUES ('TST', 'Sucursal Test', true)"))
    sesion.execute(
        text(
            "INSERT INTO unidad_demo (vin, patente, modelo, version, circuito, estado_actual,"
            " id_sucursal, km_actual, fecha_alta)"
            " VALUES ('1FTFW1E80PFA90001', 'TST001', 'Modelo', 'Version', 'COMERCIAL',"
            " 'DISPONIBLE', 'TST', 10, now())"
        )
    )
    sesion.execute(
        text(
            "INSERT INTO evento_unidad (id_unidad, tipo_evento, estado_nuevo, fecha_hora, origen, datos)"
            " VALUES ((SELECT id FROM unidad_demo WHERE patente = 'TST001'), 'ALTA', 'DISPONIBLE', now(), 'API', '{}')"
        )
    )
    sesion.commit()
    # El trigger lanza RAISE sin SQLSTATE (P0001): psycopg lo traduce a ProgrammingError.
    with pytest.raises(ProgrammingError):
        sesion.execute(text("UPDATE evento_unidad SET datos = '{}'"))
    sesion.rollback()
    with pytest.raises(ProgrammingError):
        sesion.execute(text("DELETE FROM evento_unidad"))
    sesion.rollback()


def test_rol_demo_app_con_select_e_insert(sesion: Session) -> None:
    privilegios = sesion.execute(
        text(
            "SELECT has_table_privilege('demo_app', 'evento_unidad', 'SELECT'),"
            " has_table_privilege('demo_app', 'evento_unidad', 'INSERT')"
        )
    ).one()
    assert privilegios[0] is True
    assert privilegios[1] is True
