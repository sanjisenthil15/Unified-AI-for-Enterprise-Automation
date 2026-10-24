"""scheduled meetings

Revision ID: 4f6d3fc0cb83
Revises: b45b5f86dcc9
Create Date: 2026-10-24 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f6d3fc0cb83'
down_revision: Union[str, Sequence[str], None] = 'b45b5f86dcc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A meeting can now be booked ahead of time (no recording/transcript yet)
    # and later filled in — either by an upload or by an online session ending.
    op.execute("ALTER TYPE meeting_status ADD VALUE IF NOT EXISTS 'scheduled'")
    op.add_column(
        "meetings",
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("meetings", "scheduled_at")
    # PostgreSQL cannot drop a value from an enum type. Rebuild it without
    # 'scheduled' (safe: no rows should hold that state if downgrading).
    op.execute("ALTER TYPE meeting_status RENAME TO meeting_status_old")
    op.execute(
        "CREATE TYPE meeting_status AS ENUM "
        "('pending', 'processing', 'extracting_audio', 'transcribing', "
        "'diarizing', 'analyzing', 'completed', 'failed')"
    )
    op.execute("ALTER TABLE meetings ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE meetings ALTER COLUMN status TYPE meeting_status "
        "USING status::text::meeting_status"
    )
    op.execute("ALTER TABLE meetings ALTER COLUMN status SET DEFAULT 'pending'")
    op.execute("DROP TYPE meeting_status_old")
