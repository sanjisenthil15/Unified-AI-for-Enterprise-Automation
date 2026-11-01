"""auth rate-limit counters and per-user Customer Support notification preferences

- auth_attempts: failed-login / registration counters for database-backed
  rate limiting (stores only HMAC digests of email and IP).
- support_notification_preferences: one row per user, replacing a single
  in-memory dict that all users shared.

Both are new, empty tables — nothing existing is changed, so the previous
application version keeps working against this schema.

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-11-01 17:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("account_key", sa.String(length=64), nullable=True),
        sa.Column("ip_key", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('login_failure', 'registration')", name="chk_auth_attempts_kind"),
    )
    op.create_index("ix_auth_attempts_created_at", "auth_attempts", ["created_at"])
    op.create_index("ix_auth_attempts_kind_account", "auth_attempts", ["kind", "account_key", "created_at"])
    op.create_index("ix_auth_attempts_kind_ip", "auth_attempts", ["kind", "ip_key", "created_at"])

    op.create_table(
        "support_notification_preferences",
        sa.Column(
            "user_id", sa.BigInteger(),
            sa.ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("email_notifications", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("ticket_updates", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sla_alerts", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("incident_alerts", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("agent_replies", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("support_notification_preferences")
    op.drop_index("ix_auth_attempts_kind_ip", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_kind_account", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_created_at", table_name="auth_attempts")
    op.drop_table("auth_attempts")
