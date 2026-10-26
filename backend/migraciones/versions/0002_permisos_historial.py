"""permisos_historial: demo_app sin UPDATE/DELETE sobre evento_unidad y con uso de secuencias

Capa 2 de la inmutabilidad (HU-07 criterio 3): los privilegios por defecto del rol de
aplicacion (init_db_roles.sh) incluyen UPDATE y DELETE sobre todas las tablas; se
revocan sobre evento_unidad, que queda solo con SELECT e INSERT. Ademas se otorga uso
de todas las secuencias del esquema: sin ello los inserts del rol de aplicacion sobre
tablas con columnas seriales fallarian por falta de USAGE en la secuencia.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $body$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'demo_app') THEN
                EXECUTE 'REVOKE UPDATE, DELETE ON evento_unidad FROM demo_app';
                EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO demo_app';
            END IF;
        END
        $body$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $body$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'demo_app') THEN
                EXECUTE 'GRANT UPDATE, DELETE ON evento_unidad TO demo_app';
            END IF;
        END
        $body$;
        """
    )
