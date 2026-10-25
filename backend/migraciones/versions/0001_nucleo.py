"""nucleo: sucursal, usuario, cliente, unidad_demo, evento_unidad, asignacion, parametro, auditoria

Historial inmutable de doble capa: trigger BEFORE UPDATE OR DELETE sobre evento_unidad y
permisos SELECT,INSERT para el rol demo_app. Indices exigidos por la especificacion e
indice unico parcial de asignacion (una sola abierta por unidad).

Revision ID: 0001
Revises:
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sucursal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo", sa.String(10), nullable=False, unique=True),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("domicilio", sa.String(200)),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "cliente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("documento", sa.String(20), nullable=False, unique=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("contacto", sa.String(160)),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "usuario",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legajo", sa.String(20), nullable=False, unique=True),
        sa.Column("correo", sa.String(120), nullable=False, unique=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("rol", sa.String(30), nullable=False),
        sa.Column("id_sucursal", sa.String(10), sa.ForeignKey("sucursal.codigo")),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("hash_clave", sa.String(120), nullable=False),
        sa.Column("intentos_fallidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bloqueado_hasta", sa.DateTime(timezone=True)),
        sa.Column("debe_cambiar_clave", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("clave_temporal_hasta", sa.DateTime(timezone=True)),
        sa.Column("ultima_actividad", sa.DateTime(timezone=True)),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "unidad_demo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vin", sa.CHAR(17), nullable=False, unique=True),
        sa.Column("patente", sa.String(10), nullable=False, unique=True),
        sa.Column("modelo", sa.String(60), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("circuito", sa.String(20), nullable=False),
        sa.Column("estado_actual", sa.String(20), nullable=False),
        sa.Column("id_sucursal", sa.String(10), sa.ForeignKey("sucursal.codigo"), nullable=False),
        sa.Column("km_actual", sa.Integer(), nullable=False),
        sa.Column("km_proximo_service", sa.Integer()),
        sa.Column("fecha_alta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fecha_limite_rotacion", sa.DateTime(timezone=True)),
        sa.Column("id_dispositivo_traccar", sa.Integer()),
    )
    op.create_index("ix_unidad_estado", "unidad_demo", ["estado_actual"])
    op.create_index("ix_unidad_circuito", "unidad_demo", ["circuito"])
    op.create_table(
        "evento_unidad",
        sa.Column("id_evento", sa.BigInteger(), primary_key=True),
        sa.Column("id_unidad", sa.Integer(), sa.ForeignKey("unidad_demo.id"), nullable=False),
        sa.Column("tipo_evento", sa.String(30), nullable=False),
        sa.Column("estado_anterior", sa.String(20)),
        sa.Column("estado_nuevo", sa.String(20), nullable=False),
        sa.Column("fecha_hora", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("id_usuario", sa.Integer(), sa.ForeignKey("usuario.id")),
        sa.Column("origen", sa.String(10), nullable=False),
        sa.Column("carga_diferida", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("datos", sa.JSON(), nullable=False),
    )
    # Indice exigido: evento_unidad (id_unidad, fecha_hora DESC)
    op.create_index("ix_evento_unidad_unidad_fecha", "evento_unidad", ["id_unidad", sa.text("fecha_hora DESC")])
    op.create_table(
        "asignacion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("id_unidad", sa.Integer(), sa.ForeignKey("unidad_demo.id"), nullable=False),
        sa.Column("id_responsable", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("id_sucursal", sa.String(10), sa.ForeignKey("sucursal.codigo"), nullable=False),
        sa.Column("fecha_desde", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("fecha_hasta", sa.TIMESTAMP(timezone=True)),
        sa.Column("id_evento_apertura", sa.BigInteger()),
    )
    # Indice exigido: asignacion (id_unidad, fecha_desde)
    op.create_index("ix_asignacion_unidad_desde", "asignacion", ["id_unidad", "fecha_desde"])
    # Una sola asignacion abierta por unidad (indice unico parcial)
    op.execute("CREATE UNIQUE INDEX ux_asignacion_abierta ON asignacion (id_unidad) WHERE fecha_hasta IS NULL")
    op.create_table(
        "parametro",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clave", sa.String(60), nullable=False),
        sa.Column("valor", sa.String(200), nullable=False),
        sa.Column("circuito", sa.String(20)),
        sa.Column("id_sucursal", sa.Integer()),
        sa.Column("descripcion", sa.Text()),
    )
    op.create_table(
        "auditoria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("id_usuario", sa.Integer()),
        sa.Column("accion", sa.String(80), nullable=False),
        sa.Column("recurso", sa.String(160), nullable=False),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(45)),
        sa.Column("resultado", sa.String(20), nullable=False),
    )
    # Capa 1 de la inmutabilidad: trigger BEFORE UPDATE OR DELETE
    op.execute(
        """
        CREATE OR REPLACE FUNCTION evitar_modificacion_eventos() RETURNS trigger AS $body$
        BEGIN
            RAISE EXCEPTION 'El historial de eventos es inmutable (HU-07 criterio 3)';
        END;
        $body$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_evento_unidad_inmutable
        BEFORE UPDATE OR DELETE ON evento_unidad
        FOR EACH ROW EXECUTE FUNCTION evitar_modificacion_eventos();
        """
    )
    # Capa 2: permisos del rol de aplicacion (si existe; lo crea init_db_roles.sql)
    op.execute(
        """
        DO $body$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'demo_app') THEN
                GRANT SELECT, INSERT ON evento_unidad TO demo_app;
                GRANT USAGE, SELECT ON SEQUENCE evento_unidad_id_evento_seq TO demo_app;
            END IF;
        END
        $body$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_evento_unidad_inmutable ON evento_unidad")
    op.execute("DROP FUNCTION IF EXISTS evitar_modificacion_eventos()")
    for tabla in ("auditoria", "parametro", "asignacion", "evento_unidad", "unidad_demo", "usuario", "cliente", "sucursal"):
        op.drop_table(tabla)
