"""leave requests: employee leave submitted for Admin / HR Manager approval

Creates `leave_requests`. Approval (not submission) is what marks
attendance days `on_leave`. No entitlement / balance tables — there is
no approved policy for one.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-11-01 14:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leave_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "employee_id", sa.BigInteger(),
            sa.ForeignKey("employees.id", onupdate="CASCADE", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("leave_type", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("working_days", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column(
            "reviewed_by_id", sa.BigInteger(),
            sa.ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(length=500), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("end_date >= start_date", name="chk_leave_requests_dates"),
        sa.CheckConstraint(
            "leave_type IN ('annual', 'sick', 'casual', 'unpaid', 'other')",
            name="chk_leave_requests_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="chk_leave_requests_status",
        ),
        sa.CheckConstraint(
            "status NOT IN ('approved', 'rejected') OR (reviewed_by_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="chk_leave_requests_reviewed",
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR length(trim(coalesce(decision_note, ''))) > 0",
            name="chk_leave_requests_rejection_reason",
        ),
        sa.CheckConstraint(
            "status <> 'cancelled' OR cancelled_at IS NOT NULL",
            name="chk_leave_requests_cancelled_at",
        ),
    )
    op.create_index("ix_leave_requests_employee_id", "leave_requests", ["employee_id"])
    op.create_index("ix_leave_requests_status", "leave_requests", ["status"])
    op.create_index("ix_leave_requests_created_at", "leave_requests", ["created_at"])
    op.create_index(
        "ix_leave_requests_employee_dates", "leave_requests", ["employee_id", "start_date", "end_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_leave_requests_employee_dates", table_name="leave_requests")
    op.drop_index("ix_leave_requests_created_at", table_name="leave_requests")
    op.drop_index("ix_leave_requests_status", table_name="leave_requests")
    op.drop_index("ix_leave_requests_employee_id", table_name="leave_requests")
    op.drop_table("leave_requests")
