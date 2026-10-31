"""posicion_cache: ultima posicion conocida por unidad, para cuando Traccar no responde (HU-11.3)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "posicion_cache",
        sa.Column("id_unidad", sa.Integer(), sa.ForeignKey("unidad_demo.id"), primary_key=True),
        sa.Column("latitud", sa.Float(), nullable=False),
        sa.Column("longitud", sa.Float(), nullable=False),
        sa.Column("fecha_hora", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        """
        DO $body$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'demo_app') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON posicion_cache TO demo_app';
            END IF;
        END
        $body$;
        """
    )


def downgrade() -> None:
    op.drop_table("posicion_cache")
