"""enforce single active manager

Adds a partial unique index on users(role_id) for the 'manager' role
where deleted_at IS NULL and is_active = true.
This guarantees at the database storage engine level that only ONE
active organization-wide Manager account can exist.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-31 18:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    res = conn.execute(sa.text("SELECT id FROM roles WHERE name = 'manager'")).fetchone()
    if res:
        manager_role_id = res[0]
        op.execute(f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_single_active_manager
            ON users (role_id)
            WHERE role_id = {manager_role_id} AND deleted_at IS NULL AND is_active = true
        """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_single_active_manager")
