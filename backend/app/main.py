"""Aplicación FastAPI del prototipo.

Prefijo /api/v1 para todas las rutas; documentacion en /api/v1/docs. Errores con el
formato comun {codigo, mensaje, detalle}. CORS cerrado a los origenes de la demo.
Las tareas programadas corren con APScheduler (HU-13 y HU-15).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core import logs
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.excepciones import ErrorDominio
from app.rutas_auth import router as router_auth
from app.rutas_catalogos import router as router_catalogos
from app.rutas_comercial import router as router_comercial
from app.rutas_gestion import router as router_gestion
from app.rutas_infracciones import router as router_infracciones
from app.rutas_posventa import router as router_posventa
from app.rutas_sincronizacion import router as router_sync
from app.rutas_unidades import router as router_unidades
from app.sincronizacion.dms import DMSDesdeHTTP


def _sincronizar_dms() -> None:
    """Sincronizacion programada: ante error se registra y se reintenta en el siguiente ciclo."""
    from app.sincronizacion.service import sincronizar

    sesion = SessionLocal()
    try:
        sincronizar(sesion, DMSDesdeHTTP(), usuario=None)
    except Exception as exc:  # nunca rompe la aplicacion
        logs.log_evento("sync.dms.planificador", estado="error", tipo=type(exc).__name__)
        sesion.rollback()
    finally:
        sesion.close()


def _control_diario() -> None:
    """HU-13: control diario de alertas."""
    from app.core.control_alertas import ejecutar_control

    sesion = SessionLocal()
    try:
        abiertas = ejecutar_control(sesion)
        sesion.commit()
        logs.log_evento("alertas.control", estado="exito", abiertas=abiertas)
    except Exception as exc:
        logs.log_evento("alertas.control", estado="error", tipo=type(exc).__name__)
        sesion.rollback()
    finally:
        sesion.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logs.configurar()
    planificador: BackgroundScheduler | None = None
    if settings.planificador_activo:
        planificador = BackgroundScheduler(timezone=settings.timezone_display)
        planificador.add_job(_control_diario, "cron", hour=settings.hora_control_alertas, minute=0)
        if settings.sync_dms_cada_minutos > 0:
            planificador.add_job(_sincronizar_dms, "interval", minutes=settings.sync_dms_cada_minutos)
        planificador.start()
    yield
    if planificador is not None:
        planificador.shutdown(wait=False)


def _router_salud() -> APIRouter:
    r = APIRouter(tags=["salud"])

    @r.get("/salud")
    def salud() -> dict[str, Any]:
        """Ruta publica de healthcheck (la unica junto a auth/ingresar sin token)."""
        estado_db = "ok"
        try:
            from sqlalchemy import text

            with SessionLocal() as sesion:
                sesion.execute(text("SELECT 1"))
        except Exception:
            estado_db = "caido"
        return {"estado": "ok" if estado_db == "ok" else "degradado", "base": estado_db, "etapa": 4}

    return r


v1 = APIRouter(prefix="/api/v1")
v1.include_router(_router_salud())
v1.include_router(router_auth)
v1.include_router(router_catalogos)
v1.include_router(router_comercial)
v1.include_router(router_posventa)
v1.include_router(router_infracciones)
v1.include_router(router_gestion)
v1.include_router(router_unidades)
v1.include_router(router_sync)

app = FastAPI(
    title="Plataforma de Trazabilidad de Unidades Demo",
    description="Prototipo TFG — ubicación, tablero y alertas (etapa 4). Datos ficticios (Ley 25.326).",
    version="1.0.0",
    docs_url="/api/v1/docs",
    redoc_url=None,
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origenes,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

app.include_router(v1)


@app.exception_handler(ErrorDominio)
async def manejar_error_dominio(request: Request, exc: ErrorDominio) -> JSONResponse:
    return JSONResponse(
        status_code=exc.estado_http,
        content={"codigo": exc.codigo, "mensaje": exc.mensaje, "detalle": exc.detalle},
    )


@app.exception_handler(RequestValidationError)
async def manejo_validacion(request: Request, exc: RequestValidationError) -> JSONResponse:
    campos = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
    faltantes = [str(e["loc"][-1]) for e in exc.errors() if e.get("type") == "missing"]
    mensaje = "Faltan campos obligatorios." if faltantes else "Datos de entrada inválidos."
    return JSONResponse(
        status_code=422,
        content={"codigo": "VALIDACION", "mensaje": mensaje, "detalle": {"campos": campos}},
    )
