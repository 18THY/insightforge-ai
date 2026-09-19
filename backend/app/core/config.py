"""
Application settings.

All configuration is read from environment variables (see `.env.example`
at the repository root). No secrets or environment-specific values are
hardcoded here.
"""

import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the backend service."""

    model_config = SettingsConfigDict(
        # Supports running `uvicorn` from either the repo root or the
        # `backend/` directory. Real environment variables (e.g. those set
        # by Docker Compose) always take precedence over these files.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    app_name: str = "InsightForge AI"
    environment: str = "development"

    # CORS: comma-separated list of allowed origins for the frontend.
    cors_allow_origins: str = "http://localhost:3000"

    # Database
    database_url: str = (
        "postgresql://insightforge:insightforge@localhost:5432/insightforge"
    )

    # JWT / Authentication
    # jwt_secret_key MUST be set via environment variable in any real
    # environment. The fallback here is only for local development
    # convenience; it is regenerated each process start and is NOT suitable
    # for production.
    jwt_secret_key: str = secrets.token_urlsafe(32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
