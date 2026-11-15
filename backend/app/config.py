"""Typed application configuration loaded from environment variables and `.env`."""

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
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
    # Feature 018C: a failed drone flies this far (metres) along its current heading to a simulated
    # emergency landing point. A deterministic MVP rule, not a terrain or safety assessment.
    sim_emergency_landing_distance_m: float = Field(default=250.0, gt=0)
    # Feature 018E: the LPR helicopter scenario. Fictional simulation parameters, not aviation
    # values; each scenario stores the values it started with. A drone is held when it comes within
    # radius + margin of the helicopter and released once the helicopter is radius + margin +
    # clear-extra away (a hysteresis so it does not stop and go).
    sim_lpr_speed_ms: float = Field(default=80.0, gt=0)
    sim_lpr_zone_radius_m: float = Field(default=500.0, gt=0)
    sim_lpr_hold_margin_m: float = Field(default=250.0, ge=0)
    sim_lpr_clear_extra_m: float = Field(default=100.0, ge=0)
    # A mission can only be started if the worker's last heartbeat is at most this old.
    sim_heartbeat_stale_seconds: float = Field(default=10.0, gt=0)

    # Charging speed of a docked drone, in battery percent per minute. A demo-friendly value: the
    # SF-1 model's real figure (80% in 45 minutes, about 1.8 per minute) would be far too slow to
    # watch. One number for every drone; there are no charger slots.
    sim_charge_rate_pct_per_minute: float = Field(default=20.0, gt=0)

    # Seconds between automatic-dispatch passes in the worker (only used while the mode is ON).
    dispatch_auto_interval_seconds: float = Field(default=3.0, gt=0)

    # Feature 019B: while Auto Dispatch is ON the same pass also rebalances the fleet. After a
    # relocation between two Hubs, the pair is left alone (either direction) for this long, in real
    # seconds, so drones are not shuttled back and forth. Manual relocation is never blocked.
    rebalance_pair_cooldown_seconds: float = Field(default=300.0, ge=0)

    # Automatic order generation (Feature 015B), used only while Order Simulation is ON: a random
    # pause between the min and max seconds before each new order, and a cap on outstanding
    # (READY_FOR_PICKUP) orders above which generation pauses.
    order_sim_min_interval_seconds: float = Field(default=15.0, gt=0)
    order_sim_max_interval_seconds: float = Field(default=30.0, gt=0)
    order_sim_max_outstanding_orders: int = Field(default=20, ge=1)

    # Automatic random incidents (Feature 021D-2), used only while Random Incidents is ON: one
    # attempt after a random pause between the min and max seconds (real time), at most one
    # incident per attempt, and a random cooldown per incident type after a SUCCESSFUL trigger.
    # The weights bias which type is tried first (a drone failure grounds a drone, so it is rarer).
    incident_sim_min_interval_seconds: float = Field(default=180.0, gt=0)
    incident_sim_max_interval_seconds: float = Field(default=300.0, gt=0)
    incident_sim_cooldown_min_seconds: float = Field(default=120.0, ge=0)
    incident_sim_cooldown_max_seconds: float = Field(default=180.0, ge=0)
    incident_sim_weight_lpr: float = Field(default=0.4, ge=0)
    incident_sim_weight_recipient: float = Field(default=0.4, ge=0)
    incident_sim_weight_failure: float = Field(default=0.2, ge=0)

    # Automatic recovery of drones grounded by a drone failure (Feature 022): a simulated
    # ground crew moves the drone to a Hub this many real seconds after its emergency landing
    # (`mission_flights.emergency_at`). The worker looks every `check` seconds and recovers at most
    # `batch` drones per look, so a backlog is processed in small steps.
    drone_recovery_delay_seconds: float = Field(default=120.0, ge=0)
    drone_recovery_check_seconds: float = Field(default=5.0, gt=0)
    drone_recovery_batch_size: int = Field(default=3, ge=1)

    # --- AI assistant foundation (Feature 024) ---------------------------------------------------
    # Disabled by default. Nothing here is validated while AI is off, so a missing key never stops
    # the API or the worker; `app.ai.readiness.config_problems` checks everything when AI is on and
    # the gateway then refuses to run (fail closed) with a message that never contains a secret.
    # The limits can only be tightened from here: values beyond the MVP maxima are reported as
    # configuration problems, they are not accepted.
    ai_enabled: bool = Field(
        default=False, validation_alias=AliasChoices("SKYFLEET_AI_ENABLED", "ai_enabled")
    )
    # `repr=False` and `SecretStr`: the key is never printed, logged or dumped. It is read here
    # (from the environment or `.env`) and handed to the client explicitly; the SDK's own
    # environment lookup is never relied on.
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "anthropic_api_key"),
    )
    ai_model: str = Field(
        default="claude-haiku-5-5", validation_alias=AliasChoices("SKYFLEET_AI_MODEL", "ai_model")
    )
    ai_max_input_bytes: int = Field(
        default=16 * 1024,
        validation_alias=AliasChoices("SKYFLEET_AI_MAX_INPUT_BYTES", "ai_max_input_bytes"),
    )
    ai_max_question_chars: int = Field(
        default=500,
        validation_alias=AliasChoices("SKYFLEET_AI_MAX_QUESTION_CHARS", "ai_max_question_chars"),
    )
    ai_max_output_tokens: int = Field(
        default=400,
        validation_alias=AliasChoices("SKYFLEET_AI_MAX_OUTPUT_TOKENS", "ai_max_output_tokens"),
    )
    ai_request_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices(
            "SKYFLEET_AI_REQUEST_TIMEOUT_SECONDS", "ai_request_timeout_seconds"
        ),
    )
    ai_max_requests_per_hour: int = Field(
        default=10,
        validation_alias=AliasChoices(
            "SKYFLEET_AI_MAX_REQUESTS_PER_HOUR", "ai_max_requests_per_hour"
        ),
    )
    ai_min_interval_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "SKYFLEET_AI_MIN_INTERVAL_SECONDS", "ai_min_interval_seconds"
        ),
    )
    # Internal lifetime ceiling (pessimistic reservations and unknown outcomes included) in USD.
    ai_budget_ceiling_usd: Decimal = Field(
        default=Decimal("4.00"),
        validation_alias=AliasChoices("SKYFLEET_AI_BUDGET_CEILING_USD", "ai_budget_ceiling_usd"),
    )
    # After an authentication, permission, billing, spend-limit or invalid-request failure no new
    # request is sent for this long, so a bad key or an empty balance is not hammered.
    ai_error_backoff_seconds: int = Field(
        default=900,
        validation_alias=AliasChoices(
            "SKYFLEET_AI_ERROR_BACKOFF_SECONDS", "ai_error_backoff_seconds"
        ),
    )

    # Feature 017A: how long a DELIVERED order stays in the active operational views, counted from
    # its persisted delivery time. The order itself is never deleted.
    order_delivered_visibility_seconds: float = Field(default=120.0, gt=0)

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
        if self.order_sim_max_interval_seconds < self.order_sim_min_interval_seconds:
            raise ValueError(
                "ORDER_SIM_MAX_INTERVAL_SECONDS must not be below ORDER_SIM_MIN_INTERVAL_SECONDS"
            )
        if self.incident_sim_max_interval_seconds < self.incident_sim_min_interval_seconds:
            raise ValueError(
                "INCIDENT_SIM_MAX_INTERVAL_SECONDS must not be below "
                "INCIDENT_SIM_MIN_INTERVAL_SECONDS"
            )
        if self.incident_sim_cooldown_max_seconds < self.incident_sim_cooldown_min_seconds:
            raise ValueError(
                "INCIDENT_SIM_COOLDOWN_MAX_SECONDS must not be below "
                "INCIDENT_SIM_COOLDOWN_MIN_SECONDS"
            )
        if (
            self.incident_sim_weight_lpr
            + self.incident_sim_weight_recipient
            + self.incident_sim_weight_failure
            <= 0
        ):
            raise ValueError("At least one INCIDENT_SIM_WEIGHT_* must be above zero")
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
