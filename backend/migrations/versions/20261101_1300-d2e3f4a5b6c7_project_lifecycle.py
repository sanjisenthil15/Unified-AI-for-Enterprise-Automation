"""project lifecycle: status, start_date, completion, cancellation, and archival timestamps

Adds project lifecycle columns to `projects`:
- status: planning, active, on_hold, completed, cancelled, archived
- start_date: project start date
- completed_at: timestamp when completed
- cancelled_at: timestamp when cancelled
- archived_at: timestamp when archived

Backfills all existing projects to 'active'.
New projects default to 'planning'.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-11-01 13:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns (status added nullable initially for safe backfill)
    op.add_column("projects", sa.Column("status", sa.String(length=20), nullable=True))
    op.add_column("projects", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("projects", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("projects", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))

    # 2. Backfill existing projects to 'active'
    op.execute("UPDATE projects SET status = 'active' WHERE status IS NULL")

    # 3. Enforce NOT NULL and server_default='planning' for status
    op.alter_column(
        "projects",
        "status",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="planning",
    )

    # 4. Check constraints
    op.create_check_constraint(
        "chk_projects_status",
        "projects",
        "status IN ('planning', 'active', 'on_hold', 'completed', 'cancelled', 'archived')",
    )
    op.create_check_constraint(
        "chk_projects_completed_at",
        "projects",
        "(completed_at IS NULL) OR (status IN ('completed', 'archived'))",
    )
    op.create_check_constraint(
        "chk_projects_cancelled_at",
        "projects",
        "(cancelled_at IS NULL) OR (status IN ('cancelled', 'archived'))",
    )
    op.create_check_constraint(
        "chk_projects_archived_at",
        "projects",
        "(archived_at IS NULL) OR (status = 'archived')",
    )


def downgrade() -> None:
    # 1. Drop check constraints
    op.drop_constraint("chk_projects_archived_at", "projects", type_="check")
    op.drop_constraint("chk_projects_cancelled_at", "projects", type_="check")
    op.drop_constraint("chk_projects_completed_at", "projects", type_="check")
    op.drop_constraint("chk_projects_status", "projects", type_="check")

    # 2. Drop columns
    op.drop_column("projects", "cancelled_at")
    op.drop_column("projects", "archived_at")
    op.drop_column("projects", "completed_at")
    op.drop_column("projects", "start_date")
    op.drop_column("projects", "status")

