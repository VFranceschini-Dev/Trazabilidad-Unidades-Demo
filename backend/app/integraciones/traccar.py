"""Adaptador de Traccar: ultima posicion, posicion cercana a un instante y localidad."""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.core.config import settings

SIN_POSICION = "sin posición"
MARGEN = timedelta(minutes=15)

# Localidades de la demo: (nombre, latitud, longitud)
LOCALIDADES = (
    ("Resistencia", -27.4512, -58.9866),
    ("Corrientes", -27.4692, -58.8306),
    ("Formosa", -26.1775, -58.1781),
    ("Sáenz Peña", -26.7852, -60.4388),
)


class ErrorTraccar(Exception):
    """Traccar no responde o devolvio algo inesperado."""


@dataclass(frozen=True)
class Posicion:
    latitud: float
    longitud: float
    fecha_hora: datetime


def _a_posicion(fila: dict[str, object]) -> Posicion:
    fecha = datetime.fromisoformat(str(fila["fixTime"]).replace("Z", "+00:00"))
    return Posicion(float(fila["latitude"]), float(fila["longitude"]), fecha)


class TraccarPosiciones:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.traccar_api_url).rstrip("/")

    def _posiciones(self, **params: object) -> list[Posicion]:
        try:
            respuesta = httpx.get(
                f"{self.base_url}/api/positions",
                params=params,
                auth=(settings.traccar_usuario, settings.traccar_clave),
                timeout=5,
            )
            respuesta.raise_for_status()
            return [_a_posicion(f) for f in respuesta.json()]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ErrorTraccar(str(exc)) from exc

    def ultima(self, id_dispositivo: int) -> Optional[Posicion]:
        posiciones = self._posiciones(deviceId=id_dispositivo)
        return max(posiciones, key=lambda p: p.fecha_hora) if posiciones else None

    def cercana(self, id_dispositivo: int, instante: datetime) -> Optional[Posicion]:
        """La posicion mas cercana al instante, dentro de +-15 minutos (HU-10.2)."""
        utc = instante.astimezone(timezone.utc)
        posiciones = self._posiciones(
            deviceId=id_dispositivo,
            **{"from": (utc - MARGEN).isoformat().replace("+00:00", "Z"), "to": (utc + MARGEN).isoformat().replace("+00:00", "Z")},
        )
        dentro = [p for p in posiciones if abs(p.fecha_hora - utc) <= MARGEN]
        return min(dentro, key=lambda p: abs(p.fecha_hora - utc)) if dentro else None


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFD", texto)
    return "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn").casefold()


def localidad_cercana(latitud: float, longitud: float) -> str:
    """Geocodificacion inversa simple: la localidad de la demo mas proxima."""
    return min(LOCALIDADES, key=lambda l: math.hypot(l[1] - latitud, l[2] - longitud))[0]


def describir_para_acta(posicion: Optional[Posicion], lugar_acta: Optional[str]) -> str:
    """HU-10.2: indica si la posicion coincide con el lugar del acta."""
    if posicion is None:
        return SIN_POSICION
    localidad = localidad_cercana(posicion.latitud, posicion.longitud)
    hora = posicion.fecha_hora.astimezone(_zona()).strftime("%d/%m %H:%M")
    lugar = _normalizar(lugar_acta or "")
    localidades_del_acta = [nombre for nombre, _, _ in LOCALIDADES if _normalizar(nombre) in lugar]
    if not localidades_del_acta:
        return f"{localidad} a las {hora} (el acta no indica una localidad para comparar)"
    resultado = "coincide" if localidad in localidades_del_acta else "no coincide"
    return f"{localidad} a las {hora} ({resultado})"


def _zona():
    from zoneinfo import ZoneInfo

    return ZoneInfo(settings.timezone_display)


def posicion_cercana(id_dispositivo: Optional[int], instante: datetime) -> Optional[Posicion]:
    """Para la sugerencia de imputacion: sin dispositivo o sin Traccar no hay posicion."""
    if id_dispositivo is None:
        return None
    try:
        return TraccarPosiciones().cercana(id_dispositivo, instante)
    except ErrorTraccar:
        return None
