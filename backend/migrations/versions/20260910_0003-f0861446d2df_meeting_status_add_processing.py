"""meeting status add processing

Revision ID: f0861446d2df
Revises: cfa33efa1872
Create Date: 2026-09-10 00:03:08.877321
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0861446d2df'
down_revision: Union[str, Sequence[str], None] = 'cfa33efa1872'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Phase 8 pipeline uses a single coarse "processing" state
    # (pending -> processing -> completed / failed).
    op.execute("ALTER TYPE meeting_status ADD VALUE IF NOT EXISTS 'processing'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type. Rebuild it without
    # 'processing' (safe: no rows should hold that transient state at rest).
    op.execute("ALTER TYPE meeting_status RENAME TO meeting_status_old")
    op.execute(
        "CREATE TYPE meeting_status AS ENUM "
        "('pending', 'extracting_audio', 'transcribing', 'diarizing', "
        "'analyzing', 'completed', 'failed')"
    )
    op.execute("ALTER TABLE meetings ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE meetings ALTER COLUMN status TYPE meeting_status "
        "USING status::text::meeting_status"
    )
    op.execute("ALTER TABLE meetings ALTER COLUMN status SET DEFAULT 'pending'")
    op.execute("DROP TYPE meeting_status_old")
