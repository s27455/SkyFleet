"""`ask_fleet_question`: the one orchestration function that asks the gateway about the fleet.

Order, stopping at the first refusal:

 1. AI disabled: refuse, no database read.
 2. Prepare the question (`question.py`): one line, no forged `Fleet context`, named drones. Then
    validate it and its size (the same rules the gateway applies), before any work.
 3. Compute the context budget from the REAL question: `ai_max_input_bytes` minus the fixed system
    instructions, the wrapper text and the question's own bytes.
 4. Build the read-only snapshot, ranking the drones the question names. Any failure raises
    `FleetContextUnavailableError`: the gateway is never called, so no budget is reserved and the
    provider is never contacted.
 5. Render within the budget (reduced and flagged, or refused with `FleetContextTooLargeError`).
 6. Hand the text to `AiGateway.ask(question, context)` unchanged. Every Feature 024 control (the
    readiness check, the 16 KiB check on the complete request, the hourly quota, the interval, one
    request in flight, the durable reservation, the USD 4 ceiling, no retry, no tools) applies
    exactly as before; this function can only make a request smaller or refuse it.

The answer carries the snapshot's trusted metadata (time, status, truncation, limitations, what was
omitted, what happened to the named drones), taken from the snapshot as it was RENDERED.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from app.ai.errors import AiDisabledError
from app.ai.gateway import AiGateway
from app.ai.request import SYSTEM_PROMPT, build_user_content, prepare_request
from app.ai.types import AiAnswer
from app.config import Settings
from app.fleet_context.errors import FleetContextUnavailableError
from app.fleet_context.question import prepare_question
from app.fleet_context.render import render_context
from app.fleet_context.schemas import NamedDrone, Omitted
from app.fleet_context.snapshot import build_fleet_context

logger = logging.getLogger("skyfleet.fleet_context")

UNAVAILABLE = "The fleet snapshot could not be built; no AI request was made."


@dataclass(frozen=True)
class FleetAnswer:
    answer: AiAnswer
    captured_at: str
    data_status: str
    truncated: bool
    context_bytes: int
    limitations: tuple[str, ...] = ()
    omitted: Omitted = field(default_factory=Omitted)
    named_drones: tuple[NamedDrone, ...] = ()


def context_budget(question: str, settings: Settings) -> int:
    """Bytes left for the context once the instructions, the wrapper and the question are in."""
    fixed = len(SYSTEM_PROMPT.encode("utf-8")) + len(
        build_user_content(question, "x").encode("utf-8")
    )
    return settings.ai_max_input_bytes - (fixed - 1)


def ask_fleet_question(
    question: str,
    *,
    gateway: AiGateway,
    factory: sessionmaker[Session],
    settings: Settings,
    now: datetime | None = None,
) -> FleetAnswer:
    if not settings.ai_enabled:
        raise AiDisabledError
    prepared = prepare_question(question)
    prepare_request(
        prepared.text,
        "",
        max_question_chars=settings.ai_max_question_chars,
        max_input_bytes=settings.ai_max_input_bytes,
    )
    budget = context_budget(prepared.text, settings)
    try:
        context = build_fleet_context(factory, settings, now, named_drones=prepared.named_drones)
    except Exception as error:
        logger.error("fleet snapshot failed (%s)", type(error).__name__)
        raise FleetContextUnavailableError(UNAVAILABLE) from None
    rendered = render_context(context, budget)
    answer = gateway.ask(prepared.text, rendered.text)
    final = rendered.context
    return FleetAnswer(
        answer=answer,
        captured_at=final.captured_at,
        data_status=final.data_status.value,
        truncated=final.truncated,
        context_bytes=rendered.size_bytes,
        limitations=tuple(final.limitations),
        omitted=final.omitted,
        named_drones=tuple(final.named_drones),
    )
