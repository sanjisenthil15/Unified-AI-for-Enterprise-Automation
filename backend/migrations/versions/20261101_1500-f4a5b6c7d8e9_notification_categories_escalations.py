"""notifications: categories, entity references, dedupe keys; escalations

- notifications gains category (backfilled from type), entity_type /
  entity_id, and dedupe_key with a partial unique index per user, so a
  retried producer can never insert the same notification twice.
- escalations: one row per (rule, entity) that went unattended past its
  threshold; the unique constraint makes the sweep idempotent.
- scheduled_job_runs: last-run bookkeeping that throttles the lazily
  triggered sweep across workers (no in-process state).

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-11-01 15:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("category", sa.String(length=20), nullable=True))
    op.add_column("notifications", sa.Column("entity_type", sa.String(length=50), nullable=True))
    op.add_column("notifications", sa.Column("entity_id", sa.BigInteger(), nullable=True))
    op.add_column("notifications", sa.Column("dedupe_key", sa.String(length=150), nullable=True))

    # Same mapping as modules/notifications/service.category_for_type.
    op.execute("""
        UPDATE notifications SET category = CASE
            WHEN type LIKE 'task\\_%' OR type LIKE 'sprint\\_%' THEN 'sprint'
            WHEN type LIKE 'meeting%' THEN 'meeting'
            WHEN type LIKE 'chat\\_%' OR type = 'mention' THEN 'chat'
            ELSE 'general'
        END
        WHERE category IS NULL
    """)
    op.alter_column(
        "notifications", "category",
        existing_type=sa.String(length=20), nullable=False, server_default="general",
    )
    op.create_index("ix_notifications_category", "notifications", ["category"])
    op.create_index(
        "uq_notifications_user_dedupe_key", "notifications", ["user_id", "dedupe_key"],
        unique=True, postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )

    op.create_table(
        "escalations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("rule", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("recipient_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("rule", "entity_type", "entity_id", name="uq_escalations_rule_entity"),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="chk_escalations_status"),
        sa.CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL) OR (status = 'resolved' AND resolved_at IS NOT NULL)",
            name="chk_escalations_resolved_at",
        ),
    )
    op.create_index("ix_escalations_status", "escalations", ["status"])
    op.create_index("ix_escalations_triggered_at", "escalations", ["triggered_at"])

    op.create_table(
        "scheduled_job_runs",
        sa.Column("job_name", sa.String(length=50), primary_key=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("scheduled_job_runs")
    op.drop_index("ix_escalations_triggered_at", table_name="escalations")
    op.drop_index("ix_escalations_status", table_name="escalations")
    op.drop_table("escalations")
    op.drop_index("uq_notifications_user_dedupe_key", table_name="notifications")
    op.drop_index("ix_notifications_category", table_name="notifications")
    op.drop_column("notifications", "dedupe_key")
    op.drop_column("notifications", "entity_id")
    op.drop_column("notifications", "entity_type")
    op.drop_column("notifications", "category")
