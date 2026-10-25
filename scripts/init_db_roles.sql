-- Roles de base del prototipo (se ejecuta solo en el primer arranque del volumen db).
-- demo_migraciones: dueño de las tablas (POSTGRES_USER ya existe con ese nombre si se usa .env por defecto).
-- demo_app: rol de la API; sobre evento_unidad solo SELECT e INSERT (historial inmutable, capa 2).
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'demo_app') THEN
    CREATE ROLE demo_app LOGIN PASSWORD 'cambiar_app_api';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE demo_unidades TO demo_app;
GRANT USAGE ON SCHEMA public TO demo_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO demo_app;

-- El trigger de inmutabilidad lo crea la migración Alembic (dueño: demo_migraciones).
