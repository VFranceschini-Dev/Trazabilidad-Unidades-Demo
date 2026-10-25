"""DMS simulado de la concesionaria (empleados y unidades).

Empleados con legajo, nombre, correo @demo.local, sucursal, rol y activo; se incluye uno
dado de baja para probar HU-15 criterio 2 y HU-01 criterio 4. `?fallar=1` devuelve 500 a
pedido para probar HU-15 criterio 3 (error de comunicacion y reintento en el siguiente ciclo).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="DMS simulado", version="1.0")

EMPLEADOS: list[dict[str, Any]] = [
    {"legajo": "1001", "nombre": "Ana Administradora", "correo": "admin@demo.local", "id_sucursal": "SC01", "rol": "ADMIN", "activo": True},
    {"legajo": "1002", "nombre": "Marta Marketing", "correo": "mkt@demo.local", "id_sucursal": "SC01", "rol": "RESP_MKT_VENTAS", "activo": True},
    {"legajo": "1003", "nombre": "Alberto Asesor", "correo": "asesor@demo.local", "id_sucursal": "SC02", "rol": "ASESOR", "activo": True},
    {"legajo": "1004", "nombre": "Paula Posventa", "correo": "posventa@demo.local", "id_sucursal": "SC01", "rol": "RESP_POSVENTA", "activo": True},
    {"legajo": "1005", "nombre": "Tomas Taller", "correo": "taller@demo.local", "id_sucursal": "SC03", "rol": "TECNICO_TALLER", "activo": True},
    {"legajo": "1006", "nombre": "Uriel Usados", "correo": "usados@demo.local", "id_sucursal": "SC04", "rol": "RESP_USADOS", "activo": True},
    # dado de baja en el DMS: al sincronizar debe quedar inactivo sin borrar su historial
    {"legajo": "1007", "nombre": "Bruno Baja", "correo": "baja@demo.local", "id_sucursal": "SC02", "rol": "ASESOR", "activo": False},
]

UNIDADES: list[dict[str, Any]] = []  # las unidades ya existen por semilla; el DMS las confirma


@app.get("/salud")
def salud() -> dict[str, str]:
    return {"estado": "ok"}


@app.get("/empleados")
def empleados(fallar: int = Query(default=0)) -> Any:
    if fallar:
        return JSONResponse(status_code=500, content={"error": "DMS indisponible (fallo a pedido)"})
    return EMPLEADOS


@app.get("/unidades")
def unidades(fallar: int = Query(default=0)) -> Any:
    if fallar:
        return JSONResponse(status_code=500, content={"error": "DMS indisponible (fallo a pedido)"})
    return UNIDADES
