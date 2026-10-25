"""Motor de base y sesiones por request (SQLAlchemy 2.0 estilo tipado)."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Base declarativa comun a todos los modelos."""


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_session() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: una sesion por request, siempre cerrada."""
    sesion = SessionLocal()
    try:
        yield sesion
    finally:
        sesion.close()
