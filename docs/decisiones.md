# Decisiones de la demo

Registro de ambigüedades resueltas y desvíos respecto del TFG o del prompt. (Gana el TFG.)

## Etapa 0–1 (núcleo)
- Tipos de evento REASIGNACION, LIBERACION, INGRESO_SERVICE y FIN_SERVICE: no figuran en el diccionario de datos del TFG pero los requieren HU-03 y HU-07; se agregan al enumerado.
- Origen `API` reemplaza a `WEB` (los eventos provienen de la API REST consumida por Streamlit).
- Pruebas sobre SQLite en memoria con compatibilidad de tipos (JSONB→JSON, TIMESTAMP WITH TIME ZONE→DATETIME normalizado a UTC mediante TypeDecorator, BIGINT autoincremental→INTEGER). El trigger de inmutabilidad, los GRANTs y `SELECT … FOR UPDATE` reales solo existen en PostgreSQL: se verifican estáticamente sobre la migración 0001 y dinámicamente con `make demo`.
- Recuperación de contraseña: en la demo se registra la solicitud en auditoría y se devuelve la clave temporal por respuesta (no hay envío real de correo; fuera de alcance).

## Corrección del canal de pruebas (item 7 del instructivo)
- `docker compose run --rm api pytest` fallaba porque la imagen de producción no lleva dependencias de desarrollo ni `tests/`. Solución: `backend/requirements-dev.txt` (pytest, pytest-cov, httpx, ruff, mypy) + imagen exclusiva `backend/Dockerfile.dev` + servicio `test` con perfil `"test"` en `docker-compose.yml`, que monta `./tests:/srv/tests:ro`. La imagen de producción (`api`) queda intacta.
- `make test` ejecuta en primer lugar `docker compose build test && docker compose run --rm test`; si Docker no está disponible (como en este entorno de desarrollo), cae a `python -m pytest tests` local con las mismas dependencias. Verificado: 31 pruebas pasan por ambas vías (local y simulación exacta de rutas internas del contenedor `/srv/backend` + `/srv/tests`).
- El servicio `test` usa base SQLite en memoria y no depende de `db`: puede correrse sin levantar la pila completa.
