"""Posicion de una unidad cerca de un instante (HU-10.2). La consulta real llega en la etapa 4."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SIN_POSICION = "sin posición"


def posicion_cercana(id_dispositivo: Optional[int], instante: datetime) -> Optional[dict[str, object]]:
    """Por ahora no hay posiciones: la sugerencia informa "sin posición"."""
    return None
