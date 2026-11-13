"""Typed application configuration loaded from environment variables and `.env`."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
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

    # Flight simulation (Feature 010). Accelerated time: a complete mission takes between the
    # minimum and maximum, scaled by route length. This is simulation time only; the SF-1 speeds
    # in the drone model are not changed.
    sim_flight_min_seconds: float = Field(default=30.0, gt=0)
    sim_flight_max_seconds: float = Field(default=90.0, gt=0)
    sim_delivery_dwell_seconds: float = Field(default=3.0, ge=0)
    # The capacity recheck and landing happen this far (metres) before the Hub. It must exceed the
    # dock proximity so a normal emergency stops outside the target Hub's docking radius. That is a
    # convenience only: the occupancy predicate (MAINTENANCE is never docked) is the guarantee.
    sim_landing_approach_m: float = Field(default=60.0, gt=0)
    # A diversion may use the battery reserve but must arrive with at least this much battery.
    sim_critical_battery_pct: float = Field(default=5.0, ge=0, le=100)
    # A mission can only be started if the worker's last heartbeat is at most this old.
    sim_heartbeat_stale_seconds: float = Field(default=10.0, gt=0)

    # Seconds between automatic-dispatch passes in the worker (only used while the mode is ON).
    dispatch_auto_interval_seconds: float = Field(default=3.0, gt=0)

    # Mission planning (simulation assumptions, not certified performance). Extra energy per km
    # when carrying the full rated payload, as a fraction of the empty rate (0.5 = +50%).
    mission_payload_energy_factor: float = Field(default=0.5, ge=0)
    # A drone counts as docked at a Hub when its stored position is this close (metres). A
    # simulation approximation until docking hardware confirms presence.
    hub_dock_proximity_m: float = Field(default=50.0, gt=0)

    @model_validator(mode="after")
    def check_simulation_settings(self) -> "Settings":
        if self.sim_flight_max_seconds < self.sim_flight_min_seconds:
            raise ValueError("SIM_FLIGHT_MAX_SECONDS must not be below SIM_FLIGHT_MIN_SECONDS")
        if self.sim_delivery_dwell_seconds >= self.sim_flight_min_seconds:
            raise ValueError("SIM_DELIVERY_DWELL_SECONDS must be below SIM_FLIGHT_MIN_SECONDS")
        if self.sim_landing_approach_m <= self.hub_dock_proximity_m:
            raise ValueError("SIM_LANDING_APPROACH_M must exceed HUB_DOCK_PROXIMITY_M")
        return self

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
