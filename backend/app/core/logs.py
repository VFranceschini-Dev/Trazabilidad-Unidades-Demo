"""Logs estructurados (JSON) sin datos personales."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "nivel": record.levelname,
            "modulo": record.name,
            "mensaje": record.getMessage(),
        }
        extra = getattr(record, "datos", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configurar(nivel: int = logging.INFO) -> None:
    manejador = logging.StreamHandler(sys.stdout)
    manejador.setFormatter(JsonFormatter())
    raiz = logging.getLogger()
    raiz.handlers = [manejador]
    raiz.setLevel(nivel)


def log_evento(nombre: str, **datos: object) -> None:
    """Log estructurado; `datos` nunca debe contener datos personales."""
    logging.getLogger(nombre).info("", extra={"datos": datos})
