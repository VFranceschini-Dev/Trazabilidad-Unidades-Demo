#!/bin/bash
# Roles de base del prototipo (se ejecuta solo en el primer arranque del volumen db).
# demo_migraciones: dueno de las tablas (POSTGRES_USER).
# demo_app: rol de la API; sobre evento_unidad solo SELECT e INSERT (historial inmutable, capa 2).
# Las credenciales del rol de aplicacion salen de .env (DEMO_DB_APP_USER / DEMO_DB_APP_PASSWORD).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_user="${DEMO_DB_APP_USER:-demo_app}" \
  -v app_pw="${DEMO_DB_APP_PASSWORD}" \
  -v db="$POSTGRES_DB" <<'SQL'
DO $body$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_pw');
  END IF;
END
$body$;

GRANT CONNECT ON DATABASE :db TO :app_user;
GRANT USAGE ON SCHEMA public TO :app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :app_user;

-- El trigger de inmutabilidad y el REVOKE sobre evento_unidad los crean las migraciones Alembic
-- (dueno: demo_migraciones); ver migraciones/versions/0001_nucleo.py y 0002.
SQL
