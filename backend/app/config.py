"""Typed application configuration loaded from environment variables and `.env`."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"

    # Comma-separated in the environment, e.g. "http://localhost:5173,https://app.example".
    # NoDecode stops pydantic-settings from expecting JSON so the validator can split it.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # Matches the local PostgreSQL service in docker-compose.yml (development credential only).
    database_url: str = "postgresql+psycopg://skyfleet:skyfleet@localhost:55432/skyfleet"

    # Seconds between Simulation Worker ticks.
    sim_tick_seconds: float = Field(default=1.0, gt=0)

    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
