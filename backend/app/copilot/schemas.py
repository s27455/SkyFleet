"""The typed HTTP contract of the Copilot (Feature 026).

Everything the browser may trust about a snapshot comes from here: it is copied from the
server-side snapshot, never extracted from the model's prose. No cost, token count, provider id or
raw fleet context is returned in v1.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_QUESTION_CHARS = 500


class ErrorCode(StrEnum):
    """The fixed error codes (the HTTP status is chosen per code in `service.py`)."""

    ORIGIN_NOT_ALLOWED = "ORIGIN_NOT_ALLOWED"
    AI_DISABLED = "AI_DISABLED"
    AI_MISCONFIGURED = "AI_MISCONFIGURED"
    UNAUTHORIZED = "UNAUTHORIZED"
    AUTH_THROTTLED = "AUTH_THROTTLED"
    INVALID_QUESTION = "INVALID_QUESTION"
    CONTEXT_TOO_LARGE = "CONTEXT_TOO_LARGE"
    RATE_LIMITED = "RATE_LIMITED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    AI_HALTED = "AI_HALTED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    ACCOUNTING_UNAVAILABLE = "ACCOUNTING_UNAVAILABLE"
    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AskRequest(BaseModel):
    """One question. Nothing else is accepted: no model, system prompt, tool or budget override."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class OmittedInfo(BaseModel):
    drones: int
    hubs: int
    active_incidents: int
    recovered_alerts: int


class NamedDroneInfo(BaseModel):
    id: str
    exists: bool  # false: no such drone in the fleet
    listed: bool  # false: it exists but its row is not in the snapshot the model saw


class SnapshotInfo(BaseModel):
    captured_at: str
    data_status: Literal["complete", "degraded"]
    truncated: bool
    limitations: list[str]  # fixed codes (see the fleet context), possibly with `:detail`
    omitted: OmittedInfo
    named_drones: list[NamedDroneInfo]


class AskResponse(BaseModel):
    answer: str  # untrusted text: the frontend shows it as plain text only
    answer_cut_off: bool  # the model stopped at its output limit
    snapshot: SnapshotInfo


class StatusResponse(BaseModel):
    """Generic availability only: never a secret, a setting or a reason."""

    available: bool
