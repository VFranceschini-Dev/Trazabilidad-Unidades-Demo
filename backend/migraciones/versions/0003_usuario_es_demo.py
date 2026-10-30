"""usuario_es_demo: marca de cuenta de demostracion

Las cuentas de demo (ENTORNO=demo) no exigen cambio de clave en el primer ingreso y no
pueden ingresar con ENTORNO=produccion. La columna nace en false para todas las cuentas;
la semilla marca las de demo (docs/decisiones.md).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usuario",
        sa.Column("es_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("usuario", "es_demo")
