"""operacion_diaria: uso_comercial, prestamo y alerta (Tablas 26, 27 y 29 del TFG)

Una sola salida y un solo prestamo abiertos por unidad (indices unicos parciales). El
documento de cliente pasa a ser opcional: el prospecto de un test drive solo deja nombre
y telefono (docs/decisiones.md).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("cliente", "documento", existing_type=sa.String(20), nullable=True)

    op.create_table(
        "uso_comercial",
        sa.Column("id_uso", sa.Integer(), primary_key=True),
        sa.Column("id_unidad", sa.Integer(), sa.ForeignKey("unidad_demo.id"), nullable=False),
        sa.Column("tipo_uso", sa.String(15), nullable=False),
        sa.Column("id_usuario", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("id_cliente", sa.Integer(), sa.ForeignKey("cliente.id")),
        sa.Column("fecha_hora_salida", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fecha_hora_regreso", sa.DateTime(timezone=True)),
        sa.Column("km_salida", sa.Integer(), nullable=False),
        sa.Column("km_regreso", sa.Integer()),
        sa.Column("observaciones", sa.Text()),
        sa.CheckConstraint("km_regreso >= km_salida", name="ck_uso_km_regreso"),
        sa.CheckConstraint("tipo_uso IN ('TEST_DRIVE', 'GIRA', 'GUARDIA', 'EVENTO')", name="ck_uso_tipo"),
    )
    op.create_index("ix_uso_unidad_salida", "uso_comercial", ["id_unidad", "fecha_hora_salida"])
    op.create_index(
        "ux_uso_abierto_por_unidad",
        "uso_comercial",
        ["id_unidad"],
        unique=True,
        postgresql_where=sa.text("fecha_hora_regreso IS NULL"),
    )

    op.create_table(
        "prestamo",
        sa.Column("id_prestamo", sa.Integer(), primary_key=True),
        sa.Column("id_unidad", sa.Integer(), sa.ForeignKey("unidad_demo.id"), nullable=False),
        sa.Column("id_cliente", sa.Integer(), sa.ForeignKey("cliente.id"), nullable=False),
        sa.Column("nro_orden_reparacion", sa.String(20), nullable=False),
        sa.Column("id_usuario_entrega", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("id_usuario_recepcion", sa.Integer(), sa.ForeignKey("usuario.id")),
        sa.Column("fecha_hora_entrega", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fecha_hora_devolucion", sa.DateTime(timezone=True)),
        sa.Column("km_entrega", sa.Integer(), nullable=False),
        sa.Column("km_devolucion", sa.Integer()),
        sa.Column("combustible_entrega", sa.SmallInteger(), nullable=False),
        sa.Column("combustible_devolucion", sa.SmallInteger()),
        sa.Column("control_previo", JSONB(), nullable=False),
        sa.Column("estado_entrega", sa.Text()),
        sa.Column("estado_devolucion", sa.Text()),
        sa.Column("fecha_devolucion_prevista", sa.Date(), nullable=False),
        sa.CheckConstraint("km_devolucion >= km_entrega", name="ck_prestamo_km_devolucion"),
        sa.CheckConstraint("combustible_entrega BETWEEN 0 AND 8", name="ck_prestamo_combustible_entrega"),
        sa.CheckConstraint("combustible_devolucion BETWEEN 0 AND 8", name="ck_prestamo_combustible_devolucion"),
    )
    op.create_index("ix_prestamo_unidad_entrega", "prestamo", ["id_unidad", "fecha_hora_entrega"])
    op.create_index(
        "ux_prestamo_abierto_por_unidad",
        "prestamo",
        ["id_unidad"],
        unique=True,
        postgresql_where=sa.text("fecha_hora_devolucion IS NULL"),
    )

    op.create_table(
        "alerta",
        sa.Column("id_alerta", sa.Integer(), primary_key=True),
        sa.Column("tipo_alerta", sa.String(30), nullable=False),
        sa.Column("id_unidad", sa.Integer(), sa.ForeignKey("unidad_demo.id")),
        sa.Column("mensaje", sa.String(200), nullable=False),
        sa.Column("estado", sa.String(10), nullable=False, server_default="ABIERTA"),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id_usuario_cierre", sa.Integer(), sa.ForeignKey("usuario.id")),
        sa.Column("fecha_cierre", sa.DateTime(timezone=True)),
        sa.Column("accion_realizada", sa.Text()),
    )
    op.create_index("ix_alerta_estado", "alerta", ["estado"])

    # Las bases creadas con el init anterior pueden no tener los privilegios por defecto
    op.execute(
        """
        DO $body$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'demo_app') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON uso_comercial, prestamo, alerta TO demo_app';
                EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO demo_app';
            END IF;
        END
        $body$;
        """
    )


def downgrade() -> None:
    op.drop_table("alerta")
    op.drop_table("prestamo")
    op.drop_table("uso_comercial")
    op.alter_column("cliente", "documento", existing_type=sa.String(20), nullable=False)
