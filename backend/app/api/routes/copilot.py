"""AI Copilot endpoints (Feature 026): a status probe and one authenticated `ask`.

`require_copilot_access` is the FIRST dependency of `ask`, so a request that fails any access check
is refused before the Copilot service (and with it the gateway, the fleet snapshot, the budget and
the provider) is even created. Only `ask` can cause a paid call, and only after every check passed.
The handler is a plain `def`: it runs in a worker thread, and the gateway allows one request in
flight, so at most one thread ever waits for the provider.
"""

import logging
import threading
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import sessionmaker

from app.copilot.access import (
    FailedAuthThrottle,
    bearer_token,
    origin_allowed,
    token_matches,
)
from app.copilot.schemas import AskRequest, AskResponse, ErrorCode, StatusResponse
from app.copilot.service import (
    CopilotError,
    CopilotService,
    copilot_available,
    copilot_problems,
    refusal,
)
from app.db.session import get_engine

logger = logging.getLogger("skyfleet.copilot")

router = APIRouter(prefix="/ai/copilot", tags=["ai-copilot"])

_SERVICE_LOCK = threading.Lock()


def http_error(error: CopilotError) -> HTTPException:
    """The fixed response for a refusal: `{code, message}` plus only what the caller needs."""
    detail: dict[str, object] = {"code": error.code.value, "message": error.message}
    headers: dict[str, str] = {}
    if error.retry_after_seconds is not None:
        detail["retry_after_seconds"] = error.retry_after_seconds
        headers["Retry-After"] = str(error.retry_after_seconds)
    if error.charge_possible is not None:
        detail["charge_possible"] = error.charge_possible
    if error.code is ErrorCode.UNAUTHORIZED:
        headers["WWW-Authenticate"] = "Bearer"
    return HTTPException(status_code=error.status, detail=detail, headers=headers or None)


def require_copilot_access(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> None:
    """Origin, enabled, configured, throttle, token: in this order, nothing else runs before."""
    settings = request.app.state.settings
    throttle: FailedAuthThrottle = request.app.state.copilot_throttle
    if not origin_allowed(request.headers.get("origin"), settings.cors_origins):
        raise http_error(refusal(ErrorCode.ORIGIN_NOT_ALLOWED, 403))
    if not settings.ai_enabled:
        raise http_error(refusal(ErrorCode.AI_DISABLED, 503))
    problems = copilot_problems(settings)
    token = settings.ai_access_token
    if problems or token is None:
        logger.warning("copilot misconfigured: %s", "; ".join(problems))  # setting names only
        raise http_error(refusal(ErrorCode.AI_MISCONFIGURED, 503))
    wait = throttle.retry_after()
    if wait:
        raise http_error(refusal(ErrorCode.AUTH_THROTTLED, 429, retry_after_seconds=wait))
    provided = bearer_token(authorization)
    if provided is None or not token_matches(provided, token):
        throttle.record_failure()
        logger.warning("copilot authentication failed")
        raise http_error(refusal(ErrorCode.UNAUTHORIZED, 401))
    throttle.reset()


def get_copilot_service(request: Request) -> CopilotService:
    """The one service of this app, built lazily after the access checks, from ITS Settings."""
    app = request.app
    with _SERVICE_LOCK:
        service: CopilotService | None = getattr(app.state, "copilot_service", None)
        if service is None:
            factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
            service = CopilotService(app.state.settings, factory)
            app.state.copilot_service = service
    return service


@router.get("/status", response_model=StatusResponse)
def copilot_status(request: Request) -> StatusResponse:
    """Generic availability only: no snapshot, no budget, no provider, no reason."""
    return StatusResponse(available=copilot_available(request.app.state.settings))


@router.post("/ask", response_model=AskResponse, dependencies=[Depends(require_copilot_access)])
def ask(
    body: AskRequest, service: Annotated[CopilotService, Depends(get_copilot_service)]
) -> AskResponse:
    try:
        return service.ask(body.question)
    except CopilotError as error:
        raise http_error(error) from None
