# Plataforma de Trazabilidad de Unidades Demo — Prototipo

TFG: *Plataforma Web para la Gestión y Trazabilidad de Unidades Demo en Concesionarias*
(Licenciatura en Informática, Universidad Siglo 21). Todos los datos son ficticios (Ley 25.326).

## Puesta en marcha en 3 pasos

Requisitos: **Docker Engine 24+ y Docker Compose v2**, `make` y `bash`. Nada más.

```bash
cp .env.example .env   # opcional: make demo lo crea si no existe; editá las contraseñas
make demo              # levanta todo, migra, siembra y genera actas de prueba
```

| URL | Qué es |
| --- | --- |
| `https://localhost` | Aplicación web (Streamlit detrás de Nginx, certificado autofirmado: aceptar la advertencia una vez) |
| `https://localhost/api/v1/docs` | Documentación interactiva de la API |
| `https://localhost/api/v1/salud` | Healthcheck público |
| `http://localhost:5678` | n8n (flujo de lectura de actas) |
| `http://localhost:8082` | Traccar (posiciones GPS simuladas) |

Otros objetivos del Makefile: `up`, `down`, `reset` (borra volúmenes), `seed`, `actas`, `gps`,
`correo`, `test`, `capturas`, `paquete`, `logs`.

## Usuarios de demo (solo con `ENTORNO=demo`; claves configurables con `DEMO_CLAVE_*`)

Ninguna de estas cuentas exige cambiar la contraseña al primer ingreso (ver `docs/decisiones.md`).

| Rol | Correo | Contraseña |
| --- | --- | --- |
| Administrador del sistema | admin@demo.local | `DemoAdmin2026!` |
| Responsable de Marketing y Ventas | mkt@demo.local | `DemoMkt2026!` |
| Asesor comercial (Formosa) | asesor@demo.local | `DemoAsesor2026!` |
| Asesor comercial (Casa Central) | asesor.central@demo.local | `DemoCentral2026!` |
| Asesor comercial (Sáenz Peña) | asesor.saenz@demo.local | `DemoSaenz2026!` |
| Responsable de Posventa | posventa@demo.local | `DemoPosventa2026!` |
| Administración | administracion.usuario@demo.local | `DemoAdministracion2026!` |
| Gerencia | gerencia@demo.local | `DemoGerencia2026!` |
| Usuario técnico n8n | tecnico-n8n@demo.local | (API key por cabecera, no ingresa por pantalla) |

El DMS simulado da de alta además un empleado dado de baja (`baja@demo.local`) para probar HU-15.2 y HU-01.4.

## Arquitectura

Monolito modular FastAPI + PostgreSQL 16 + Streamlit + Nginx HTTPS, con servicios de apoyo:
DMS simulado, n8n, GreenMail (correo de prueba) y Traccar (GPS). Ver `docs/especificacion.md`.

**Historial inmutable de doble capa:** un trigger `BEFORE UPDATE OR DELETE` rechaza toda modificación
de `evento_unidad`, y la API se conecta con un rol de base (`demo_app`) que solo tiene `SELECT, INSERT`
sobre esa tabla; el rol dueño (`demo_migraciones`) ejecuta las migraciones.

## Estado del proyecto (por etapas)

- **Etapa 0 — andamiaje y contenedores:** ✅ estructura, Compose con healthchecks, Nginx + certificado, Alembic inicial, esqueleto web.
- **Etapa 1 — núcleo de trazabilidad:** ✅ identidad, motor de estados, sincronización DMS, pantallas P1, P2, P3, P4 y P8.
- **Etapa 2 — operación diaria:** ✅ usos comerciales, préstamos por garantía, pantallas P5 y P7.
- **Etapa 3 — circuito de infracciones:** ✅ correo, n8n, lectura de actas, bandeja y pantalla P6.
- **Etapa 4 — ubicación, tablero y alertas:** ✅ Traccar con simulador, pantallas P2, P9 y P10, y mapa en P3.
- Etapa 5: empaquetado final.

## Desarrollo

Sin `make` (por ejemplo, en Windows), con recarga automática y sin certificado:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db api web dms
```

Web en `http://localhost:8501` y API en `http://localhost:8000/api/v1/docs`. La primera vez,
cargar los datos con `docker compose exec api python /srv/scripts/seed.py` (en Git Bash,
anteponer `MSYS_NO_PATHCONV=1`).

## Posiciones GPS de prueba

`make gps` da de alta los dispositivos en Traccar y envía los recorridos. Sin `make`:

```bash
docker compose exec -T api python /srv/scripts/simular_gps.py
```

## Actas de prueba

Con todos los servicios levantados (`make up` o `docker compose up -d`), `make actas` genera 8 PDF
y los envía por correo. Sin `make`:

```bash
docker compose exec -T api python /srv/scripts/generar_actas.py
docker compose exec -T api python /srv/scripts/enviar_actas.py
```

n8n las lee en menos de un minuto y quedan en **Infracciones** (usuario de Administración). Un acta
repite su número y no se duplica; otra es ilegible y queda para carga manual.

## Correo de la demo

Los enlaces de recuperación y las claves temporales llegan a GreenMail, nunca a una casilla real.
`make correo PARA=mkt@demo.local` los muestra. Sin `make`:

```bash
docker compose exec -T api python /srv/scripts/ver_correo.py mkt@demo.local
```

## Pruebas

`make test` (o `scripts/test.ps1` en Windows) corre la suite **dentro de Docker** (servicio `test`
del perfil `test`): unitarias, de integración y de aceptación por HU contra una base PostgreSQL
efímera (`demo_unidades_test`) creada y migrada en el servicio `db` al iniciar, y eliminada al
terminar. Requiere `.env` presente (nunca se modifica ni se versiona). Exigencia de cobertura
≥ 80 % en `core/` y servicios de dominio.

Fuera de alcance (ver `docs/decisiones.md`): conexión real con DMS/Strix/FordPass, llaveros BLE/ESP32,
app móvil, correo real a usuarios y publicación en internet.
