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
`test`, `capturas`, `paquete`, `logs`.

## Usuarios de demo (cambiar contraseña al primer ingreso)

| Rol | Correo | Contraseña temporal |
| --- | --- | --- |
| Administrador del sistema | admin@demo.local | `DemoAdmin2026!` |
| Responsable de Marketing y Ventas | mkt@demo.local | `DemoMkt2026!` |
| Asesor comercial | asesor@demo.local | `DemoAsesor2026!` |
| Responsable de Posventa | posventa@demo.local | `DemoPosventa2026!` |
| Técnico de Taller | taller@demo.local | `DemoTaller2026!` |
| Responsable de División Usados | usados@demo.local | `DemoUsados2026!` |
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
- **Etapa 1 — núcleo de trazabilidad:** ⏳ en curso (identidad, motor de estados, sincronización DMS, pantallas P1/P3/P4/P8).
- Etapas 2 a 5: infracciones/OCR, ubicación/GPS, préstamos y tablero, empaquetado final.

## Pruebas

`make test` (o `scripts/test.ps1` en Windows) corre la suite **dentro de Docker** (servicio `test`
del perfil `test`): unitarias, de integración y de aceptación por HU contra una base PostgreSQL
efímera (`demo_unidades_test`) creada y migrada en el servicio `db` al iniciar, y eliminada al
terminar. Requiere `.env` presente (nunca se modifica ni se versiona). Exigencia de cobertura
≥ 80 % en `core/` y servicios de dominio.

Fuera de alcance (ver `docs/decisiones.md`): conexión real con DMS/Strix/FordPass, llaveros BLE/ESP32,
app móvil, correo real a usuarios y publicación en internet.
