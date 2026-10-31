"""Simulador GPS: da de alta los dispositivos en Traccar y envia posiciones por OsmAnd.

Los recorridos siguen los usos y prestamos de la semilla, asi la posicion de un momento pasado
coincide con quien tenia la unidad. Datos ficticios. Se puede ejecutar mas de una vez.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta, timezone
from math import cos, pi, sin

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.comercial.models import UsoComercial  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.posventa.models import Prestamo  # noqa: E402
from app.unidades.models import UnidadDemo  # noqa: E402

OSMAND = os.environ.get("TRACCAR_OSMAND_URL", "http://traccar:5055")
BASE_POR_SUCURSAL = {
    "SC01": (-27.4512, -58.9866),  # Casa Central, Resistencia
    "SC02": (-26.1775, -58.1781),  # Formosa
    "SC03": (-26.7852, -60.4388),  # Saenz Pena
    "SC04": (-27.4300, -59.0200),  # Division Usados, Resistencia
}
PASO_USO = 10  # minutos: menos que el margen de +-15 de la sugerencia de imputacion
PASO_PRESTAMO = 180


def recorrido(
    base: tuple[float, float], desde: datetime, hasta: datetime, paso_minutos: int, radio: float, semilla: int
) -> list[tuple[datetime, float, float]]:
    """Sale de la base, se aleja hasta `radio` grados a mitad de camino y vuelve."""
    rng = random.Random(semilla)
    angulo = rng.uniform(0.0, 2.0 * pi)
    duracion = max((hasta - desde).total_seconds(), 1.0)
    tiempos = []
    t = desde
    while t < hasta:
        tiempos.append(t)
        t += timedelta(minutes=paso_minutos)
    tiempos.append(hasta)

    puntos = []
    for momento in tiempos:
        avance = (momento - desde).total_seconds() / duracion
        distancia = radio * sin(pi * avance) * (1.0 - rng.uniform(0.0, 0.1))
        direccion = angulo + rng.uniform(-0.2, 0.2)
        puntos.append((momento, base[0] + distancia * cos(direccion), base[1] + distancia * sin(direccion)))
    return puntos


def preparar_traccar(cliente: httpx.Client) -> None:
    """El primer usuario creado en Traccar queda como administrador."""
    respuesta = cliente.get("/api/devices")
    if respuesta.status_code == 200:
        return
    alta = cliente.post(
        "/api/users",
        json={"name": "Administrador demo", "email": settings.traccar_usuario, "password": settings.traccar_clave},
        auth=None,
    )
    alta.raise_for_status()


def enviar(unidad: UnidadDemo, sesion, ahora: datetime) -> int:
    base = BASE_POR_SUCURSAL.get(unidad.id_sucursal, BASE_POR_SUCURSAL["SC01"])
    puntos: list[tuple[datetime, float, float]] = []
    usos = sesion.scalars(select(UsoComercial).where(UsoComercial.id_unidad == unidad.id)).all()
    for uso in usos:
        puntos += recorrido(base, uso.fecha_hora_salida, uso.fecha_hora_regreso or ahora, PASO_USO, 0.02, uso.id_uso)
    prestamos = sesion.scalars(select(Prestamo).where(Prestamo.id_unidad == unidad.id)).all()
    for prestamo in prestamos:
        fin = prestamo.fecha_hora_devolucion or ahora
        puntos += recorrido(base, prestamo.fecha_hora_entrega, fin, PASO_PRESTAMO, 0.05, prestamo.id_prestamo)
    puntos.append((ahora, base[0], base[1]))

    for momento, latitud, longitud in sorted(puntos):
        httpx.post(
            OSMAND,
            params={"id": unidad.patente, "lat": latitud, "lon": longitud, "timestamp": int(momento.timestamp()), "speed": 0},
            timeout=10,
        ).raise_for_status()
    return len(puntos)


def simular() -> None:
    ahora = datetime.now(timezone.utc)
    cliente = httpx.Client(
        base_url=settings.traccar_api_url, auth=(settings.traccar_usuario, settings.traccar_clave), timeout=10
    )
    preparar_traccar(cliente)
    existentes = {d["uniqueId"]: d["id"] for d in cliente.get("/api/devices").raise_for_status().json()}
    with SessionLocal() as sesion:
        for unidad in sesion.scalars(select(UnidadDemo).order_by(UnidadDemo.patente)):
            id_dispositivo = existentes.get(unidad.patente)
            if id_dispositivo is None:
                alta = cliente.post("/api/devices", json={"name": unidad.patente, "uniqueId": unidad.patente})
                id_dispositivo = alta.raise_for_status().json()["id"]
            unidad.id_dispositivo_traccar = id_dispositivo
            print(f"== {unidad.patente}: {enviar(unidad, sesion, ahora)} posiciones")
        sesion.commit()


if __name__ == "__main__":
    simular()
