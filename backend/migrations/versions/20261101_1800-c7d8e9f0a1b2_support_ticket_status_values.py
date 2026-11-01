"""support tickets: add 'assigned' and 'waiting_for_customer' statuses

The ORM model, API schema, ticket UI ("Waiting for Customer") and the
analytics / intelligence "open ticket" counts all use these two statuses,
but the support_ticket_status enum created in 84adb65613d9 lacked them —
so setting either failed with a database error. Upgrade only adds enum
values: no existing row changes.

Downgrade note: Postgres can't drop enum values, so downgrade rebuilds the
type and maps rows that use the new values to their nearest older status
(assigned -> open, waiting_for_customer -> in_progress). That mapping is
lossy; never downgrade production (restore a backup instead).

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-11-01 18:00:00
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_VALUES = ("open", "in_progress", "resolved", "closed", "escalated")


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE can't be used inside the migration's
    # transaction on older Postgres versions, so run it in autocommit.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE support_ticket_status ADD VALUE IF NOT EXISTS 'assigned' AFTER 'open'")
        op.execute("ALTER TYPE support_ticket_status ADD VALUE IF NOT EXISTS 'waiting_for_customer' AFTER 'in_progress'")


def downgrade() -> None:
    op.execute("UPDATE support_tickets SET status = 'open' WHERE status = 'assigned'")
    op.execute("UPDATE support_tickets SET status = 'in_progress' WHERE status = 'waiting_for_customer'")
    op.execute("ALTER TYPE support_ticket_status RENAME TO support_ticket_status_new")
    values = ", ".join(f"'{v}'" for v in OLD_VALUES)
    op.execute(f"CREATE TYPE support_ticket_status AS ENUM ({values})")
    # The column has no server default (see 84adb65613d9), so none to restore.
    op.execute(
        "ALTER TABLE support_tickets ALTER COLUMN status TYPE support_ticket_status "
        "USING status::text::support_ticket_status"
    )
    op.execute("DROP TYPE support_ticket_status_new")
