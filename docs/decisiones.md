# Decisiones de diseño

Registro de diferencias entre el prompt de cada etapa, el TFG y lo implementado.
Cuando algo contradice al TFG, gana el TFG y la diferencia queda anotada acá.

## Etapa 1 — núcleo de trazabilidad

### Origen de los eventos: solo WEB, N8N, TRACCAR y DMS

El diccionario de datos del TFG (`evento_unidad.origen`) define exactamente esos cuatro
valores. El código de la etapa 0 usaba un valor propio `API` para las operaciones
registradas desde la interfaz/API; se eliminó del enum `Origen` y se reemplazó por `WEB`
en servicios, rutas, semilla y pruebas. Una prueba (`test_origen_solo_valores_del_tfg`)
fija el enum en esos cuatro valores.

### Plazos de rotación: 6 meses (COMERCIAL) y 12 meses (POSVENTA)

El TFG indica rotación de entre seis meses y un año según la política de la marca. La
semilla de la etapa 0 cargaba 24 y 18 meses, fuera de ese rango. Se fijó
`plazo_rotacion_meses` en 6 (COMERCIAL) y 12 (POSVENTA) en la semilla, en las pruebas y
en los valores por defecto de `unidades.service.fecha_limite_rotacion`.

### Tipos de evento agregados al diccionario de datos

`REASIGNACION`, `LIBERACION`, `INGRESO_SERVICE` y `FIN_SERVICE` no figuran en el
diccionario de datos del TFG pero los requieren HU-03 y HU-07; se agregan al enum
`TipoEvento` y a la tabla de transiciones del motor de estados.

### Permisos del rol de aplicación sobre el historial (capa 2 de inmutabilidad)

Los privilegios por defecto que `scripts/init_db_roles.sh` otorga a `demo_app` incluyen
`UPDATE` y `DELETE` sobre todas las tablas futuras. La migración `0002_permisos_historial`
los revoca sobre `evento_unidad` (queda solo `SELECT, INSERT`) y otorga `USAGE, SELECT`
sobre todas las secuencias del esquema, sin las cuales los inserts del rol de aplicación
en tablas con columnas seriales fallarían. El entorno de pruebas replica el mismo orden
que producción: privilegios por defecto antes de migrar, `REVOKE` en la migración.

### Credenciales del rol de aplicación desde `.env`

El init de roles de la etapa 0 dejaba la clave de `demo_app` hardcodeada en el SQL y no
coincidía con `DEMO_DB_APP_PASSWORD` de `.env` (la API no podía autenticar). Se reemplazó
`init_db_roles.sql` por `init_db_roles.sh`, que lee `DEMO_DB_APP_USER` y
`DEMO_DB_APP_PASSWORD` del entorno del servicio `db`. Los volúmenes ya inicializados se
alinean con `ALTER ROLE` desde el entorno de pruebas.

### ENTORNO con valor por defecto `produccion`

El prompt pide la variable `ENTORNO` (`demo` o `produccion`) para que la semilla y las
cuentas de demo solo funcionen en la demostracion. Si `.env` no la define, `core/config.py`
asume `produccion`: una instalacion sin configurar nunca expone las cuentas con
credenciales publicas. `.env.example` trae `ENTORNO=demo`, asi que `make demo` no cambia.
Con `produccion`, `scripts/seed.py` termina con un mensaje y sin tocar la base.

### Cuentas `es_demo`: excepcion al cambio de clave del primer ingreso

Columna `usuario.es_demo` (migracion `0003_usuario_es_demo`). Las cuentas de la semilla
quedan con `es_demo = true` y `debe_cambiar_clave = false` para que el guion de la demo no
se corte; las cuentas creadas antes de esta columna se marcan al volver a correr la semilla.
El resto de la politica (bloqueo por intentos, vencimiento del token, inactividad,
auditoria) se aplica igual. La excepcion vale solo con `ENTORNO=demo`: con `produccion`
una cuenta `es_demo` no puede ingresar y recibe el mismo mensaje generico que una cuenta
inactiva. Una clave temporal emitida por recuperacion sigue exigiendo el cambio.

### Claves de demo en `DEMO_CLAVE_*` con los valores del README

El prompt nombra las variables `DEMO_CLAVE_*` y da como ejemplo `Demo-Gerencia-2026`. Se
adopto el nombre de las variables pero se mantuvieron las claves ya documentadas en el
README (`DemoMkt2026!`, etc.), que cumplen la politica. Si una variable falta, la semilla
usa la clave del README.

### Lista de contraseñas comunes

`backend/datos/contrasenas_comunes.txt` contiene las primeras 1.000 lineas de
`Passwords/Common-Credentials/10k-most-common.txt` de SecLists (danielmiessler/SecLists).
Ninguna llega a 10 caracteres, por lo que la regla de longitud minima ya las rechaza; la
lista se mantiene porque la exige la politica y cubre cambios futuros del minimo.

### Logo de la concesionaria en lugar de "Parque Demo" sin marca

El prompt pide "sin logos ni colores de Ford". La demo muestra el logo de la concesionaria
Donnet (no el de Ford): el ultimo cuadro de `logo-donnet-animado.gif` de donnet.com.ar,
fijo y con fondo transparente, en P1/P2 sobre el titulo y en la barra lateral de las
pantallas internas; el favicon es la "D" del logo. Los colores siguen siendo los de las
referencias.

### Pantallas P3, P4 y P8: diferencias con las referencias

- **Menu lateral:** muestra solo las opciones construidas, habilitadas por `menu_permitido`
  de `/yo`. Tablero, Uso comercial, Prestamos, Infracciones, Alertas y Reportes se agregan
  en sus etapas. Se sumo "Altas" al menu de Resp. Posventa, que HU-02 habilita y faltaba.
- **Asesor:** el prompt lo envia a P7, que corresponde a la etapa 2; hasta entonces entra a P3.
- **P3:** sin mapa de Traccar (etapa 4).
- **P4:** sin la regla de infracciones pendientes (etapa 3). "Desde" es informativo: la
  asignacion se registra en el momento de confirmar. El motivo se guarda en
  `evento_unidad.datos`, sin columna nueva; la lista de motivos es propia, porque la
  referencia solo muestra un ejemplo.
- **P8:** sin dispositivo Traccar (etapa 4) ni busqueda en el DMS: el DMS simulado no publica
  unidades, y agregarlas haria que la sincronizacion les de el alta sola, sin pasar por esta
  pantalla. Modelo y version quedan en dos campos, como en `unidad_demo`. El circuito se
  deduce del rol, que solo puede dar de alta en el suyo.

Rutas de lectura agregadas para estas pantallas, no listadas en el prompt: `GET /unidades`,
`/unidades/recientes`, `/unidades/limite-rotacion`, `/unidades/{id}/asignaciones`,
`/sucursales` y `/responsables`.

### Stack y estructura: diferencias con el prompt de la etapa 0

- **JWT con PyJWT** en lugar de `python-jose`.
- **Sincronizacion programada con una tarea `asyncio`** en `main.py` en lugar de APScheduler,
  por ser la unica tarea programada de esta etapa.
- **Rutas en `app/rutas_*.py`** y esquemas en `esquemas.py`, en lugar de `router.py` y
  `schemas.py` por modulo. Los adaptadores del DMS estan en `sincronizacion/dms.py`, sin
  carpeta `integraciones/`.
- **Puerto 80 publicado en Nginx**, ademas del 443, para redirigir a HTTPS.
- **ruff y mypy** todavia no estan configurados, aunque el prompt los pide en la etapa 0.

### Objetivos del Makefile de etapas siguientes

`actas`, `gps`, `capturas` y `paquete` existen porque los pide el prompt, pero sus scripts
llegan en etapas posteriores: mientras tanto avisan y terminan sin error.

### Recarga en modo desarrollo

Streamlit solo invalida su cache de paginas y modulos si hay una sesion conectada al guardar.
Con `RECARGA_DESARROLLO` (solo en `docker-compose.dev.yml`) `frontend/app.py` la limpia en cada
ejecucion usando `Runtime.instance()._script_cache`, una API privada de Streamlit 1.38 que
hay que revisar si se actualiza la version.

### Imagen de n8n 1.53.2

La etiqueta `1.53.4` del prompt de versiones no existe en Docker Hub y hacia fallar la
instalacion limpia. Se usa `1.53.2`, la ultima publicada de esa version menor.

## Etapa 2 — operación diaria

### Alerta `DEVOLUCION_CON_DANOS`

HU-06 pide una alerta por devolucion con danos, pero la Tabla 29 del TFG no tiene ese tipo.
Se agrega al diccionario. La alerta se guarda en `alerta` con referencia a la unidad; su
pantalla (P9) llega en la etapa 4. Los danos no tienen columna propia en `prestamo`: quedan
en `estado_devolucion`, en la alerta y en los datos del evento.

### Prospecto del test drive: nombre y telefono

La Tabla 26 vincula el test drive a un cliente y P7 muestra un solo dato de contacto. La
migracion `0004` vuelve opcional `cliente.documento` y P7 pide nombre y telefono, en dos
campos para validar cada uno. Cada test drive crea un cliente: sin documento no hay con que
reconocer a un prospecto que vuelve. En el prestamo, en cambio, el cliente se identifica
por documento y se reutiliza.

### Control previo

Los cuatro items de P5 se guardan en `prestamo.control_previo` (JSONB, como pide el prompt) y
las observaciones en `estado_entrega`, el campo de la Tabla 27.

### Service vencido segun el km mayor

HU-05.2 bloquea por kilometraje. Se compara el proximo service con el mayor entre el km actual
y el declarado en la entrega. Una unidad sin proximo service cargado no se considera vencida.

### Bloqueo de la unidad antes de validar

`transicionar` usaba el estado leido antes de esperar el `FOR UPDATE`: con dos pedidos
simultaneos, el segundo podia aplicar una transicion invalida. Ahora refresca la fila, y las
operaciones toman el bloqueo con `obtener_unidad_bloqueada` antes de evaluar precondiciones.
Corrige tambien las operaciones de la etapa 1.

### Asesores por sucursal

Se suman dos asesores ficticios (Casa Central y Saenz Pena) al DMS simulado, la semilla y el
CSV, para que la historia de la semilla no quede toda en Formosa. La Division Usados sigue sin
asesor y su unidad comercial (AI009JK) queda DISPONIBLE.

### Semilla: historia solo en unidades sin movimientos

La historia de 30 dias usa fechas pasadas y el motor rechaza eventos anteriores al ultimo de
cada unidad, por lo que la semilla saltea las unidades con movimientos. Para verla completa
hay que partir de una base nueva. La fecha prevista del prestamo demorado queda 2 dias antes
de la ejecucion de la semilla.

### Asesor: entra a P7

El arreglo provisional de la etapa 1 (entrar a P3) se retira: P7 ya existe.

### Revision con Qwen

El codigo de esta etapa se reviso con `qwen3.8-flash`, enviando solo fragmentos de codigo y
reglas de negocio, sin credenciales ni datos del TFG. Se aplicaron la correccion del bloqueo
y la del service vencido. Se descartaron, entre otras, las validaciones de fecha diferida en
la pantalla: `st.time_input` no admite limites y la API ya rechaza esas fechas con un mensaje.

## Etapa 3 — circuito de infracciones

### Perfiles alineados con la Tabla 30 (correccion)

Hasta la etapa 2 el codigo tenia Tecnico de Taller y Resp. Division Usados, que el TFG no
define, y le faltaban Administracion y Gerencia. Esta decision corrige tambien una afirmacion
erronea de este documento ("no existe un perfil Gerencia"). La migracion `0005` deja inactivas
las cuentas con los perfiles quitados. Division Usados sigue existiendo como sucursal. Tambien
se aplica lo que la Tabla 30 dice sobre la consulta: el Asesor solo ve sus unidades y el
Resp. Posventa, las de su circuito.

### OCR y PDF en n8n, como dice el TFG

El prompt ubica el OCR en el backend y una ingesta multipart. El TFG dice que n8n guarda el PDF, lo
procesa con Tesseract y envia los datos a la API, y gana el TFG. El flujo guarda el adjunto en el
volumen `actas_pdf` (`/actas`), ejecuta `n8n/lector_actas.py` y envia a `POST /infracciones/ingesta`
los datos con el nombre del archivo. La API comparte el volumen solo para leer el PDF en P6 y borrar
el repetido. n8n usa una imagen propia (`n8n/Dockerfile`) con Tesseract, poppler y Python.

### Responsable del circuito cuando no hay responsable identificable

HU-10.4 habla del responsable de la sucursal, dato que el modelo no tiene. Se imputa al primer
usuario activo con el perfil del circuito: Resp. Marketing y Ventas (COMERCIAL) o Resp. Posventa
(POSVENTA), y se genera la alerta `SIN_RESPONSABLE`.

### Lectura del correo en n8n: se marca como leido al recibirlo

El prompt pide dejar el correo sin leer si la API falla despues de tres reintentos. El nodo IMAP
de n8n 1.53 marca el correo al leerlo y no hay un nodo para hacerlo despues, asi que ese caso no
se cumple: un acta que falle los tres intentos queda como ejecucion con error en n8n y hay que
reenviarla. Los reintentos si estan, y reenviar no duplica porque la ingesta es idempotente.

### Vista del acta como imagen

Streamlit 1.38 no trae visor de PDF. La API agrega `GET /infracciones/{id}/vista` con la primera
pagina en PNG, y P6 permite ademas descargar el PDF original.

### Corregir datos en la misma pantalla

La referencia tiene un boton "Corregir datos". Aca los campos ya se editan mientras el acta esta
pendiente, y al validarla quedan fijos. La validacion y la imputacion son dos pasos separados, como
en HU-09 y HU-10. El aviso de baja confianza marca el rotulo, sin el borde de color de la referencia.

### Posicion de Traccar

La sugerencia informa "sin posición" hasta la etapa 4 (`integraciones/traccar.py`), asi que
HU-10.2 todavia no esta cumplida.

### Revision con Qwen

Se reviso la imputacion y la ingesta con `qwen3.8-flash`. Se aplico el manejo de dos ingestas
simultaneas del mismo numero. La revision de las expresiones regulares fallo por error del servicio
y quedo sin hacer; esas expresiones se cubren con pruebas.
