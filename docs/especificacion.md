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

# Etapa 2 — operación diaria

## Modelo de datos de esta etapa

| Tabla | Puntos clave |
| --- | --- |
| `uso_comercial` | `tipo_uso` (TEST_DRIVE, GIRA, GUARDIA, EVENTO), salida/regreso con fecha y km, `CHECK km_regreso >= km_salida` |
| `prestamo` | orden de reparación, cliente, entrega/devolución con fecha, km, combustible (0 a 8), control previo en JSONB, `fecha_devolucion_prevista`; una sola abierta por unidad |

Índices: `uso_comercial (id_unidad, fecha_hora_salida)` y `prestamo (id_unidad, fecha_hora_entrega)`.

Las alertas de devolución con daños (HU-06) se guardan en la tabla `alerta`; si todavía no existe, creala ahora con
la estructura descrita en `docs/especificacion.md` o, si no está, con: tipo, referencia a unidad o acta, mensaje,
estado (ABIERTA, CERRADA), usuario y fecha de cierre y acción realizada.

## Transiciones de esta etapa

| Estado origen | Evento | Estado destino | HU | Precondiciones |
| --- | --- | --- | --- | --- |
| ASIGNADA | SALIDA | EN_USO | HU-04 | el usuario es el responsable asignado |
| EN_USO | REGRESO | ASIGNADA | HU-04 | km de regreso ≥ km de salida |
| DISPONIBLE | PRESTAMO | EN_PRESTAMO | HU-05 | circuito POSVENTA; service no vencido; control previo completo o justificado |
| EN_PRESTAMO | DEVOLUCION | DISPONIBLE | HU-06 | km de devolución ≥ km de entrega |

Todas pasan por el motor de estados de `core`. El responsable vigente (HU-07) ya debe tener en cuenta usos y préstamos.

## API de esta etapa

Prefijo `/api/v1`, documentación en `/api/v1/docs`. Toda ruta exige token y rol salvo `salud` y `auth/ingresar`. Errores con un formato común `{codigo, mensaje, detalle}`.

| Método | Ruta | HU | Roles |
| --- | --- | --- | --- |
| POST | `/usos/salida` · `/usos/{id}/regreso` | HU-04 | Asesor comercial |
| POST | `/prestamos` · `/prestamos/{id}/devolucion` · GET `/prestamos?activos=true` | HU-05, HU-06 | Resp. Posventa |
| GET | `/salud` | — | público |

Todas las operaciones que registran un movimiento aceptan `fecha_hora` opcional para la carga diferida: si se envía, el evento se guarda con ese instante y `carga_diferida = true`; nunca puede ser futura ni anterior al último evento de la unidad.

## Rutas agregadas en la etapa 2

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/usos/mis-unidades` | Unidades a cargo del asesor, con la salida abierta si la hay (P7) |

# Etapa 3 — circuito de infracciones

## Modelo de datos de esta etapa

| Tabla | Puntos clave |
| --- | --- |
| `infraccion` | `nro_acta` único, `patente_leida`, `fecha_hora_infraccion`, jurisdicción, monto NUMERIC(12,2), vencimiento, `archivo_pdf`, `confianza_ocr` y confianza por campo en JSONB, estado (PENDIENTE_VALIDACION, VALIDADA, IMPUTADA, PAGADA, RECHAZADA), `id_unidad` nulo, `id_resp_usuario` / `id_resp_cliente` con `CHECK` de que solo uno tenga valor, quién validó y cuándo |
| `alerta` | tipo (ROTACION_VENCIDA, PRESTAMO_DEMORADO, SERVICE_PROXIMO, MULTA_POR_VENCER, ACTA_A_VALIDAR, DEVOLUCION_CON_DANOS, SIN_RESPONSABLE), referencia a unidad o acta, mensaje, estado, cierre con usuario, fecha y acción realizada; sin duplicar una alerta abierta del mismo tipo y referencia |

Índices: `infraccion (estado)` e `infraccion (patente_leida)`.

## API de esta etapa

Prefijo `/api/v1`, documentación en `/api/v1/docs`. Toda ruta exige token y rol salvo `salud` y `auth/ingresar`. Errores con un formato común `{codigo, mensaje, detalle}`.

| Método | Ruta | HU | Roles |
| --- | --- | --- | --- |
| POST | `/infracciones/ingesta` (multipart PDF) | HU-08 | usuario técnico de n8n (API key) |
| GET | `/infracciones?estado=` · `/infracciones/{id}` · `/infracciones/{id}/pdf` | HU-09 | Administración |
| PUT | `/infracciones/{id}/validar` · `/rechazar` | HU-09 | Administración |
| GET | `/infracciones/{id}/sugerencia` | HU-10 | Administración |
| POST | `/infracciones/{id}/imputar` · `/pagar` | HU-10 | Administración |
| GET | `/salud` | — | público |

## Circuito de actas (HU-08 a HU-10)

**Flujo de n8n** (`n8n/flujo_actas.json`, importado al iniciar con la CLI de n8n):
`IMAP Email Trigger` (casilla `administracion@demo.local` de GreenMail, cada minuto) → filtrar adjuntos PDF → `HTTP Request` multipart a `POST /api/v1/infracciones/ingesta` con la API key del usuario técnico → marcar el correo como leído. Si la API responde con error, el flujo reintenta tres veces y deja el correo sin leer.

**Lectura del acta** (en el backend, `integraciones/ocr_tesseract.py`, detrás de la interfaz `LectorActas`):
1. Si el PDF tiene capa de texto, extraerla con `pdfplumber` y asignar confianza 99 a lo que coincida.
2. Si no, rasterizar con `pdf2image` a 300 ppp y pasar por Tesseract con `image_to_data`, idioma `spa`.
3. Extraer cada campo con expresiones regulares tolerantes: número de acta, patente (formatos `AA 999 AA` y `AAA 999`, normalizada), fecha y hora, lugar o jurisdicción, monto (formato argentino `$ 185.400,00`) y vencimiento.
4. La confianza de cada campo es el promedio de la confianza de las palabras que lo componen; la confianza general, el promedio de los campos encontrados.
5. Idempotencia por `nro_acta`: si ya existe, responder `200` con la existente y no duplicar. Si no se pudo leer ningún dato, guardar el PDF igual, con estado PENDIENTE_VALIDACION y sin datos, para carga manual.
6. Al registrar un acta se genera la alerta ACTA_A_VALIDAR.

**Sugerencia de imputación (HU-10):** buscar la unidad por patente, llamar a `responsable_vigente` con la fecha y hora del acta, y consultar a Traccar la posición más cercana a ese instante (±15 minutos). Indicar si coincide con el lugar del acta comparando la localidad por geocodificación inversa simple (tabla de localidades de la demo con coordenadas) o, si no hay dato, informar "sin posición". Si no hay responsable identificable, imputar al responsable de la sucursal y generar la alerta SIN_RESPONSABLE.

## Lectura de actas según el TFG

Esta etapa se apartó del prompt anterior: la lectura corre en n8n (`n8n/lector_actas.py`) y la
ingesta recibe en JSON los datos leídos y el nombre del PDF que n8n guardó en el volumen compartido.
Ver `decisiones.md`.

# Etapa 4 — ubicación, tablero y alertas

## Modelo de datos de esta etapa

| Tabla | Puntos clave |
| --- | --- |
| `alerta` | tipo (ROTACION_VENCIDA, PRESTAMO_DEMORADO, SERVICE_PROXIMO, MULTA_POR_VENCER, ACTA_A_VALIDAR, DEVOLUCION_CON_DANOS, SIN_RESPONSABLE), referencia a unidad o acta, mensaje, estado, cierre con usuario, fecha y acción realizada; sin duplicar una alerta abierta del mismo tipo y referencia |
| `parametro` | clave, valor, circuito y sucursal opcionales: plazo de rotación en meses por circuito, umbral OCR 80, aviso de service 500 km, aviso de multa 5 días, duración de token, intentos máximos |
| `posicion_cache` | última posición conocida por unidad, para responder cuando Traccar no está disponible (HU-11 criterio 3) |

## Transiciones de esta etapa

| Estado origen | Evento | Estado destino | HU | Precondiciones |
| --- | --- | --- | --- | --- |
| DISPONIBLE o ASIGNADA | PASE_VENTA | EN_VENTA | HU-14 | sin actas PENDIENTE_VALIDACION, VALIDADA sin imputar; sin préstamo ni service abiertos |
| EN_VENTA | BAJA | BAJA | HU-14 | motivo: venta como usado o devolución a la terminal |
| cualquiera | POSICION, INFRACCION | sin cambio | HU-10, HU-11 | eventos informativos |

## API de esta etapa

Prefijo `/api/v1`, documentación en `/api/v1/docs`. Toda ruta exige token y rol salvo `salud` y `auth/ingresar`. Errores con un formato común `{codigo, mensaje, detalle}`.

| Método | Ruta | HU | Roles |
| --- | --- | --- | --- |
| GET | `/unidades` (filtros: sucursal, circuito, estado) | HU-12 | según perfil; el asesor solo ve las suyas |
| POST | `/unidades/{id}/pase-venta` · `/baja` | HU-14 | Resp. Marketing y Ventas |
| GET | `/unidades/{id}/ubicacion` | HU-11 | lectura según perfil |
| GET | `/tablero/indicadores` | HU-12 | Gerencia y responsables |
| GET | `/alertas` · POST `/alertas/{id}/cerrar` | HU-13 | responsables de área |
| POST | `/alertas/ejecutar-control` | HU-13 | Administrador del sistema |
| GET | `/salud` | — | público |

## Ubicación

Servicio `traccar` (web 8082, OsmAnd 5055). El adaptador `TraccarPosiciones` consulta la última posición y la
posición más cercana a un instante (±15 minutos), y guarda la última en `posicion_cache` para responder cuando Traccar
no está disponible. Activá ahora la comparación de posición en la sugerencia de HU-10.
