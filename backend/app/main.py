"""Aplicación FastAPI del prototipo.

Prefijo /api/v1 para todas las rutas; documentacion en /api/v1/docs. Errores con el
formato comun {codigo, mensaje, detalle}. CORS cerrado a los origenes de la demo.
La sincronizacion DMS programada corre en un task interno (HU-15 criterio 1 y 3).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

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
from app.rutas_posventa import router as router_posventa
from app.rutas_sincronizacion import router as router_sync
from app.rutas_unidades import router as router_unidades
from app.sincronizacion.dms import DMSDesdeHTTP


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logs.configurar()
    tarea = asyncio.create_task(_planificador_dms()) if settings.sync_dms_cada_minutos > 0 else None
    yield
    if tarea is not None:
        tarea.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarea


async def _planificador_dms() -> None:
    """Sincronizacion programada: ante error se registra y se reintenta en el siguiente ciclo."""
    from app.sincronizacion.service import sincronizar

    while True:
        await asyncio.sleep(max(settings.sync_dms_cada_minutos, 1) * 60)
        sesion = SessionLocal()
        try:
            sincronizar(sesion, DMSDesdeHTTP(), usuario=None)
        except Exception as exc:  # nunca rompe la aplicacion
            logs.log_evento("sync.dms.planificador", estado="error", tipo=type(exc).__name__)
            sesion.rollback()
        finally:
            sesion.close()


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
        return {"estado": "ok" if estado_db == "ok" else "degradado", "base": estado_db, "etapa": 2}

    return r


v1 = APIRouter(prefix="/api/v1")
v1.include_router(_router_salud())
v1.include_router(router_auth)
v1.include_router(router_catalogos)
v1.include_router(router_comercial)
v1.include_router(router_posventa)
v1.include_router(router_unidades)
v1.include_router(router_sync)

app = FastAPI(
    title="Plataforma de Trazabilidad de Unidades Demo",
    description="Prototipo TFG — operación diaria (etapa 2). Datos ficticios (Ley 25.326).",
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
    allow_methods=["GET", "POST"],
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
