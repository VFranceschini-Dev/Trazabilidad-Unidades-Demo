"""Adaptadores del DMS: HTTP al servicio simulado y lectura del respaldo CSV.

El contrato es el mismo (`DMSAdapter.traer_empleados` / `traer_unidades`), de modo que
la sincronizacion no cambia si manana el DMS real expone otra URL. HU-15.3: ante error
de comunicacion se lanza `ErrorDMS` y el reintento queda para el siguiente ciclo.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import settings


class ErrorDMS(Exception):
    """Fallo de comunicacion o de datos contra el DMS (HU-15.3)."""


@dataclass(frozen=True)
class EmpleadoDMS:
    legajo: str
    nombre: str
    correo: str
    id_sucursal: str
    rol: str        # ADMIN | RESP_MKT_VENTAS | ASESOR | RESP_POSVENTA | TECNICO_TALLER | RESP_USADOS
    activo: bool


@dataclass(frozen=True)
class UnidadDMS:
    vin: str
    patente: str
    modelo: str
    version: str
    circuito: str
    id_sucursal: str
    km_actual: int


class DMSAdapter(Protocol):
    def traer_empleados(self) -> list[EmpleadoDMS]: ...
    def traer_unidades(self) -> list[UnidadDMS]: ...


class DMSDesdeHTTP:
    """Cliente del DMS simulado; `?fallar=1` permite probar HU-15.3 a pedido."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.dms_api_url).rstrip("/")

    def _get(self, ruta: str, fallar: bool = False) -> list[dict[str, object]]:
        url = f"{self.base_url}{ruta}"
        if fallar:
            url += "?fallar=1"
        try:
            respuesta = httpx.get(url, timeout=10)
            respuesta.raise_for_status()
            return respuesta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ErrorDMS(f"No se pudo comunicar con el DMS: {exc}") from exc

    def traer_empleados(self, *, fallar: bool = False) -> list[EmpleadoDMS]:
        filas = self._get("/empleados", fallar)
        return [
            EmpleadoDMS(
                legajo=str(f["legajo"]),
                nombre=str(f["nombre"]),
                correo=str(f["correo"]).lower(),
                id_sucursal=str(f["id_sucursal"]),
                rol=str(f["rol"]),
                activo=bool(f["activo"]),
            )
            for f in filas
        ]

    def traer_unidades(self, *, fallar: bool = False) -> list[UnidadDMS]:
        filas = self._get("/unidades", fallar)
        return [
            UnidadDMS(
                vin=str(f["vin"]).upper(),
                patente=str(f["patente"]),
                modelo=str(f["modelo"]),
                version=str(f["version"]),
                circuito=str(f["circuito"]),
                id_sucursal=str(f["id_sucursal"]),
                km_actual=int(f["km_actual"]),
            )
            for f in filas
        ]


class DMSDesdeCSV:
    """Respaldo local `datos_demo/dms_respaldo.csv` (mismo contrato)."""

    def __init__(self, ruta: str | Path) -> None:
        self.ruta = Path(ruta)

    def _leer(self) -> list[dict[str, str]]:
        if not self.ruta.exists():
            raise ErrorDMS(f"No existe el respaldo {self.ruta}.")
        with self.ruta.open(encoding="utf-8-sig", newline="") as archivo:
            return list(csv.DictReader(archivo))

    def traer_empleados(self) -> list[EmpleadoDMS]:
        return [
            EmpleadoDMS(
                legajo=f["legajo"],
                nombre=f["nombre"],
                correo=f["correo"].lower(),
                id_sucursal=f["id_sucursal"],
                rol=f["rol"],
                activo=f["activo"] == "1",
            )
            for f in self._leer()
            if f.get("tipo", "EMPLEADO") == "EMPLEADO"
        ]

    def traer_unidades(self) -> list[UnidadDMS]:
        return [
            UnidadDMS(
                vin=f["vin"].upper(),
                patente=f["patente"],
                modelo=f["modelo"],
                version=f["version"],
                circuito=f["circuito"],
                id_sucursal=f["id_sucursal"],
                km_actual=int(f["km_actual"]),
            )
            for f in self._leer()
            if f.get("tipo") == "UNIDAD"
        ]
