"""Durable AI spend accounting: one budget row and one log row per request.

These tables hold only numbers and codes. They never hold a prompt, an answer, a key or a
provider message. Money is stored as integer nano-USD (1e-9 USD) in BIGINT columns, so sums are
exact. The two tables must agree at all times:

    budget.spent_nano_usd    = SUM(request.charged_nano_usd)
    budget.reserved_nano_usd = SUM(request.reserved_nano_usd) of the requests still RESERVED

and the store checks that on every reservation and halts itself if it does not hold. Log rows are
never deleted (the lifetime total is derived from them); that is a few hundred rows a day at most.

The proposed migration is `migrations/drafts/0019_ai_budget.py` (a draft: not applied).
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

BUDGET_NAME = "anthropic"


class RequestStatus(StrEnum):
    RESERVED = "RESERVED"  # sent or about to be sent; its reservation is held
    SUCCEEDED = "SUCCEEDED"  # charged the provider-reported cost
    REJECTED = "REJECTED"  # the provider refused it before generating anything: refunded
    # May have been billed (a timeout, a 5xx, a dropped connection): charged in full.
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"  # a reservation nobody settled (a crash): charged in full


_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in RequestStatus)


class AiBudgetState(Base):
    __tablename__ = "ai_budget_state"
    __table_args__ = (
        CheckConstraint("spent_nano_usd >= 0", name="ck_ai_budget_spent_nonnegative"),
        CheckConstraint("reserved_nano_usd >= 0", name="ck_ai_budget_reserved_nonnegative"),
    )

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    spent_nano_usd: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    reserved_nano_usd: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    # Set when the gateway stopped itself (an estimate was exceeded or the books disagree); only a
    # person clears it after looking at the cause.
    halted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    halt_reason: Mapped[str | None] = mapped_column(String(64), default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AiRequestLog(Base):
    __tablename__ = "ai_request_log"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="ck_ai_request_status_valid"),
        CheckConstraint("reserved_nano_usd >= 0", name="ck_ai_request_reserved_nonnegative"),
        CheckConstraint("charged_nano_usd >= 0", name="ck_ai_request_charged_nonnegative"),
        Index("ix_ai_request_log_created_at", "created_at"),
        Index("ix_ai_request_log_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    model: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    request_bytes: Mapped[int] = mapped_column(Integer)
    reserved_nano_usd: Mapped[int] = mapped_column(BigInteger)
    charged_nano_usd: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    # A stable code only (an `UpstreamKind` value or a fixed word), never provider text.
    error_code: Mapped[str | None] = mapped_column(String(48), default=None)
    provider_request_id: Mapped[str | None] = mapped_column(String(64), default=None)
