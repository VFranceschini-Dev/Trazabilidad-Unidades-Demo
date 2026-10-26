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
