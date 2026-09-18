"""
Application settings.

All configuration is read from environment variables (see `.env.example`
at the repository root). No secrets or environment-specific values are
hardcoded here.
"""

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

    # Database (not yet used by the application — provisioned here so the
    # connection string is available to later phases without requiring a
    # config change).
    database_url: str = (
        "postgresql://insightforge:insightforge@localhost:5432/insightforge"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
