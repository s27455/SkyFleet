"""Durable, atomic AI spend accounting.

THE DESIGN. Before a request is sent, `reserve` takes a row lock on the single budget row
(`SELECT ... FOR UPDATE`) and, in that one transaction, sweeps abandoned reservations, checks that
the books agree, checks every limit and the budget, adds the request's pessimistic cost to
`reserved` and records a `RESERVED` log row. The lock is held until the commit, so two requests,
in this process or another, can never both pass the same check: the second waits, then sees the
first one's reservation. Nothing is sent unless the reservation was committed.

After the call exactly one of three things settles the reservation, never an automatic refund of
unknown spend:

* success: the provider-reported cost is charged and the rest is released;
* the provider rejected the request before generating anything: it is refunded;
* the outcome is unclear (a timeout, a 5xx, a dropped connection): the whole reservation is kept
  as spent.

A reservation that nobody settles (a crash after the send) is swept to `UNKNOWN` and charged in
full once it is older than the lease, `stale_after_seconds`, so a crash can only make the books
more conservative. The lease is the longest a request may plausibly be alive (the SDK itself caps
a non-streaming request at 10 minutes), and the slot is NOT freed by the sweep: for one more lease
after a sweep no new request may start (`ConcurrencyLimitError`), because a swept request might
still be running. So a second provider request starts at least two leases after the first began,
never while the first may still be active. The accounting store is trusted only while it agrees
with itself: if the budget row and the log disagree, the store halts itself and the gateway stays
closed until a person looks.

Any database error on the way to a reservation becomes `AccountingUnavailableError`: no
reservation, no request. Amounts are integer nano-USD (1e-9 USD).
"""

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.ai.errors import (
    BACKOFF_KINDS,
    AccountingUnavailableError,
    AiError,
    AiHaltedError,
    BudgetExhaustedError,
    ConcurrencyLimitError,
    ErrorBackoffError,
    RateLimitedError,
    TooSoonError,
)
from app.ai.models import BUDGET_NAME, AiBudgetState, AiRequestLog, RequestStatus
from app.ai.types import TransportUsage

logger = logging.getLogger("skyfleet.ai")

UNAVAILABLE = "The AI budget could not be read or written; no request was sent."
STALE_ERROR_CODE = "stale_reservation"
_BACKOFF_CODES = tuple(kind.value for kind in BACKOFF_KINDS)


@dataclass(frozen=True)
class BudgetLimits:
    ceiling_nano_usd: int
    max_requests_per_hour: int
    min_interval_seconds: int
    # The lease: an unsettled reservation older than this is swept (charged in full), and no new
    # request may start until this long after the sweep, so a slow request cannot overlap the next.
    stale_after_seconds: int
    error_backoff_seconds: int


@dataclass(frozen=True)
class Reservation:
    request_id: int
    reserved_nano_usd: int
    model: str


@dataclass(frozen=True)
class BudgetSnapshot:
    spent_nano_usd: int
    reserved_nano_usd: int
    halted: bool
    halt_reason: str | None


class BudgetStore(Protocol):
    """What the gateway needs from the accounting; the SQL store below is the real one."""

    def reserve(
        self,
        *,
        model: str,
        reserved_nano_usd: int,
        request_bytes: int,
        limits: BudgetLimits,
        now: datetime,
    ) -> Reservation: ...

    def settle_success(
        self,
        reservation: Reservation,
        *,
        charged_nano_usd: int,
        usage: TransportUsage,
        provider_request_id: str | None,
        now: datetime,
    ) -> None: ...

    def settle_rejected(
        self,
        reservation: Reservation,
        *,
        error_code: str,
        provider_request_id: str | None,
        now: datetime,
    ) -> None: ...

    def settle_ambiguous(
        self,
        reservation: Reservation,
        *,
        error_code: str,
        provider_request_id: str | None,
        now: datetime,
    ) -> None: ...

    def halt(self, reason: str, now: datetime) -> None: ...

    def snapshot(self) -> BudgetSnapshot: ...


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive timestamps; everything stored here is UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _ensure_row(session: Session, now: datetime) -> None:
    """Create the budget row if it is missing (idempotent, safe when two callers race)."""
    values = {
        "name": BUDGET_NAME,
        "spent_nano_usd": 0,
        "reserved_nano_usd": 0,
        "halted": False,
        "updated_at": now,
    }
    insert: Any = (
        postgresql_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    )
    session.execute(insert(AiBudgetState).values(**values).on_conflict_do_nothing())


def _lock_budget(session: Session) -> AiBudgetState:
    """The budget row, locked until this transaction ends (a no-op lock on SQLite)."""
    return session.scalars(
        select(AiBudgetState)
        .where(AiBudgetState.name == BUDGET_NAME)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


class SqlBudgetStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    # --- reservation --------------------------------------------------------------------------

    def reserve(
        self,
        *,
        model: str,
        reserved_nano_usd: int,
        request_bytes: int,
        limits: BudgetLimits,
        now: datetime,
    ) -> Reservation:
        with self._factory() as session:
            try:
                _ensure_row(session, now)
                budget = _lock_budget(session)
                self._sweep_stale(session, budget, limits, now)
                self._verify_books(session, budget, now)
                refusal = self._refusal(session, budget, reserved_nano_usd, limits, now)
                if refusal is not None:
                    session.commit()  # keeps the sweep (and a halt); nothing was reserved
                    raise refusal
                budget.reserved_nano_usd += reserved_nano_usd
                budget.updated_at = now
                row = AiRequestLog(
                    created_at=now,
                    model=model,
                    status=RequestStatus.RESERVED.value,
                    request_bytes=request_bytes,
                    reserved_nano_usd=reserved_nano_usd,
                    charged_nano_usd=0,
                )
                session.add(row)
                session.flush()
                reservation = Reservation(row.id, reserved_nano_usd, model)
                session.commit()
                return reservation
            except AiError:
                session.rollback()
                raise
            except SQLAlchemyError:
                session.rollback()
                raise AccountingUnavailableError(UNAVAILABLE) from None

    def _sweep_stale(
        self, session: Session, budget: AiBudgetState, limits: BudgetLimits, now: datetime
    ) -> None:
        """Charge in full every reservation that was never settled for too long."""
        cutoff = now - timedelta(seconds=limits.stale_after_seconds)
        stale = session.scalars(
            select(AiRequestLog)
            .where(AiRequestLog.status == RequestStatus.RESERVED.value)
            .where(AiRequestLog.created_at < cutoff)
            .with_for_update()
        ).all()
        moved = 0
        for row in stale:
            row.status = RequestStatus.UNKNOWN.value
            row.charged_nano_usd = row.reserved_nano_usd
            row.finished_at = now
            row.error_code = STALE_ERROR_CODE
            moved += row.reserved_nano_usd
        if moved:
            budget.reserved_nano_usd -= moved
            budget.spent_nano_usd += moved
            budget.updated_at = now
            logger.warning("AI accounting: %s stale reservation(s) charged in full", len(stale))

    def _verify_books(self, session: Session, budget: AiBudgetState, now: datetime) -> None:
        """The budget row and the log must agree; if not, halt and stay closed."""
        charged = int(
            session.scalar(select(func.coalesce(func.sum(AiRequestLog.charged_nano_usd), 0))) or 0
        )
        held = int(
            session.scalar(
                select(func.coalesce(func.sum(AiRequestLog.reserved_nano_usd), 0)).where(
                    AiRequestLog.status == RequestStatus.RESERVED.value
                )
            )
            or 0
        )
        if charged != budget.spent_nano_usd or held != budget.reserved_nano_usd:
            budget.halted = True
            budget.halt_reason = "ACCOUNTING_INCONSISTENT"
            budget.updated_at = now
            logger.error("AI accounting: the budget row and the request log disagree; halted")

    def _refusal(
        self,
        session: Session,
        budget: AiBudgetState,
        reserved_nano_usd: int,
        limits: BudgetLimits,
        now: datetime,
    ) -> AiError | None:
        """The first reason to refuse this request, or None. Reads only; it never writes."""
        if budget.halted:
            return AiHaltedError(
                "The AI assistant stopped itself and stays closed until it is reviewed "
                f"({budget.halt_reason or 'halted'})."
            )

        last_failure = session.scalar(
            select(func.max(AiRequestLog.finished_at)).where(
                AiRequestLog.status == RequestStatus.REJECTED.value,
                AiRequestLog.error_code.in_(_BACKOFF_CODES),
            )
        )
        if last_failure is not None:
            wait = limits.error_backoff_seconds - (now - _as_utc(last_failure)).total_seconds()
            if wait > 0:
                return ErrorBackoffError(
                    "The last AI request failed because of the key, the balance or the request; "
                    "waiting before trying again.",
                    retry_after_seconds=math.ceil(wait),
                )

        in_flight = session.scalar(
            select(func.count())
            .select_from(AiRequestLog)
            .where(AiRequestLog.status == RequestStatus.RESERVED.value)
        )
        if (in_flight or 0) >= 1:
            return ConcurrencyLimitError("Another AI request is still in progress.")

        # A swept request may still be running (we only know it outlived its lease): keep the slot
        # closed for one more lease after the sweep.
        last_sweep = session.scalar(
            select(func.max(AiRequestLog.finished_at)).where(
                AiRequestLog.status == RequestStatus.UNKNOWN.value,
                AiRequestLog.error_code == STALE_ERROR_CODE,
            )
        )
        if last_sweep is not None:
            wait = limits.stale_after_seconds - (now - _as_utc(last_sweep)).total_seconds()
            if wait > 0:
                return ConcurrencyLimitError(
                    "A previous AI request outlived its lease and may still be active; waiting.",
                    retry_after_seconds=math.ceil(wait),
                )

        last_created = session.scalar(select(func.max(AiRequestLog.created_at)))
        if last_created is not None:
            wait = limits.min_interval_seconds - (now - _as_utc(last_created)).total_seconds()
            if wait > 0:
                return TooSoonError(
                    f"AI requests must be at least {limits.min_interval_seconds} seconds apart.",
                    retry_after_seconds=math.ceil(wait),
                )

        window = [
            _as_utc(created)
            for created in session.scalars(
                select(AiRequestLog.created_at)
                .where(AiRequestLog.created_at > now - timedelta(hours=1))
                .order_by(AiRequestLog.created_at)
            )
        ]
        if len(window) >= limits.max_requests_per_hour:
            expires = window[len(window) - limits.max_requests_per_hour] + timedelta(hours=1)
            return RateLimitedError(
                f"At most {limits.max_requests_per_hour} AI requests per hour are allowed.",
                retry_after_seconds=max(1, math.ceil((expires - now).total_seconds())),
            )

        committed = budget.spent_nano_usd + budget.reserved_nano_usd
        if committed + reserved_nano_usd > limits.ceiling_nano_usd:
            return BudgetExhaustedError("The AI budget ceiling would be exceeded.")
        return None

    # --- settlement ---------------------------------------------------------------------------

    def settle_success(
        self,
        reservation: Reservation,
        *,
        charged_nano_usd: int,
        usage: TransportUsage,
        provider_request_id: str | None,
        now: datetime,
    ) -> None:
        self._settle(
            reservation,
            status=RequestStatus.SUCCEEDED,
            charged=charged_nano_usd,
            error_code=None,
            provider_request_id=provider_request_id,
            usage=usage,
            now=now,
        )

    def settle_rejected(
        self,
        reservation: Reservation,
        *,
        error_code: str,
        provider_request_id: str | None,
        now: datetime,
    ) -> None:
        self._settle(
            reservation,
            status=RequestStatus.REJECTED,
            charged=0,
            error_code=error_code,
            provider_request_id=provider_request_id,
            usage=None,
            now=now,
        )

    def settle_ambiguous(
        self,
        reservation: Reservation,
        *,
        error_code: str,
        provider_request_id: str | None,
        now: datetime,
    ) -> None:
        self._settle(
            reservation,
            status=RequestStatus.AMBIGUOUS,
            charged=reservation.reserved_nano_usd,
            error_code=error_code,
            provider_request_id=provider_request_id,
            usage=None,
            now=now,
        )

    def _settle(
        self,
        reservation: Reservation,
        *,
        status: RequestStatus,
        charged: int,
        error_code: str | None,
        provider_request_id: str | None,
        usage: TransportUsage | None,
        now: datetime,
    ) -> None:
        with self._factory() as session:
            try:
                budget = _lock_budget(session)
                row = session.scalars(
                    select(AiRequestLog)
                    .where(AiRequestLog.id == reservation.request_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                ).one()
                if row.status == RequestStatus.RESERVED.value:
                    budget.reserved_nano_usd -= row.reserved_nano_usd
                    budget.spent_nano_usd += charged
                    row.status = status.value
                    row.charged_nano_usd = charged
                else:
                    # Already swept (charged in full as UNKNOWN): only a larger real cost adds more.
                    extra = max(0, charged - row.charged_nano_usd)
                    budget.spent_nano_usd += extra
                    row.charged_nano_usd += extra
                row.finished_at = now
                row.error_code = row.error_code if row.status == "UNKNOWN" else error_code
                row.provider_request_id = provider_request_id
                if usage is not None:
                    row.prompt_tokens = usage.prompt_tokens
                    row.output_tokens = usage.output_tokens
                budget.updated_at = now
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise AccountingUnavailableError(UNAVAILABLE) from None

    # --- the breaker and a read-only view -----------------------------------------------------

    def halt(self, reason: str, now: datetime) -> None:
        """Stop the gateway until a person clears it (the reason is a fixed code, never text)."""
        with self._factory() as session:
            try:
                _ensure_row(session, now)
                budget = _lock_budget(session)
                budget.halted = True
                budget.halt_reason = reason[:64]
                budget.updated_at = now
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise AccountingUnavailableError(UNAVAILABLE) from None

    def snapshot(self) -> BudgetSnapshot:
        with self._factory() as session:
            try:
                row = session.get(AiBudgetState, BUDGET_NAME)
            except SQLAlchemyError:
                raise AccountingUnavailableError(UNAVAILABLE) from None
            if row is None:
                return BudgetSnapshot(0, 0, False, None)
            return BudgetSnapshot(
                row.spent_nano_usd, row.reserved_nano_usd, row.halted, row.halt_reason
            )
