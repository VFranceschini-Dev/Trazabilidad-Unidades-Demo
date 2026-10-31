"""infracciones: tabla infraccion, alerta sin duplicados y perfiles de la Tabla 30

Las cuentas con los perfiles quitados (Tecnico de Taller, Resp. Division Usados) quedan
inactivas con un perfil vigente: el enum Rol ya no puede leer los valores viejos.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE usuario SET rol = 'GERENCIA', activo = false WHERE rol IN ('TECNICO_TALLER', 'RESP_USADOS')")

    op.create_table(
        "infraccion",
        sa.Column("id_infraccion", sa.Integer(), primary_key=True),
        sa.Column("nro_acta", sa.String(30), unique=True),
        sa.Column("patente_leida", sa.String(9)),
        sa.Column("fecha_hora_infraccion", sa.DateTime(timezone=True)),
        sa.Column("jurisdiccion", sa.String(80)),
        sa.Column("monto", sa.Numeric(12, 2)),
        sa.Column("fecha_vencimiento", sa.Date()),
        sa.Column("archivo_pdf", sa.String(255), nullable=False),
        sa.Column("confianza_ocr", sa.Numeric(5, 2)),
        sa.Column("confianza_campos", JSONB(), nullable=False, server_default="{}"),
        sa.Column("estado", sa.String(20), nullable=False, server_default="PENDIENTE_VALIDACION"),
        sa.Column("fecha_recepcion", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id_unidad", sa.Integer(), sa.ForeignKey("unidad_demo.id")),
        sa.Column("id_resp_usuario", sa.Integer(), sa.ForeignKey("usuario.id")),
        sa.Column("id_resp_cliente", sa.Integer(), sa.ForeignKey("cliente.id")),
        sa.Column("id_usuario_validacion", sa.Integer(), sa.ForeignKey("usuario.id")),
        sa.Column("fecha_validacion", sa.DateTime(timezone=True)),
        sa.Column("motivo_rechazo", sa.Text()),
        sa.CheckConstraint("num_nonnulls(id_resp_usuario, id_resp_cliente) <= 1", name="ck_infraccion_un_responsable"),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE_VALIDACION', 'VALIDADA', 'IMPUTADA', 'PAGADA', 'RECHAZADA')",
            name="ck_infraccion_estado",
        ),
    )
    op.create_index("ix_infraccion_estado", "infraccion", ["estado"])
    op.create_index("ix_infraccion_patente", "infraccion", ["patente_leida"])

    op.add_column("alerta", sa.Column("id_infraccion", sa.Integer(), sa.ForeignKey("infraccion.id_infraccion")))
    # Sin duplicar una alerta abierta del mismo tipo y referencia
    op.execute(
        "UPDATE alerta a SET estado = 'CERRADA', accion_realizada = 'Duplicada al migrar' "
        "WHERE estado = 'ABIERTA' AND EXISTS (SELECT 1 FROM alerta b WHERE b.estado = 'ABIERTA' "
        "AND b.tipo_alerta = a.tipo_alerta AND b.id_unidad IS NOT DISTINCT FROM a.id_unidad "
        "AND b.id_alerta > a.id_alerta)"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_alerta_abierta ON alerta "
        "(tipo_alerta, COALESCE(id_unidad, 0), COALESCE(id_infraccion, 0)) WHERE estado = 'ABIERTA'"
    )

    op.execute(
        """
        DO $body$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'demo_app') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON infraccion TO demo_app';
                EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO demo_app';
            END IF;
        END
        $body$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ux_alerta_abierta")
    op.drop_column("alerta", "id_infraccion")
    op.drop_table("infraccion")
