"""AI spend accounting (Feature 024, Gate B2).

Revision ID: 0019
Revises: 0018

Reviewed and approved in Gate B1/B2 (it was drafted in `migrations/drafts/` first).

Adds two tables and changes nothing else (no existing table, row or constraint):

* `ai_budget_state`: one row (`name = 'anthropic'`, created by the gateway on first use, nothing is
  seeded) holding the spent and the reserved amounts in integer nano-USD and the halt flag;
* `ai_request_log`: one row per request attempt, numbers and codes only. It never holds a prompt,
  an answer, a key or a provider message.

The two must agree (spent = sum of charged; reserved = sum of the reserved amounts of the RESERVED
rows); the gateway checks that on every reservation and halts itself if it does not hold. The
downgrade drops both tables, which discards the spend history: do not downgrade once real
requests have been made unless that is intended.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

STATUSES = "'RESERVED', 'SUCCEEDED', 'REJECTED', 'AMBIGUOUS', 'UNKNOWN'"


def upgrade() -> None:
    op.create_table(
        "ai_budget_state",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("spent_nano_usd", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("reserved_nano_usd", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("halted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("halt_reason", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("spent_nano_usd >= 0", name="ck_ai_budget_spent_nonnegative"),
        sa.CheckConstraint("reserved_nano_usd >= 0", name="ck_ai_budget_reserved_nonnegative"),
    )
    op.create_table(
        "ai_request_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("request_bytes", sa.Integer, nullable=False),
        sa.Column("reserved_nano_usd", sa.BigInteger, nullable=False),
        sa.Column("charged_nano_usd", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("error_code", sa.String(48), nullable=True),
        sa.Column("provider_request_id", sa.String(64), nullable=True),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_ai_request_status_valid"),
        sa.CheckConstraint("reserved_nano_usd >= 0", name="ck_ai_request_reserved_nonnegative"),
        sa.CheckConstraint("charged_nano_usd >= 0", name="ck_ai_request_charged_nonnegative"),
    )
    op.create_index("ix_ai_request_log_created_at", "ai_request_log", ["created_at"])
    op.create_index(
        "ix_ai_request_log_status_created_at", "ai_request_log", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_request_log_status_created_at", table_name="ai_request_log")
    op.drop_index("ix_ai_request_log_created_at", table_name="ai_request_log")
    op.drop_table("ai_request_log")
    op.drop_table("ai_budget_state")
