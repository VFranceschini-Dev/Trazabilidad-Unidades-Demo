"""Configuracion central leida desde variables de entorno (.env)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://demo_app:cambiar_app_api@localhost:5432/demo_unidades"
    database_url_migraciones: str = ""

    jwt_secret: str = "clave-demo-solo-desarrollo"
    jwt_algoritmo: str = "HS256"
    duracion_token_horas: int = 8
    sesion_inactiva_minutos: int = 30
    intentos_maximos: int = 5
    bloqueo_minutos: int = 15
    validez_clave_temporal_horas: int = 48

    dms_api_url: str = "http://dms:8100"
    traccar_api_url: str = "http://traccar:8082"
    n8n_api_key: str = "cambiar_api_key_n8n"

    timezone_display: str = "America/Argentina/Buenos_Aires"
    sync_dms_cada_minutos: int = 1

    cors_origenes: list[str] = ["https://localhost", "http://localhost:8501"]


settings = Settings()
