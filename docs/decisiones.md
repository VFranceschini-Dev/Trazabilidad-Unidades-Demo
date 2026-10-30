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
usa la clave del README. No existe un perfil "Gerencia": los seis perfiles son los de la
Tabla 30 (`identidad.models.Rol`).

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
