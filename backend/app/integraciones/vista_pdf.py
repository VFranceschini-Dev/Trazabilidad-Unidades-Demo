"""Vista previa de un acta para mostrarla junto a sus datos (HU-09.1)."""

from __future__ import annotations

import io

from pdf2image import convert_from_bytes


def vista_previa(contenido: bytes) -> bytes:
    """Primera pagina del PDF en PNG."""
    salida = io.BytesIO()
    convert_from_bytes(contenido, dpi=110, first_page=1, last_page=1)[0].save(salida, format="PNG")
    return salida.getvalue()
