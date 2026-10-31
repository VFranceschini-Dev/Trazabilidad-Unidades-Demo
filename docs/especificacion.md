# Especificación compartida

Copia de las secciones de los prompts de cada etapa (`docs_referencia/`, sin versionar). Lo que el código hace distinto está en [decisiones.md](decisiones.md), que tiene prioridad sobre este texto. Si el prompt contradice al TFG, gana el TFG.

# Etapa 0 — andamiaje

## Stack y versiones

| Capa | Tecnología |
| --- | --- |
| Lenguaje | Python 3.12 |
| API | FastAPI, Pydantic v2, Uvicorn |
| Persistencia | PostgreSQL 16, SQLAlchemy 2 (estilo 2.0, tipado), Alembic |
| Interfaz | Streamlit (consume solo la API) |
| Automatización | n8n (imagen oficial, instalación propia) |
| OCR | Tesseract 5 con idioma `spa`, `pytesseract`, `pdf2image`, `pdfplumber` |
| Geolocalización | Traccar (imagen oficial) |
| Correo de prueba | GreenMail (SMTP + IMAP) |
| Proxy | Nginx con HTTPS y certificado autofirmado |
| Tareas programadas | APScheduler dentro del backend |
| Seguridad | `passlib[bcrypt]` costo 12, `python-jose` para JWT |
| Pruebas | pytest, pytest-cov, httpx, Playwright para capturas |
| Calidad | ruff (lint y formato), mypy en `core/` |
| Orquestación | Docker Compose v2, Makefile |

Fijá las versiones en `requirements.txt` y en las etiquetas de imagen. Nada de `latest`.

## Arquitectura y estructura del repositorio

Monolito modular: una sola API dividida en módulos por dominio. Un módulo usa los servicios de otro, nunca sus tablas. Todo cambio de estado pasa por el motor de estados de `core`. Todo lo externo entra por un adaptador.

```
.
├── backend/
│   ├── app/
│   │   ├── main.py                 # crea la app, registra routers, scheduler
│   │   ├── core/                   # config, db, seguridad, auditoría, motor de estados, historial
│   │   ├── identidad/              # HU-01 login, roles, bloqueo, sesiones
│   │   ├── unidades/               # HU-02, HU-03, HU-07, HU-14
│   │   ├── comercial/              # HU-04
│   │   ├── posventa/               # HU-05, HU-06
│   │   ├── infracciones/           # HU-08, HU-09, HU-10
│   │   ├── ubicacion/              # HU-11
│   │   ├── tablero/                # HU-12, HU-13
│   │   ├── sincronizacion/         # HU-15
│   │   └── integraciones/          # base.py + dms_simulado, dms_csv, traccar, ocr_tesseract
│   ├── migraciones/                # Alembic
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── .streamlit/config.toml      # ya existe: respetarlo
│   ├── app.py
│   ├── paginas/                    # una página por pantalla P1 a P10
│   ├── componentes/                # tarjeta, chip de estado, alerta, tabla, menú
│   ├── estilos.css
│   ├── cliente_api.py              # único punto de acceso a la API
│   └── Dockerfile
├── dms_simulado/                   # FastAPI aparte con datos ficticios
├── n8n/flujo_actas.json            # exportado, se importa al iniciar
├── nginx/                          # conf + script de certificado autofirmado
├── scripts/                        # seed, generar_actas, enviar_actas, simular_gps, capturas, empaquetar
├── datos_demo/                     # actas PDF generadas, CSV de respaldo del DMS
├── tests/                          # unitarias, integración, aceptación por HU
├── docs/                           # decisiones, guion, navegación, diseño, texto para el TFG
├── docker-compose.yml
├── .env.example
├── Makefile
└── README.md
```

Cada módulo de dominio tiene `router.py`, `service.py`, `models.py` y `schemas.py`. Las rutas no contienen lógica: validan, llaman al servicio y devuelven el esquema.

## Servicios de Docker Compose

| Servicio | Puerto interno | Expuesto | Depende de | Healthcheck |
| --- | --- | --- | --- | --- |
| `db` (PostgreSQL 16) | 5432 | no | — | `pg_isready` |
| `api` (FastAPI) | 8000 | vía Nginx `/api` | db | `GET /api/v1/salud` |
| `web` (Streamlit) | 8501 | vía Nginx `/` | api | `/_stcore/health` |
| `dms` (DMS simulado) | 8100 | no | — | `GET /salud` |
| `traccar` | 8082 web, 5055 OsmAnd | 8082 y 5055 en localhost | — | `GET /api/server` |
| `n8n` | 5678 | 5678 en localhost | api, mail | `/healthz` |
| `mail` (GreenMail) | 3025 SMTP, 3143 IMAP | 3025 en localhost | — | puerto abierto |
| `nginx` | 443 | 443 | web, api | — |

Volúmenes con nombre para la base, los PDF de actas, n8n y Traccar. Red interna única. Variables en `.env` (copiado de `.env.example` por `make demo` si no existe).

`Makefile` con: `demo` (todo desde cero), `up`, `down`, `reset` (borra volúmenes, pide confirmación), `seed`, `actas` (genera y envía actas de prueba), `gps` (simulador), `test`, `capturas`, `paquete`, `logs`.

## Fuera de alcance

Conexión real con el DMS, Strix Flotas y FordPass Pro; custodia de llaves con llaveros BLE y receptores ESP32; aplicación móvil nativa o PWA; envío real de correos a usuarios; publicación en internet. Mencionalos solo en `docs/decisiones.md`.

# Etapa 1 — núcleo de trazabilidad

## Modelo de datos de esta etapa

Respetá los nombres y tipos del diccionario de datos del TFG (Tablas 23 a 29).

| Tabla | Puntos clave |
| --- | --- |
| `sucursal` | 4 sedes: Casa Central, Formosa, Sáenz Peña, División Usados |
| `usuario` | legajo, correo único, nombre, rol, `id_sucursal`, activo, hash, intentos fallidos, bloqueado hasta, debe cambiar contraseña, `es_demo` |
| `cliente` | documento, nombre, contacto (datos ficticios) |
| `unidad_demo` | `vin` CHAR(17) único, `patente` única, modelo/versión, `circuito` (COMERCIAL, POSVENTA), `estado_actual`, `id_sucursal`, `km_actual`, `km_proximo_service`, `fecha_alta`, `fecha_limite_rotacion`, `id_dispositivo_traccar` nulo |
| `evento_unidad` | `id_evento` BIGINT, `id_unidad`, `tipo_evento`, `estado_anterior`, `estado_nuevo`, `fecha_hora` TIMESTAMPTZ, `id_usuario` nulo, `origen` (WEB, N8N, TRACCAR, DMS), `carga_diferida` BOOL, `datos` JSONB |
| `asignacion` | `fecha_desde`, `fecha_hasta` nula mientras está vigente; índice único parcial: una sola asignación abierta por unidad |
| `parametro` | clave, valor, circuito y sucursal opcionales: plazo de rotación en meses por circuito, umbral OCR 80, aviso de service 500 km, aviso de multa 5 días, duración de token, intentos máximos |
| `auditoria` | usuario, acción, recurso, fecha, IP, resultado (ingresos, intentos fallidos y operaciones) |

**Historial inmutable, implementado de dos formas a la vez:**
1. Un trigger `BEFORE UPDATE OR DELETE` sobre `evento_unidad` que lance una excepción.
2. Dos roles de base: uno de migraciones (dueño de las tablas) y otro de aplicación con `SELECT, INSERT` sobre `evento_unidad`. La API se conecta con el de aplicación.

Índices: `evento_unidad (id_unidad, fecha_hora DESC)` y `asignacion (id_unidad, fecha_desde)`.

## Motor de estados

Una sola función en `core/estados.py`, por ejemplo `transicionar(sesion, unidad, evento, usuario, origen, datos, fecha_hora=None)`, que en una misma transacción: bloquea la fila de la unidad (`SELECT … FOR UPDATE`), valida la transición contra la tabla, verifica las precondiciones, actualiza `estado_actual` e inserta el evento. Una transición no prevista devuelve `409` con el estado actual y las acciones permitidas.

| Estado origen | Evento | Estado destino | HU | Precondiciones |
| --- | --- | --- | --- | --- |
| — | ALTA | DISPONIBLE | HU-02 | VIN de 17 caracteres y patente sin registrar |
| DISPONIBLE | ASIGNACION | ASIGNADA | HU-03 | circuito COMERCIAL; responsable activo y de la sucursal destino |
| ASIGNADA | REASIGNACION | ASIGNADA | HU-03 | cierra la asignación vigente y abre otra |
| ASIGNADA | LIBERACION | DISPONIBLE | HU-03 | cierra la asignación vigente |
| ASIGNADA | SALIDA | EN_USO | HU-04 | el usuario es el responsable asignado |
| EN_USO | REGRESO | ASIGNADA | HU-04 | km de regreso ≥ km de salida |
| DISPONIBLE | PRESTAMO | EN_PRESTAMO | HU-05 | circuito POSVENTA; service no vencido; control previo completo o justificado |
| EN_PRESTAMO | DEVOLUCION | DISPONIBLE | HU-06 | km de devolución ≥ km de entrega |
| DISPONIBLE | INGRESO_SERVICE | EN_SERVICE | HU-07 | — |
| EN_SERVICE | FIN_SERVICE | DISPONIBLE | HU-07 | actualiza km y próximo service |
| DISPONIBLE o ASIGNADA | PASE_VENTA | EN_VENTA | HU-14 | sin actas PENDIENTE_VALIDACION, VALIDADA sin imputar; sin préstamo ni service abiertos |
| EN_VENTA | BAJA | BAJA | HU-14 | motivo: venta como usado o devolución a la terminal |
| cualquiera | POSICION, INFRACCION | sin cambio | HU-10, HU-11 | eventos informativos |

Los tipos REASIGNACION, LIBERACION, INGRESO_SERVICE y FIN_SERVICE no figuran en el diccionario de datos del TFG pero los requieren HU-03 y HU-07: agregalos y registralo en `docs/decisiones.md`.

## Responsable vigente en una fecha y hora

`core/historial.py` expone `responsable_vigente(id_unidad, instante) -> Responsable | None`, que devuelve el tipo (usuario o cliente), su identificador, el evento que lo justifica y el período. Orden de búsqueda: préstamo cuyo intervalo de entrega a devolución contenga el instante; si no, uso comercial cuyo intervalo de salida a regreso lo contenga; si no, asignación vigente en ese instante; si no, `None`. Los intervalos abiertos se toman hasta el momento actual. Esta función la usan HU-07 (criterio 4) y HU-10, y tiene pruebas con bordes exactos (instante igual a la salida, igual al regreso, sin datos).

## API de esta etapa

Prefijo `/api/v1`, documentación en `/api/v1/docs`. Toda ruta exige token y rol salvo `salud` y `auth/ingresar`. Errores con un formato común `{codigo, mensaje, detalle}`.

| Método | Ruta | HU | Roles |
| --- | --- | --- | --- |
| POST | `/auth/ingresar` · `/auth/salir` · `/auth/cambiar-clave` · `/auth/recuperar` | HU-01 | público / autenticado |
| GET | `/yo` (usuario, rol, menú permitido) | HU-01 | autenticado |
| POST | `/unidades` | HU-02 | Resp. Marketing y Ventas (COMERCIAL), Resp. Posventa (POSVENTA) |
| GET | `/unidades/{id}` · `/unidades/{id}/historial` · `/unidades/{id}/responsable?en=` | HU-07 | lectura según perfil |
| POST | `/unidades/{id}/asignaciones` · `/reasignar` · `/liberar` | HU-03 | Resp. Marketing y Ventas |
| POST | `/unidades/{id}/service/ingreso` · `/service/fin` | HU-07 | Resp. Posventa, Resp. Marketing y Ventas |
| POST | `/sincronizacion/dms` | HU-15 | Administrador del sistema |
| GET | `/salud` | — | público |

Todas las operaciones que registran un movimiento aceptan `fecha_hora` opcional para la carga diferida: si se envía, el evento se guarda con ese instante y `carga_diferida = true`; nunca puede ser futura ni anterior al último evento de la unidad.

## Seguridad

- Contraseñas con bcrypt costo 12; política: mínimo 10 caracteres, mayúscula, minúscula y número, sin nombre ni correo, rechazo de las 1.000 contraseñas más comunes (lista incluida en el repo).
- Contraseña temporal de un uso válida 48 h y cambio obligatorio en el primer ingreso.
- JWT firmado (HS256, clave en `.env`) con vencimiento de 8 h; cierre por 30 minutos de inactividad controlado en el servidor con la marca de última actividad.
- Bloqueo de 15 minutos tras 5 intentos fallidos; mensaje único "Usuario o contraseña incorrectos" con el número de intento.
- Control de rol en cada endpoint con una dependencia de FastAPI; la interfaz oculta opciones, pero el control real está en el backend.
- Auditoría de ingresos, intentos fallidos y operaciones con usuario, fecha, hora e IP.
- Usuario técnico para n8n con API key por cabecera, limitado a la ruta de ingesta.
- CORS cerrado, cabeceras de seguridad en Nginx, sin datos personales en URLs ni en logs.

## Rutas de lectura agregadas para las pantallas

No figuran en el prompt; las necesitan P3, P4 y P8. Todas exigen token.

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/unidades?estado=&circuito=&q=` | Listado con filtros y búsqueda por patente o VIN |
| GET | `/unidades/recientes?limite=` | Últimas altas con fecha y origen |
| GET | `/unidades/limite-rotacion?circuito=` | Plazo en meses y fecha límite para un alta ahora |
| GET | `/unidades/{id}/asignaciones` | Asignaciones de la unidad, la más reciente primero |
| GET | `/sucursales` | Sucursales activas |
| GET | `/responsables` | Asesores, incluidos los inactivos (HU-03.3) |
