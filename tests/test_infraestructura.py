"""Pruebas de humo de la infraestructura: API viva, esquema del nucleo y trigger.

Validan que la base efimera del servicio `db` queda migrada y con las dos capas de
inmutabilidad operativas antes de correr el resto de la suite.
"""

from __future__ import annotations

import pytest
from psycopg import errors as errores_psycopg
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


def test_capa1_trigger_inmutable_con_rol_dueno(sesion_dueno: Session) -> None:
    """Capa 1 de inmutabilidad: con todos los privilegios (rol dueno), el trigger igual rechaza."""
    sesion_dueno.execute(text("INSERT INTO sucursal (codigo, nombre, activa) VALUES ('TST', 'Sucursal Test', true)"))
    sesion_dueno.execute(
        text(
            "INSERT INTO unidad_demo (vin, patente, modelo, version, circuito, estado_actual,"
            " id_sucursal, km_actual, fecha_alta)"
            " VALUES ('1FTFW1E80PFA90001', 'TST001', 'Modelo', 'Version', 'COMERCIAL',"
            " 'DISPONIBLE', 'TST', 10, now())"
        )
    )
    sesion_dueno.execute(
        text(
            "INSERT INTO evento_unidad (id_unidad, tipo_evento, estado_nuevo, fecha_hora, origen, datos)"
            " VALUES ((SELECT id FROM unidad_demo WHERE patente = 'TST001'), 'ALTA', 'DISPONIBLE', now(), 'WEB', '{}')"
        )
    )
    sesion_dueno.commit()
    antes = sesion_dueno.execute(
        text("SELECT id_evento, tipo_evento, datos::text, fecha_hora FROM evento_unidad ORDER BY id_evento")
    ).all()
    # El trigger lanza RAISE sin SQLSTATE (P0001): psycopg lo traduce a ProgrammingError.
    with pytest.raises(ProgrammingError, match="inmutable"):
        sesion_dueno.execute(text("UPDATE evento_unidad SET datos = '{}'"))
    sesion_dueno.rollback()
    with pytest.raises(ProgrammingError, match="inmutable"):
        sesion_dueno.execute(text("DELETE FROM evento_unidad"))
    sesion_dueno.rollback()
    despues = sesion_dueno.execute(
        text("SELECT id_evento, tipo_evento, datos::text, fecha_hora FROM evento_unidad ORDER BY id_evento")
    ).all()
    assert despues == antes


def test_rol_demo_app_permisos_de_historial(sesion: Session) -> None:
    """Capa 2 de inmutabilidad: solo SELECT e INSERT; sin UPDATE ni DELETE (migracion 0002)."""
    privilegios = sesion.execute(
        text(
            "SELECT has_table_privilege('demo_app', 'evento_unidad', 'SELECT'),"
            " has_table_privilege('demo_app', 'evento_unidad', 'INSERT'),"
            " has_table_privilege('demo_app', 'evento_unidad', 'UPDATE'),"
            " has_table_privilege('demo_app', 'evento_unidad', 'DELETE')"
        )
    ).one()
    assert privilegios[0] is True
    assert privilegios[1] is True
    assert privilegios[2] is False
    assert privilegios[3] is False
    assert (
        sesion.execute(text("SELECT has_sequence_privilege('demo_app', 'usuario_id_seq', 'USAGE')")).scalar()
        is True
    )


def test_capa2_demo_app_permiso_denegado_al_modificar_historial(sesion: Session) -> None:
    """Capa 2 de inmutabilidad: el rol de aplicacion recibe permiso denegado al intentar
    UPDATE o DELETE sobre evento_unidad, aun antes de que intervenga el trigger."""
    with pytest.raises(ProgrammingError, match="permission denied for table evento_unidad") as exc_update:
        sesion.execute(text("UPDATE evento_unidad SET datos = '{}'"))
    assert isinstance(exc_update.value.orig, errores_psycopg.InsufficientPrivilege)
    sesion.rollback()
    with pytest.raises(ProgrammingError, match="permission denied for table evento_unidad") as exc_delete:
        sesion.execute(text("DELETE FROM evento_unidad"))
    assert isinstance(exc_delete.value.orig, errores_psycopg.InsufficientPrivilege)
    sesion.rollback()
