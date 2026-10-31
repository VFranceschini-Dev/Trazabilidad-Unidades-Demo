"""token_recuperacion y version de sesion: enlace de un solo uso y cierre de sesiones

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuario", sa.Column("version_sesion", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("usuario", sa.Column("clave_cambiada_en", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "token_recuperacion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id_usuario", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("hash_token", sa.String(64), nullable=False, unique=True),
        sa.Column("vence_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_token_recuperacion_id_usuario", "token_recuperacion", ["id_usuario"])
    op.execute(
        """
        DO $body$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'demo_app') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE ON token_recuperacion TO demo_app';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE token_recuperacion_id_seq TO demo_app';
            END IF;
        END
        $body$;
        """
    )


def downgrade() -> None:
    op.drop_table("token_recuperacion")
    op.drop_column("usuario", "clave_cambiada_en")
    op.drop_column("usuario", "version_sesion")
